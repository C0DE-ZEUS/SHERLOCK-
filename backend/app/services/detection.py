"""Deterministic detection of sensitive information in plain text.

Detection is regex-based with validation (checksums, context keywords, digit
counts) to keep false positives down. Matches are *possible* sensitive data:
nothing here verifies that an identifier is real or belongs to anyone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import parse_qsl, urlsplit

HIGH, MEDIUM, LOW = "high", "medium", "low"


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    explanation: str


CATEGORIES: dict[str, Category] = {
    c.key: c
    for c in [
        Category(
            "secret",
            "Potential secret or API key",
            "Matches a common format for API keys, access tokens, private keys, or a labelled "
            "password. Anyone holding a live secret can usually act as its owner.",
        ),
        Category(
            "url",
            "URL",
            "Links can expose private documents, internal systems, or access tokens embedded "
            "in the address.",
        ),
        Category(
            "email",
            "Email address",
            "A personal or work email address can identify someone and be used for spam or "
            "phishing.",
        ),
        Category(
            "bank_account",
            "Possible bank account number",
            "A 9-18 digit number next to an account label. Shown as a possible match only; "
            "Sherlock cannot verify bank accounts.",
        ),
        Category(
            "payment_card",
            "Possible payment card number",
            "A 13-19 digit number that passes the Luhn checksum used by card networks. "
            "This is a possible match, not a verified card.",
        ),
        Category(
            "aadhaar",
            "Possible Aadhaar number",
            "A 12-digit number in the Aadhaar format that passes the Verhoeff checksum. "
            "This is a possible match, not a verified identity.",
        ),
        Category(
            "pan",
            "Possible PAN",
            "Matches the format of an Indian Permanent Account Number (5 letters, 4 digits, "
            "1 letter). This is a possible match, not a verified identity.",
        ),
        Category(
            "ifsc",
            "Possible IFSC code",
            "Matches the format of an Indian bank branch code. Combined with an account "
            "number it can help identify a bank account.",
        ),
        Category(
            "phone",
            "Phone number",
            "A phone number can identify a person and be used for unwanted contact.",
        ),
    ]
}


@dataclass(frozen=True)
class Match:
    category: str
    risk: str
    start: int
    end: int
    value: str
    detail: str = ""  # short sub-type, e.g. "GitHub token"


# --------------------------------------------------------------------------
# Validators
# --------------------------------------------------------------------------

_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_valid(digits: str) -> bool:
    check = 0
    for i, ch in enumerate(reversed(digits)):
        check = _VERHOEFF_D[check][_VERHOEFF_P[i % 8][int(ch)]]
    return check == 0


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


# --------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "Private key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:[\s\S]{0,6000}?-----END [A-Z ]*PRIVATE KEY-----)?"
        ),
    ),
    ("AWS access key ID", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b")),
    ("GitHub token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,255}\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe key", re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("API secret key", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}")),
    (
        "JSON Web Token",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ),
]

# "password: xyz", "api_key = xyz" ... the value (group 1) is the finding.
_LABELLED_SECRET = re.compile(
    r"(?i)\b(?:api[_ -]?key|secret(?:[_ -]?key)?|client[_ -]?secret|access[_ -]?token|"
    r"auth[_ -]?token|bearer|password|passwd|pwd|token)\b\s*[:=]?\s*[\"']?"
    r"([^\s\"',;]{6,200})"
)
# Words that commonly follow "password"/"token" in prose and are not secrets.
_LABELLED_STOPWORDS = {
    "required", "reset", "expired", "changed", "manager", "policy", "protected",
    "should", "must", "will", "field", "strength", "hidden", "provided", "invalid",
}

_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'`{}|\\^\[\]]+")
_URL_SENSITIVE_PARAMS = re.compile(
    r"(?i)^(?:token|access_token|id_token|refresh_token|auth|authorization|key|api_key|apikey|"
    r"sig|signature|secret|password|pass|pwd|session|sessionid|sid|code|otp|"
    r"x-amz-signature|x-amz-credential|x-goog-signature|sv|se|sp)$"
)

_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@(?:[A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,24}(?![A-Za-z0-9-])"
)

_BANK_ACCOUNT = re.compile(
    r"(?i)\b(?:a/c|acct|account|acc|bank\s+account)\.?\s*(?:no|number|num|#)?\.?\s*[:#-]?\s*"
    r"(\d(?:[ -]?\d){8,17})(?![\d])"
)
# Contiguous digits, 4-4-4-4(-x) groups, or the 4-6-5 Amex layout.
_CARD = re.compile(
    r"(?<![\d-])(?:\d{13,19}|\d{4}([ -])\d{4}\1\d{4}\1\d{1,7}|\d{4}([ -])\d{6}\2\d{5})(?![\d-])"
)
_AADHAAR = re.compile(r"(?<![\d-])[2-9]\d{3}([ -]?)\d{4}\1\d{4}(?![\d-])")
_PAN = re.compile(r"\b[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]\b")
_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")

_PHONE_PATTERNS = [
    # Indian mobile: +91 98765 43210, +91-9876543210, 09876543210, 98765-43210
    re.compile(r"(?<![\w+])(?:(?:\+|00)91[\s.-]?|0)?[6-9]\d{4}[\s.-]?\d{5}(?![\w])"),
    # Indian landline with STD code: 022-2345 6789, 080 23456789
    re.compile(r"(?<![\w+])0\d{2,4}[\s-]\d{3,4}[\s-]?\d{4}(?![\w])"),
    # International with explicit country code
    re.compile(r"(?<![\w+])\+\d{1,3}[\s.-]?(?:\(\d{1,4}\)[\s.-]?)?\d{2,5}(?:[\s.-]?\d{2,5}){1,4}(?![\w])"),
    # North American style with separators: (555) 123-4567, 555-123-4567
    re.compile(r"(?<![\w])(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\w])"),
]


# --------------------------------------------------------------------------
# Detectors. Each yields matches; earlier detectors win overlaps.
# --------------------------------------------------------------------------

def _secrets(text: str) -> Iterable[Match]:
    for detail, pattern in _SECRET_PATTERNS:
        for m in pattern.finditer(text):
            yield Match("secret", HIGH, m.start(), m.end(), m.group(0), detail)


def _labelled_secrets(text: str) -> Iterable[Match]:
    for m in _LABELLED_SECRET.finditer(text):
        value = m.group(1)
        if value.lower().rstrip(".:") in _LABELLED_STOPWORDS:
            continue
        if not re.search(r"[A-Za-z0-9]", value) or set(value) <= {"*", "•", "x", "X"}:
            continue
        # Require some character variety so ordinary words are not flagged.
        if value.isalpha() and value.islower() and len(value) < 12:
            continue
        yield Match("secret", HIGH, m.start(1), m.end(1), value, "Labelled credential")


def _urls(text: str) -> Iterable[Match]:
    for m in _URL.finditer(text):
        raw = m.group(0)
        trimmed = raw.rstrip(".,;:!?)'\"")
        if len(trimmed) < 8:
            continue
        risk, detail = LOW, "Link"
        try:
            parts = urlsplit(trimmed if "://" in trimmed else "http://" + trimmed)
            params = parse_qsl(parts.query, keep_blank_values=True)
            fragment_params = parse_qsl(parts.fragment, keep_blank_values=True)
            if any(_URL_SENSITIVE_PARAMS.match(k) for k, _ in params + fragment_params):
                risk, detail = HIGH, "Link containing a token or key"
            elif parts.query or re.search(r"[A-Za-z0-9_-]{20,}", parts.path):
                risk, detail = MEDIUM, "Link that may be private"
        except ValueError:
            pass
        yield Match("url", risk, m.start(), m.start() + len(trimmed), trimmed, detail)


def _emails(text: str) -> Iterable[Match]:
    for m in _EMAIL.finditer(text):
        yield Match("email", MEDIUM, m.start(), m.end(), m.group(0))


def _bank_accounts(text: str) -> Iterable[Match]:
    for m in _BANK_ACCOUNT.finditer(text):
        digits = _digits(m.group(1))
        if 9 <= len(digits) <= 18 and len(set(digits)) > 1:
            yield Match("bank_account", HIGH, m.start(1), m.end(1), m.group(1))


def _cards(text: str) -> Iterable[Match]:
    for m in _CARD.finditer(text):
        digits = _digits(m.group(0))
        if 13 <= len(digits) <= 19 and digits[0] in "23456" and luhn_valid(digits) and len(set(digits)) > 1:
            yield Match("payment_card", HIGH, m.start(), m.end(), m.group(0))


def _aadhaar(text: str) -> Iterable[Match]:
    for m in _AADHAAR.finditer(text):
        digits = _digits(m.group(0))
        if len(digits) == 12 and verhoeff_valid(digits) and len(set(digits)) > 1:
            yield Match("aadhaar", HIGH, m.start(), m.end(), m.group(0))


def _pan(text: str) -> Iterable[Match]:
    for m in _PAN.finditer(text):
        yield Match("pan", HIGH, m.start(), m.end(), m.group(0))


def _ifsc(text: str) -> Iterable[Match]:
    for m in _IFSC.finditer(text):
        yield Match("ifsc", MEDIUM, m.start(), m.end(), m.group(0))


def _phones(text: str) -> Iterable[Match]:
    for pattern in _PHONE_PATTERNS:
        for m in pattern.finditer(text):
            value = m.group(0).strip()
            digits = _digits(value)
            if not 10 <= len(digits) <= 15 or len(set(digits)) < 3:
                continue
            start = m.start() + (len(m.group(0)) - len(m.group(0).lstrip()))
            yield Match("phone", MEDIUM, start, start + len(value), value)


DETECTORS: list[Callable[[str], Iterable[Match]]] = [
    _secrets,
    _urls,
    _emails,
    _labelled_secrets,
    _bank_accounts,
    _cards,
    _aadhaar,
    _pan,
    _ifsc,
    _phones,
]


def detect(text: str) -> list[Match]:
    """Return non-overlapping matches ordered by position."""
    accepted: list[Match] = []
    for detector in DETECTORS:
        for match in detector(text):
            if match.end <= match.start:
                continue
            if any(match.start < a.end and a.start < match.end for a in accepted):
                continue
            accepted.append(match)
    return sorted(accepted, key=lambda m: m.start)


# --------------------------------------------------------------------------
# Masking
# --------------------------------------------------------------------------

def _mask_keep_last(value: str, keep: int = 4) -> str:
    """Star every alphanumeric character except the last ``keep`` ones."""
    alnum_positions = [i for i, ch in enumerate(value) if ch.isalnum()]
    visible = set(alnum_positions[-keep:]) if keep else set()
    return "".join(
        ch if (not ch.isalnum() or i in visible) else "*" for i, ch in enumerate(value)
    )


_SECRET_PREFIX = re.compile(r"^(?:AKIA|ASIA|gh[pousr]_|github_pat_|xox[abposr]-|(?:sk|rk|pk)_(?:live|test)_|AIza|sk-(?:proj-|ant-)?|eyJ)")


def mask_value(category: str, value: str) -> str:
    if category == "email":
        local, _, domain = value.partition("@")
        shown = local[:2] if len(local) > 2 else local[:1]
        return f"{shown}***@{domain}"
    if category == "url":
        try:
            parts = urlsplit(value if "://" in value else "http://" + value)
            prefix = f"{parts.scheme}://" if "://" in value else ""
            has_more = bool(parts.path.strip("/") or parts.query or parts.fragment)
            return f"{prefix}{parts.netloc}" + ("/****" if has_more else "")
        except ValueError:
            return value[:12] + "****"
    if category == "secret":
        if value.startswith("-----BEGIN"):
            return "-----BEGIN ... PRIVATE KEY----- (hidden)"
        # Show only a well-known type prefix (e.g. "ghp_"), never part of a
        # labelled password or other free-form secret.
        prefix = _SECRET_PREFIX.match(value)
        head = prefix.group(0) if prefix else ""
        return head + "*" * min(max(len(value) - len(head), 8), 16)
    if category == "ai":
        # AI suggestions are free text (names, addresses, passwords): show
        # only each word's first character, and nothing for single words.
        words = value.split()
        if len(words) == 1:
            return "*" * min(max(len(value), 6), 12)
        shown = " ".join(w[0] + "*" * min(max(len(w) - 1, 2), 8) for w in words[:6])
        return shown + (" …" if len(words) > 6 else "")
    if category in {"pan", "ifsc"}:
        return _mask_keep_last(value, 3)
    return _mask_keep_last(value, 4)


def normalise(value: str) -> str:
    """Comparison form used for verification: no whitespace, lowercase."""
    return re.sub(r"\s+", "", value).lower()
