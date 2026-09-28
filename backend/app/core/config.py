from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://slc:slc_dev_password@localhost:5432/software_lifecycle"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
