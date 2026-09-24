import pytest


@pytest.fixture(autouse=True)
def disable_external_apis_in_tests(monkeypatch):
    """Ensure automated tests run hermetically without hitting live external APIs.

    Real API credentials remain intact in .env for REPL and live application usage.
    """
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
