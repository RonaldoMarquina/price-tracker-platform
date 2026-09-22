"""Worker configuration settings loaded from environment."""

from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Configuration for scraping worker process."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
    QUEUE_NAME: str = "scraping-jobs"
    DLQ_NAME: str = "scraping-jobs-dlq"
    MAX_RETRIES: int = 3
    VISIBILITY_TIMEOUT: int = 30
    POLL_INTERVAL_SECONDS: float = 1.0
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def assemble_database_url(self) -> "WorkerSettings":
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


worker_settings = WorkerSettings()
