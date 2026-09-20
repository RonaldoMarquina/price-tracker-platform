"""Worker configuration settings loaded from environment."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Configuration for scraping worker process."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/price_tracker"
    QUEUE_NAME: str = "scraping-jobs"
    DLQ_NAME: str = "scraping-jobs-dlq"
    MAX_RETRIES: int = 3
    VISIBILITY_TIMEOUT: int = 30
    POLL_INTERVAL_SECONDS: float = 1.0
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"


worker_settings = WorkerSettings()
