import pytest

from app import config


def test_missing_key_gives_a_plain_error(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        config.load_api_key()


def test_placeholder_key_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your-key-here")
    with pytest.raises(RuntimeError):
        config.load_api_key()


def test_real_looking_key_is_returned(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  test-value  ")
    assert config.load_api_key() == "test-value"
