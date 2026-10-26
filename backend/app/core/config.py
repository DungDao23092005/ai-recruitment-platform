import json
import re
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
    GEMINI_GENERATION_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_PRICING_TIER: str = "paid_standard"
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

    # Explainable AI match-explanation cache
    MATCH_EXPLANATION_CACHE_ENABLED: bool = True
    MATCH_EXPLANATION_CACHE_TTL_SECONDS: int = 604800
    MATCH_EXPLANATION_CACHE_VERSION: str = "v1"

    # Quota-controlled refresh coordination
    MATCH_EXPLANATION_LOCK_TTL_SECONDS: int = 120
    MATCH_EXPLANATION_IDEMPOTENCY_TTL_SECONDS: int = 86400
    MATCH_EXPLANATION_IN_PROGRESS_TTL_SECONDS: int = 120
    MATCH_EXPLANATION_IDEMPOTENCY_SCHEMA_VERSION: str = "v1"

    # Rate Limiting Configuration
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN_IP_PER_MINUTE: int = 20
    RATE_LIMIT_LOGIN_EMAIL_PER_MINUTE: int = 5
    RATE_LIMIT_REGISTER_IP_PER_MINUTE: int = 10
    RATE_LIMIT_FORGOT_PASSWORD_IP_PER_MINUTE: int = 5
    RATE_LIMIT_FORGOT_PASSWORD_EMAIL_PER_MINUTE: int = 3
    RATE_LIMIT_VERIFY_OTP_IP_PER_MINUTE: int = 10
    RATE_LIMIT_VERIFY_OTP_EMAIL_PER_MINUTE: int = 5
    RATE_LIMIT_RESET_PASSWORD_IP_PER_MINUTE: int = 10
    RATE_LIMIT_RESET_PASSWORD_EMAIL_PER_MINUTE: int = 5
    RATE_LIMIT_AI_CHAT_PER_MINUTE: int = 10
    RATE_LIMIT_PARSE_RESUME_PER_MINUTE: int = 5
    RATE_LIMIT_PARSE_JD_PER_MINUTE: int = 5
    RATE_LIMIT_MATCH_PER_MINUTE: int = 10
    RATE_LIMIT_RECOMMENDATIONS_PER_MINUTE: int = 10
    RATE_LIMIT_EXPLANATION_REFRESH_PER_MINUTE: int = 30

    # Trusted Proxies for safe client IP extraction
    TRUSTED_PROXIES: Annotated[list[str], NoDecode] = []

    # Request body hardening. Every non-upload request is capped at 1 MiB; the
    # CV upload route gets a slightly larger envelope so a 10 MiB PDF plus
    # multipart framing fits. Deadlines bound how long a client may take to
    # deliver a body, on top of the per-request size limit.
    MAX_REQUEST_BODY_BYTES: int = 1 * 1024 * 1024
    MAX_RESUME_REQUEST_BYTES: int = 11 * 1024 * 1024
    UPLOAD_MAX_ACTIVE: int = 4
    UPLOAD_MAX_WAITING: int = 8
    UPLOAD_QUEUE_TIMEOUT_SECONDS: float = 5.0
    UPLOAD_CHUNK_TIMEOUT_SECONDS: float = 15.0
    UPLOAD_TOTAL_TIMEOUT_SECONDS: float = 120.0

    # Isolated PDF extraction. The PDF parser runs in a spawned child process so
    # a malformed document cannot exhaust the API process.
    PDF_ISOLATION_ENABLED: bool = True
    PDF_WORKER_MAX_CONCURRENCY: int = 2
    PDF_WORKER_TIMEOUT_SECONDS: float = 30.0
    PDF_WORKER_TERMINATE_GRACE_SECONDS: float = 2.0
    PDF_WORKER_MAX_CONSECUTIVE_FAILURES: int = 3
    PDF_WORKER_QUARANTINE_SECONDS: float = 60.0

    # Recruitment analytics rollup and retention.
    ANALYTICS_ROLLUP_ENABLED: bool = True
    ANALYTICS_ROLLUP_INTERVAL_SECONDS: float = 300.0
    ANALYTICS_ROLLUP_LOOKBACK_DAYS: int = 30
    ANALYTICS_RAW_RETENTION_DAYS: int = 90
    ANALYTICS_UNIQUE_VIEW_TTL_SECONDS: int = 93600

    # VNPAY Configuration
    VNPAY_TMN_CODE: str = ""
    VNPAY_HASH_SECRET: str = ""
    VNPAY_PAYMENT_URL: str = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
    VNPAY_QUERY_URL: str = "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
    VNPAY_RETURN_URL: str = ""
    VNPAY_IPN_URL: str = ""
    VNPAY_TIMEOUT: int = 15

    EMAIL_PROVIDER: str = "mailpit"
    EMAIL_FROM: str = "AI Recruitment Platform <noreply@example.com>"
    RESEND_API_KEY: str = ""
    MAILPIT_HOST: str = "mailpit"
    MAILPIT_PORT: int = 1025
    GMAIL_USERNAME: str = ""
    GMAIL_APP_PASSWORD: str = ""
    GMAIL_HOST: str = "smtp.gmail.com"
    GMAIL_PORT: int = 587

    # Transactional outbox worker (durable notification email delivery).
    EMAIL_OUTBOX_ENABLED: bool = True
    EMAIL_OUTBOX_POLL_INTERVAL_SECONDS: float = 30.0
    EMAIL_OUTBOX_BATCH_SIZE: int = 20
    EMAIL_OUTBOX_LEASE_SECONDS: int = 300
    EMAIL_OUTBOX_MAX_ATTEMPTS: int = 3
    EMAIL_OUTBOX_RETRY_BASE_SECONDS: float = 2.0
    EMAIL_OUTBOX_RETRY_MAX_SECONDS: float = 300.0
    EMAIL_OUTBOX_SENT_RETENTION_DAYS: int = 30

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

    @field_validator("GEMINI_PRICING_TIER")
    @classmethod
    def validate_gemini_pricing_tier(cls, value: str) -> str:
        if value not in {
            "free_tier",
            "paid_standard",
            "paid_context_cache",
        }:
            raise ValueError(
                "GEMINI_PRICING_TIER must be one of free_tier, "
                "paid_standard or paid_context_cache"
            )
        return value

    @field_validator("RATE_LIMIT_EXPLANATION_REFRESH_PER_MINUTE")
    @classmethod
    def validate_explanation_refresh_rate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "RATE_LIMIT_EXPLANATION_REFRESH_PER_MINUTE must be greater "
                "than 0"
            )
        return value

    @field_validator(
        "RATE_LIMIT_RESET_PASSWORD_IP_PER_MINUTE",
        "RATE_LIMIT_RESET_PASSWORD_EMAIL_PER_MINUTE",
    )
    @classmethod
    def validate_reset_password_rate_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "Reset-password rate limit settings must be greater than 0"
            )
        return value

    @field_validator("MATCH_EXPLANATION_CACHE_TTL_SECONDS")
    @classmethod
    def validate_match_explanation_cache_ttl(cls, value: int) -> int:
        # Redis treats a non-positive TTL as invalid/indefinite depending on the
        # command. Reject it at startup so a bad config cannot create keys that
        # never expire.
        if value <= 0:
            raise ValueError(
                "MATCH_EXPLANATION_CACHE_TTL_SECONDS must be greater than 0"
            )
        return value

    @field_validator("MATCH_EXPLANATION_CACHE_VERSION")
    @classmethod
    def validate_match_explanation_cache_version(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value or ""):
            raise ValueError(
                "MATCH_EXPLANATION_CACHE_VERSION must be 1-64 characters of "
                "letters, digits, '.', '_' or '-'"
            )
        return value

    @field_validator(
        "MATCH_EXPLANATION_LOCK_TTL_SECONDS",
        "MATCH_EXPLANATION_IDEMPOTENCY_TTL_SECONDS",
        "MATCH_EXPLANATION_IN_PROGRESS_TTL_SECONDS",
    )
    @classmethod
    def validate_match_explanation_refresh_ttls(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "Match explanation refresh TTL settings must be greater than 0"
            )
        return value

    @field_validator("MATCH_EXPLANATION_IDEMPOTENCY_SCHEMA_VERSION")
    @classmethod
    def validate_match_explanation_idempotency_schema_version(
        cls, value: str
    ) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,20}", value or ""):
            raise ValueError(
                "MATCH_EXPLANATION_IDEMPOTENCY_SCHEMA_VERSION must be 1-20 "
                "characters of letters, digits, '.', '_' or '-'"
            )
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