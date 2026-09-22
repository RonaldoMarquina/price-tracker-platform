import os
from urllib.parse import quote

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

    def __init__(self, **values):
        super().__init__(**values)
        self._validate_and_assemble_database_url(values)

    def _validate_and_assemble_database_url(self, kwargs_values: dict) -> None:
        """Enforce strict precedence for database connection configuration.

        1. Explicit DATABASE_URL via constructor kwargs or OS environment takes priority.
        2. Discrete DB_* variables (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD) are used ONLY
           when no explicit DATABASE_URL is supplied (or when discrete DB_* are explicitly
           passed to constructor kwargs).
        3. Never rebuild with a partial set of variables: if discrete mode is triggered,
           all required parameters must be present, else raise a safe ValueError.
        4. When neither is explicitly provided, retain the default local DATABASE_URL.
        """
        discrete_fields = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]

        url_in_kwargs = (
            "DATABASE_URL" in kwargs_values and kwargs_values["DATABASE_URL"] is not None
        )
        if url_in_kwargs:
            return

        kwargs_has_db = any(k in kwargs_values for k in discrete_fields)
        url_in_env = "DATABASE_URL" in os.environ and bool(os.environ["DATABASE_URL"].strip())

        if url_in_env and not kwargs_has_db:
            return

        env_has_db = any(
            k in os.environ and bool(os.environ[k].strip()) for k in discrete_fields
        )
        has_discrete = kwargs_has_db or env_has_db

        if has_discrete:
            missing = [k for k in discrete_fields if not getattr(self, k)]
            if missing:
                missing_str = ", ".join(sorted(missing))
                raise ValueError(
                    "Incomplete database configuration: missing discrete parameters: "
                    f"{missing_str}. Provide either a full DATABASE_URL or all discrete "
                    "variables (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD)."
                )
            encoded_user = quote(self.DB_USER, safe="")
            encoded_pwd = quote(self.DB_PASSWORD, safe="")
            port = self.DB_PORT or 5432
            auth = f"{encoded_user}:{encoded_pwd}@"
            self.DATABASE_URL = f"postgresql://{auth}{self.DB_HOST}:{port}/{self.DB_NAME}"


settings = Settings()
