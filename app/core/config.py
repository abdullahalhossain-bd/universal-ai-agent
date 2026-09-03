"""
Application configuration.

Centralized settings for:
- FastAPI application
- PostgreSQL
- Redis
- API key generation
- Groq LLM provider pool
- Groq usage/cost calculation
"""

from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ---------------------------------
    # Application
    # ---------------------------------

    app_name: str = "Universal AI Agent"
    app_env: str = "development"
    environment: str = "development"

    # ---------------------------------
    # Persistence
    # ---------------------------------

    database_url: str

    # ---------------------------------
    # Credential encryption
    # ---------------------------------
    credential_encryption_key: str

    redis_url: str = "redis://localhost:6379/0"

    # ---------------------------------
    # API
    # ---------------------------------
    api_v1_prefix: str = "/api/v1"
    api_key_prefix: str = "pk_live_"

    # ---------------------------------
    # Groq
    # ---------------------------------
    groq_model: str = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_input_cost_per_1m: float = 0.075
    groq_output_cost_per_1m: float = 0.30

    # ---------------------------------
    # Groq vision (image chat)
    # ---------------------------------
    groq_vision_model: str = "qwen/qwen3.6-27b"
    groq_vision_input_cost_per_1m: float = 0.20
    groq_vision_output_cost_per_1m: float = 0.60
    vision_image_token_estimate: int = 1200

    # ---------------------------------
    # HTTP / networking
    # ---------------------------------
    trusted_proxies: str = ""
    crawler_max_page_bytes: int = 2_000_000
    crawler_max_pages: int = 50
    crawler_timeout_seconds: float = 15.0
    reservation_ttl_seconds: int = 300

    # Create missing tables on startup. Keep true for development;
    # production must use Alembic migrations exclusively.
    auto_create_tables: bool = True

    # ---------------------------------
    # Image chat / vision
    # ---------------------------------
    image_storage_path: str = "./data/chat-images"
    storage_backend: str = "local"
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_public_base_url: str | None = None
    vision_cache_ttl_seconds: int = 86400
    vision_max_matched_products: int = 5

    # The widget is intentionally embeddable on arbitrary merchant
    # domains. Authentication is via x-api-key (not cookies), and the
    # application sets allow_credentials=False, so wildcard CORS is
    # compatible with the widget. Deployments may still restrict this
    # to a comma-separated allow-list when desired.
    cors_allow_origins: str = "*"

    # ---------------------------------
    # Observability
    # ---------------------------------
    log_json: bool = True
    alert_webhook_url: str | None = None

    # ---------------------------------
    # Groq API key pool
    # ---------------------------------
    groq_api_key_1: str | None = None
    groq_api_key_2: str | None = None
    groq_api_key_3: str | None = None
    groq_api_key_4: str | None = None
    groq_api_key_5: str | None = None
    groq_api_key_6: str | None = None
    groq_api_key_7: str | None = None
    groq_api_key_8: str | None = None
    groq_api_key_9: str | None = None
    groq_api_key_10: str | None = None
    groq_api_key_11: str | None = None
    groq_api_key_12: str | None = None
    groq_api_key_13: str | None = None
    groq_api_key_14: str | None = None

    # ---------------------------------
    # Dashboard auth
    # ---------------------------------
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60 * 24 * 7
    admin_jwt_access_token_minutes: int = 60 * 8
    frontend_url: str = "http://localhost:5173"

    # ---------------------------------
    # Billing (Stripe)
    # ---------------------------------
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_starter: str | None = None
    stripe_price_growth: str | None = None
    stripe_price_pro: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator(
        "database_url",
        "redis_url",
        "groq_base_url",
        "trusted_proxies",
        "cors_allow_origins",
        mode="before",
    )
    @classmethod
    def _strip_whitespace(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _validate_production_settings(self):
        environments = {
            (self.environment or "").lower().strip(),
            (self.app_env or "").lower().strip(),
        }
        if not environments.intersection({"production", "prod"}):
            return self

        if self.jwt_secret_key == "dev-only-insecure-secret-change-me":
            raise ValueError(
                "JWT_SECRET_KEY must be explicitly configured in production"
            )
        if len(self.jwt_secret_key.encode("utf-8")) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 bytes in production"
            )

        database_host = urlparse(self.database_url).hostname
        if database_host and database_host.endswith(".localhost") or database_host in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError(
                "DATABASE_URL must not point to localhost in production; "
                "use the managed Postgres service host or a remote database."
            )

        redis_host = urlparse(self.redis_url).hostname
        if redis_host and redis_host.endswith(".localhost") or redis_host in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError(
                "REDIS_URL must not point to localhost in production; "
                "use the managed Redis service host."
            )

        # Wildcard CORS is intentional for the embeddable widget. The
        # app never enables credentialed CORS, so browsers do not attach
        # cookies/HTTP credentials cross-origin. A deployment can replace
        # '*' with an explicit allow-list for a stricter posture.
        origins = get_cors_origins_for_validation(self.cors_allow_origins)
        if not origins:
            raise ValueError(
                "CORS_ALLOW_ORIGINS must not be empty in production"
            )

        if self.storage_backend.lower().strip() == "s3":
            required = {
                "S3_BUCKET": self.s3_bucket,
                "S3_REGION": self.s3_region,
                "S3_ACCESS_KEY_ID": self.s3_access_key_id,
                "S3_SECRET_ACCESS_KEY": self.s3_secret_access_key,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(
                    "Missing production S3 settings: " + ", ".join(missing)
                )

        return self


def get_cors_origins_for_validation(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


settings = Settings()
