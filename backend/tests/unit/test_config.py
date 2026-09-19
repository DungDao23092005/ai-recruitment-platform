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
        monkeypatch.setenv("SECRET_KEY", "test-production-secret-12345678901234567890")
        monkeypatch.setenv("DATABASE_PASSWORD", "test-password-123")
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com,https://api.example.com")

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
    monkeypatch.setenv("SECRET_KEY", "test-production-secret-12345678901234567890")
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password-123")
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com,https://api.example.com")

    settings = Settings(_env_file=None)

    assert settings.ENVIRONMENT == "production"
    assert settings.SECRET_KEY == "test-production-secret-12345678901234567890"


def test_database_uri_uses_aioodbc_scheme():
    settings = Settings(_env_file=None)

    assert settings.database_uri.startswith("mssql+aioodbc://")


def test_database_uri_includes_odbc_driver_params():
    settings = Settings(_env_file=None)

    assert "driver=ODBC+Driver+18+for+SQL+Server" in settings.database_uri
    assert "TrustServerCertificate=yes" in settings.database_uri


def test_database_uri_urlencodes_credentials():
    settings = Settings(
        _env_file=None,
        DATABASE_USER="sa",
        DATABASE_PASSWORD="P@ss w0rd!/+",
    )

    assert "sa:P%40ss+w0rd%21%2F%2B@" in settings.database_uri


# === SECRET_KEY validation tests ===


def test_production_secret_key_min_32_bytes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    # 31 bytes - should fail
    monkeypatch.setenv("SECRET_KEY", "a" * 31)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_secret_key_exactly_32_bytes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com")

    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "a" * 32


def test_production_secret_key_over_32_bytes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "a" * 33)
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com")

    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "a" * 33


def test_production_secret_key_placeholder_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "change-me-in-development-with-a-random-value")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_development_short_secret_key_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SECRET_KEY", "short")

    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "short"


# === DATABASE_PASSWORD validation tests ===


def test_production_database_password_empty_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_PASSWORD", "")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "DATABASE_PASSWORD is required in production" in str(exc_info.value)


def test_production_database_password_whitespace_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_PASSWORD", "   ")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "DATABASE_PASSWORD is required in production" in str(exc_info.value)


def test_production_database_password_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_PASSWORD", "secure-password-123")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com")

    settings = Settings(_env_file=None)
    assert settings.DATABASE_PASSWORD == "secure-password-123"


def test_development_empty_database_password_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_PASSWORD", "")

    settings = Settings(_env_file=None)
    assert settings.DATABASE_PASSWORD == ""


# === GEMINI_API_KEY validation tests ===


def test_production_gemini_api_key_empty_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "GEMINI_API_KEY is required in production" in str(exc_info.value)


def test_production_gemini_api_key_whitespace_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "GEMINI_API_KEY is required in production" in str(exc_info.value)


def test_production_gemini_api_key_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GEMINI_API_KEY", "valid-api-key-123")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com")

    settings = Settings(_env_file=None)
    assert settings.GEMINI_API_KEY == "valid-api-key-123"


def test_development_empty_gemini_api_key_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    settings = Settings(_env_file=None)
    assert settings.GEMINI_API_KEY == ""


# === CORS validation tests ===


def test_production_cors_wildcard_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "*")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "Unsafe CORS origin '*' not allowed in production" in str(exc_info.value)


def test_production_cors_localhost_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "Development origin 'http://localhost:5173' not allowed in production" in str(
        exc_info.value
    )


def test_production_cors_localhost_with_port_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "Development origin 'http://localhost:3000' not allowed in production" in str(
        exc_info.value
    )


def test_production_cors_localhost_ip_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://127.0.0.1:3000")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "Development origin 'http://127.0.0.1:3000' not allowed in production" in str(
        exc_info.value
    )


def test_production_cors_legitimate_https_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://app.example.com,https://api.example.com")
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    settings = Settings(_env_file=None)
    assert settings.BACKEND_CORS_ORIGINS == [
        "https://app.example.com",
        "https://api.example.com",
    ]


def test_development_localhost_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:3000")

    settings = Settings(_env_file=None)
    assert settings.BACKEND_CORS_ORIGINS == [
        "http://localhost:5173",
        "http://127.0.0.1:3000",
    ]


def test_production_cors_localhost_ipv6_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://[::1]:3000")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "Development origin 'http://[::1]:3000' not allowed in production" in str(
        exc_info.value
    )


def test_production_cors_localhost_ipv4_zero_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://0.0.0.0:3000")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "Development origin 'http://0.0.0.0:3000' not allowed in production" in str(
        exc_info.value
    )