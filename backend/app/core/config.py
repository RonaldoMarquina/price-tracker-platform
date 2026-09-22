"""Core configuration and settings."""

from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    API_PORT: int = 8000
    API_HOST: str = "0.0.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    DOCS_ENABLED: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    INTERNAL_API_KEY: str = "dev-internal-secret-token"

    # Discrete database connection parameters for secure ECS container runtime
    DB_HOST: str | None = None
    DB_PORT: int = 5432
    DB_NAME: str | None = None
    DB_USER: str | None = None
    DB_PASSWORD: str | None = None
    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int | None = None
    POSTGRES_DB: str | None = None
    POSTGRES_USER: str | None = None

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/price_tracker"

    @model_validator(mode="after")
    def assemble_database_url(self) -> "Settings":
        """Assemble DATABASE_URL dynamically if discrete parameters are provided."""
        host = self.DB_HOST or self.POSTGRES_HOST
        port = self.DB_PORT if self.DB_PORT != 5432 else (self.POSTGRES_PORT or 5432)
        name = self.DB_NAME or self.POSTGRES_DB
        user = self.DB_USER or self.POSTGRES_USER
        password = self.DB_PASSWORD

        if host and name:
            auth = ""
            if user:
                encoded_user = quote(user, safe="")
                if password:
                    encoded_pwd = quote(password, safe="")
                    auth = f"{encoded_user}:{encoded_pwd}@"
                else:
                    auth = f"{encoded_user}@"
            self.DATABASE_URL = f"postgresql://{auth}{host}:{port}/{name}"
        return self


settings = Settings()
