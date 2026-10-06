from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://slc:slc_dev_password@localhost:5432/software_lifecycle"
    cors_origins: str = "http://localhost:3000,https://softwarelifecycle.whf969.com"
    required_db_revision: str = "0020_global_role_status"
    read_only_mode: bool = False
    auth_mode: Literal["disabled", "oidc"] = "disabled"
    admin_operator_enabled: bool = False
    oidc_issuer_url: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_algorithms: str = "RS256"
    oidc_leeway_seconds: int = Field(default=30, ge=0, le=300)
    oidc_jwks_timeout_seconds: int = Field(default=5, ge=1, le=30)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def use_installed_postgres_driver(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://"):]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://"):]
        return value

    @model_validator(mode="after")
    def validate_oidc_configuration(self):
        if self.auth_mode == "disabled":
            return self
        required = {
            "OIDC_ISSUER_URL": self.oidc_issuer_url,
            "OIDC_AUDIENCE": self.oidc_audience,
            "OIDC_JWKS_URL": self.oidc_jwks_url,
        }
        missing = [name for name, value in required.items() if not value or not value.strip()]
        if missing:
            raise ValueError(f"OIDC mode requires {', '.join(missing)}")
        for name, value in (
            ("OIDC_ISSUER_URL", self.oidc_issuer_url),
            ("OIDC_JWKS_URL", self.oidc_jwks_url),
        ):
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(f"{name} must be an HTTPS URL without credentials, query or fragment")
        allowed = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"}
        algorithms = self.oidc_algorithm_list
        if not algorithms or not set(algorithms) <= allowed:
            raise ValueError("OIDC_ALGORITHMS must contain only approved asymmetric algorithms")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def oidc_algorithm_list(self) -> list[str]:
        return [item.strip() for item in self.oidc_algorithms.split(",") if item.strip()]

settings = Settings()
