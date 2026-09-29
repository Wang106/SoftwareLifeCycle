from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://slc:slc_dev_password@localhost:5432/software_lifecycle"
    cors_origins: str = "http://localhost:3000,https://softwarelifecycle.whf969.com"
    required_db_revision: str = "0010_append_only_audit_events"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

settings = Settings()
