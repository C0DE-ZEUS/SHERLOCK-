import os
import tempfile
from pathlib import Path

# Isolate test artifacts before the app (and its settings) are imported.
os.environ["SHERLOCK_TEMP_DIR"] = str(Path(tempfile.mkdtemp(prefix="sherlock-tests-")))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import text_extraction  # noqa: E402
from app.services.ai import providers  # noqa: E402
from app.services.limits import rate_limiter  # noqa: E402
from app.services.sessions import store  # noqa: E402


@pytest.fixture()
def client():
    rate_limiter.reset()
    with TestClient(app) as c:
        yield c
    store.clear()


@pytest.fixture()
def no_ocr(monkeypatch):
    monkeypatch.setattr(text_extraction, "ocr_status", lambda: (False, text_extraction.OCR_SETUP_MESSAGE))


@pytest.fixture()
def fake_ocr(monkeypatch):
    """Replace Tesseract with a stub returning the words a test supplies.

    Tesseract is an external program that may not be installed where tests
    run; the stub lets us test everything Sherlock does with OCR boxes.
    """
    holder: dict = {"words": []}
    monkeypatch.setattr(text_extraction, "ocr_status", lambda: (True, "stub OCR"))
    monkeypatch.setattr(text_extraction, "ocr_words", lambda image: list(holder["words"]))
    return holder


class FakeProvider:
    """Stands in for Ollama. ``reply`` is a string, an exception, or a
    function of the user prompt returning either."""

    name = "fake"
    model = "fake-model"

    def __init__(self, reply="{\"findings\": []}", available=True):
        self.reply = reply
        self.available = available
        self.calls: list[str] = []

    def status(self):
        return providers.AIStatus(self.available, "fake", self.model, "localhost", True,
                                  "ready" if self.available else "Fake AI is offline.")

    def complete_json(self, system, user, schema):
        self.calls.append(user)
        reply = self.reply(user) if callable(self.reply) else self.reply
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture(autouse=True)
def hermetic_ai():
    """Never call a real model from the test suite."""
    providers.set_provider(providers.DisabledProvider())
    yield
    providers.set_provider(None)


@pytest.fixture()
def fake_ai():
    def install(reply="{\"findings\": []}", available=True):
        provider = FakeProvider(reply, available)
        providers.set_provider(provider)
        return provider
    return install
