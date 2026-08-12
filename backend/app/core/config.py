import json
from typing import Annotated
from urllib.parse import quote_plus

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
    def validate_cors_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"Invalid CORS origin, must be an HTTP(S) URL: {origin!r}")
        return value

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
        return value

    @field_validator("DATABASE_PORT")
    @classmethod
    def validate_database_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("DATABASE_PORT must be in range 1-65535")
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
            f"?driver={driver_param}&TrustServerCertificate=yes"
        )


settings = Settings()