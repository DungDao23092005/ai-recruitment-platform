import json
from typing import Annotated, Optional
from urllib.parse import quote_plus, urlparse

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

VALID_ENVIRONMENTS = ("development", "staging", "production", "testing")


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Recruitment Platform"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    API_V1_STR: str = "/api/v1"

    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    SECRET_KEY: str = "change-me-in-development-with-a-random-value"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    DATABASE_DRIVER: str = "ODBC Driver 18 for SQL Server"
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 1433
    DATABASE_NAME: str = "ai_recruitment_platform"
    DATABASE_USER: str = ""
    DATABASE_PASSWORD: str = ""

    # AI & Vector Database Configuration
    GEMINI_API_KEY: str = ""
    GEMINI_GENERATION_MODEL: str = "gemini-3.5-flash"
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    VECTOR_DIMENSION: int = 384
    CROSS_ENCODER_MODEL_NAME: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    FINAL_SCORE_THRESHOLD: float = 0.3

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # Rate Limiting Configuration
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN_IP_PER_MINUTE: int = 20
    RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE: int = 5
    RATE_LIMIT_REGISTER_IP_PER_MINUTE: int = 10
    RATE_LIMIT_FORGOT_PASSWORD_IP_PER_MINUTE: int = 5
    RATE_LIMIT_FORGOT_PASSWORD_EMAIL_PER_MINUTE: int = 3
    RATE_LIMIT_VERIFY_OTP_IP_PER_MINUTE: int = 10
    RATE_LIMIT_AI_CHAT_PER_MINUTE: int = 10
    RATE_LIMIT_PARSE_RESUME_PER_MINUTE: int = 5
    RATE_LIMIT_PARSE_JD_PER_MINUTE: int = 5
    RATE_LIMIT_MATCH_PER_MINUTE: int = 10
    RATE_LIMIT_RECOMMENDATIONS_PER_MINUTE: int = 10

    # Trusted Proxies for safe client IP extraction
    TRUSTED_PROXIES: Annotated[list[str], NoDecode] = []

    EMAIL_PROVIDER: str = "mailpit"
    EMAIL_FROM: str = "AI Recruitment Platform <noreply@example.com>"
    RESEND_API_KEY: str = ""
    MAILPIT_HOST: str = "mailpit"
    MAILPIT_PORT: int = 1025
    GMAIL_USERNAME: str = ""
    GMAIL_APP_PASSWORD: str = ""
    GMAIL_HOST: str = "smtp.gmail.com"
    GMAIL_PORT: int = 587

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        if value not in VALID_ENVIRONMENTS:
            raise ValueError(
                f"ENVIRONMENT must be one of {', '.join(VALID_ENVIRONMENTS)}, got: {value!r}"
            )
        return value

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except json.JSONDecodeError:
                pass
            return [
                origin.strip()
                for origin in value.split(",")
                if origin.strip()
            ]
        if isinstance(value, list):
            return value
        raise ValueError(f"Invalid BACKEND_CORS_ORIGINS value: {value!r}")

    @field_validator("BACKEND_CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, value: list[str], info: ValidationInfo) -> list[str]:
        for origin in value:
            # Handle wildcard first
            if origin == "*":
                env = info.data.get("ENVIRONMENT", "development") if info.data else "development"
                if env == "production":
                    raise ValueError("Unsafe CORS origin '*' not allowed in production")
                continue

            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"Invalid CORS origin, must be an HTTP(S) URL: {origin!r}")

        # Production CORS hardening
        env = info.data.get("ENVIRONMENT", "development") if info.data else "development"
        if env == "production":
            cls._validate_production_cors_origins(value)
        return value

    @classmethod
    def _validate_production_cors_origins(cls, origins: list[str]) -> None:
        """Validate CORS origins for production environment."""
        for origin in origins:
            # Parse URL to check host
            try:
                parsed = urlparse(origin)
                host = parsed.hostname or ""
                port = parsed.port

                # Check for localhost/loopback
                if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                    raise ValueError(
                        f"Development origin '{origin}' not allowed in production"
                    )
            except Exception as e:
                if "not allowed in production" in str(e):
                    raise
                raise ValueError(f"Invalid CORS origin format: {origin!r}")

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: str, info: ValidationInfo) -> str:
        env = info.data.get("ENVIRONMENT", "development") if info.data else "development"
        if env == "production":
            placeholder = "change-me-in-development-with-a-random-value"
            if not value or value == placeholder:
                raise ValueError(
                    "SECRET_KEY must be a custom non-empty secret in production"
                )
            # Minimum 32 bytes UTF-8 encoded length
            if len(value.encode("utf-8")) < 32:
                raise ValueError(
                    "SECRET_KEY must be at least 32 bytes (UTF-8) in production"
                )
        return value

    @field_validator("DATABASE_PASSWORD")
    @classmethod
    def validate_database_password(cls, value: str, info: ValidationInfo) -> str:
        env = info.data.get("ENVIRONMENT", "development") if info.data else "development"
        if env == "production":
            if not value or not value.strip():
                raise ValueError("DATABASE_PASSWORD is required in production")
        return value

    @field_validator("GEMINI_API_KEY")
    @classmethod
    def validate_gemini_api_key(cls, value: str, info: ValidationInfo) -> str:
        env = info.data.get("ENVIRONMENT", "development") if info.data else "development"
        if env == "production":
            if not value or not value.strip():
                raise ValueError("GEMINI_API_KEY is required in production")
        return value

    @property
    def database_uri(self) -> str:
        credentials = ""
        if self.DATABASE_USER:
            credentials = (
                f"{quote_plus(self.DATABASE_USER)}:{quote_plus(self.DATABASE_PASSWORD)}@"
            )
        driver_param = quote_plus(self.DATABASE_DRIVER)
        return (
            f"mssql+aioodbc://"
            f"{credentials}{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
            f"?driver={driver_param}&TrustServerCertificate=yes&ConnectRetryCount=3&ConnectRetryInterval=10"
        )


settings = Settings()