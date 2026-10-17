import pytest

from app.services.detection import CATEGORIES, detect, mask_value
from tests import synthetic as s


def categories(text: str) -> list[str]:
    return [m.category for m in detect(text)]


def values(text: str, category: str) -> list[str]:
    return [m.value for m in detect(text) if m.category == category]


def test_email_detected_and_masked():
    matches = detect(f"Write to {s.EMAIL} today.")
    assert [m.category for m in matches] == ["email"]
    assert matches[0].value == s.EMAIL
    assert mask_value("email", s.EMAIL) == "ja***@example.com"


@pytest.mark.parametrize(
    "phone",
    ["+91 98765 43210", "+91-9876543210", "9876543210", "09876543210", "022-2345 6789", "+1 415 555 0134", "(415) 555-0134"],
)
def test_phone_formats(phone):
    assert values(f"Call me on {phone} please", "phone") == [phone]


def test_phone_masked_keeps_last_four():
    assert mask_value("phone", "9876543210") == "******3210"


def test_aadhaar_like_requires_valid_checksum_and_is_cautious():
    valid = s.aadhaar_like()
    assert values(f"ID {valid}", "aadhaar") == [valid]
    assert CATEGORIES["aadhaar"].label.startswith("Possible")
    assert "not a verified identity" in CATEGORIES["aadhaar"].explanation

    digits = valid.replace(" ", "")
    wrong = digits[:-1] + str((int(digits[-1]) + 1) % 10)
    assert "aadhaar" not in categories(f"ID {wrong}")


def test_pan_like_is_labelled_possible():
    assert values(f"PAN: {s.PAN}", "pan") == [s.PAN]
    assert CATEGORIES["pan"].label == "Possible PAN"
    # lowercase or wrong shape is not PAN
    assert "pan" not in categories("abcpe1234f ABCPE12345")


def test_bank_account_needs_context():
    assert values(f"Account No: {s.ACCOUNT}", "bank_account") == [s.ACCOUNT]
    assert values(f"A/c no. {s.ACCOUNT}", "bank_account") == [s.ACCOUNT]
    # The same digits without an account label are not flagged as an account.
    assert "bank_account" not in categories(f"Order reference {s.ACCOUNT}")


def test_ifsc_and_card():
    assert values(f"IFSC {s.IFSC}", "ifsc") == [s.IFSC]
    assert values(f"Card {s.TEST_CARD}", "payment_card") == [s.TEST_CARD]
    assert "payment_card" not in categories("Card 4111 1111 1111 1112")  # fails Luhn


def test_secrets():
    assert values(f"token {s.GITHUB_TOKEN}", "secret") == [s.GITHUB_TOKEN]
    assert values(f"aws {s.AWS_KEY}", "secret") == [s.AWS_KEY]
    assert values("password: Hunter2-Example", "secret") == ["Hunter2-Example"]
    assert values("api_key = abcd1234efgh5678", "secret") == ["abcd1234efgh5678"]
    key = "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAKj34\n-----END RSA PRIVATE KEY-----"
    assert values(f"key:\n{key}", "secret") == [key]
    assert mask_value("secret", s.GITHUB_TOKEN).startswith("ghp_")
    assert s.GITHUB_TOKEN[6:] not in mask_value("secret", s.GITHUB_TOKEN)
    # Free-form secrets reveal no characters at all.
    assert set(mask_value("secret", "Hunter2-Example")) == {"*"}


def test_password_prose_not_flagged():
    for text in ["Your password must be changed.", "Click password reset to continue.", "The token is valid."]:
        assert "secret" not in categories(text), text


def test_url_risk_levels():
    [plain] = [m for m in detect("See https://example.com/about.") if m.category == "url"]
    assert plain.value == "https://example.com/about" and plain.risk == "low"
    [tok] = [m for m in detect("https://files.example.com/d?id=7&token=abc123") if m.category == "url"]
    assert tok.risk == "high"
    assert mask_value("url", tok.value) == "https://files.example.com/****"


def test_email_inside_url_reported_once():
    found = detect("https://example.com/invite?email=jane.doe@example.com")
    assert [m.category for m in found] == ["url"]


def test_normal_text_has_no_false_positives():
    text = (
        "The quarterly meeting is on 12 March 2024 at 10:30 in room 204. "
        "We shipped 1500 units for a total of 45,000 rupees, invoice 2024-001. "
        "Version 3.11.4 was released in 2023 and supports 64-bit Windows. "
        "Chapter 7 covers pages 120 to 168. The password policy is described below."
    )
    assert detect(text) == []


def test_matches_do_not_overlap():
    text = f"Account No: {s.ACCOUNT} phone 9876543210 card {s.TEST_CARD}"
    found = detect(text)
    for a, b in zip(found, found[1:]):
        assert a.end <= b.start
