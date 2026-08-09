import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_default_settings():
    settings = Settings(_env_file=None)

    assert settings.PROJECT_NAME == "AI Recruitment Platform"
    assert settings.VERSION == "1.0.0"
    assert settings.ENVIRONMENT == "development"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.API_V1_STR == "/api/v1"
    assert settings.BACKEND_CORS_ORIGINS == [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    assert settings.SECRET_KEY == "change-me-in-development-with-a-random-value"


def test_environment_variable_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PROJECT_NAME", "Custom Name")
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("API_V1_STR", "/custom/v1")
    monkeypatch.setenv("SECRET_KEY", "custom-secret")

    settings = Settings(_env_file=None)

    assert settings.PROJECT_NAME == "Custom Name"
    assert settings.ENVIRONMENT == "staging"
    assert settings.LOG_LEVEL == "WARNING"
    assert settings.API_V1_STR == "/custom/v1"
    assert settings.SECRET_KEY == "custom-secret"


@pytest.mark.parametrize("environment", ["development", "staging", "production", "testing"])
def test_valid_environments(monkeypatch: pytest.MonkeyPatch, environment: str):
    monkeypatch.setenv("ENVIRONMENT", environment)
    if environment == "production":
        monkeypatch.setenv("SECRET_KEY", "test-production-secret-123")

    settings = Settings(_env_file=None)

    assert settings.ENVIRONMENT == environment


def test_invalid_environment_raises_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "invalid")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_accepts_json_array_string(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS", '["http://localhost:5173","https://example.com"]'
    )

    settings = Settings(_env_file=None)

    assert settings.BACKEND_CORS_ORIGINS == [
        "http://localhost:5173",
        "https://example.com",
    ]


def test_cors_accepts_comma_separated_string(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS", "http://localhost:5173, https://example.com"
    )

    settings = Settings(_env_file=None)

    assert settings.BACKEND_CORS_ORIGINS == [
        "http://localhost:5173",
        "https://example.com",
    ]


def test_invalid_cors_origin_raises_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "localhost:5173")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_default_secret_raises_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "change-me-in-development-with-a-random-value")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_accepts_custom_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "test-production-secret-123")

    settings = Settings(_env_file=None)

    assert settings.ENVIRONMENT == "production"
    assert settings.SECRET_KEY == "test-production-secret-123"