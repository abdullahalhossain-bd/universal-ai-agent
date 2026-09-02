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

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

from pydantic import field_validator
from pydantic import model_validator


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
    # Encrypts merchant connection secrets (DB connection strings,
    # which embed username/password) before they touch our own DB.
    # Required — url-safe base64-encoded 32-byte Fernet key. Generate
    # with:
    #   python -c "from cryptography.fernet import Fernet; \
    #       print(Fernet.generate_key().decode())"
    # Store it in a secrets manager / KMS, never committed alongside
    # code. Rotate by re-encrypting (see CredentialStore) rather than
    # editing rows by hand.
    credential_encryption_key: str

    redis_url: str = (
        "redis://localhost:6379/0"
    )

    # ---------------------------------
    # API
    # ---------------------------------

    api_v1_prefix: str = "/api/v1"
    api_key_prefix: str = "pk_live_"

    # ---------------------------------
    # Groq
    # ---------------------------------

    groq_model: str = (
        "openai/gpt-oss-20b"
    )

    groq_base_url: str = (
        "https://api.groq.com/openai/v1"
    )

    # Cost per 1 million tokens
    groq_input_cost_per_1m: float = 0.075
    groq_output_cost_per_1m: float = 0.30

    # ---------------------------------
    # Groq vision (image chat)
    # ---------------------------------
    # Groq's multimodal lineup changes frequently — this is the
    # current vision-capable chat-completions model as of the last
    # time this was checked. Override via env var if Groq
    # deprecates it (see console.groq.com/docs/vision).
    groq_vision_model: str = "qwen/qwen3.6-27b"

    # Cost per 1 million tokens for the vision model. Kept separate
    # from the text model's cost settings above since vision models
    # are usually priced differently and image tokens are far more
    # expensive per request than a typical text turn.
    groq_vision_input_cost_per_1m: float = 0.20
    groq_vision_output_cost_per_1m: float = 0.60

    # Flat token surcharge applied to preflight budget estimates for
    # an uploaded image (in addition to the text prompt). Image
    # tokenization is model-specific and not something
    # `estimate_messages_tokens` can compute from a stringified
    # message, so a conservative flat estimate is used instead —
    # actual cost is still billed from the real usage the provider
    # returns.
    vision_image_token_estimate: int = 1200

    # ---------------------------------
    # HTTP / networking
    # ---------------------------------
    # Comma-separated list of reverse-proxy IPs whose
    # X-Forwarded-For headers may be trusted. Empty by
    # default: the direct peer address is always used.
    trusted_proxies: str = ""

    # Maximum bytes fetched per crawled page.
    crawler_max_page_bytes: int = 2_000_000

    # Maximum pages crawled per knowledge ingestion.
    crawler_max_pages: int = 50

    # Crawler per-request timeout (seconds).
    crawler_timeout_seconds: float = 15.0

    # Budget reservation TTL (seconds). A reservation older
    # than this is considered stale and expires.
    reservation_ttl_seconds: int = 300

    # Create missing tables on startup. Keep true for
    # development; set false in production where schema
    # evolution is managed exclusively by `alembic upgrade head`.
    auto_create_tables: bool = True

    # ---------------------------------
    # Image chat / vision
    # ---------------------------------

    # Local filesystem root for uploaded chat images when no other
    # object storage backend is configured. See
    # app.images.local_storage.LocalObjectStorage.
    image_storage_path: str = "./data/chat-images"

    # Object storage backend for uploaded chat images: "local" or
    # "s3". Use "s3" for any deployment running more than one
    # API/worker replica, or on a platform without a persistent
    # attached disk — see app.images.storage.get_object_storage.
    storage_backend: str = "local"

    # S3-compatible storage config (only read when
    # storage_backend == "s3"). Works with AWS S3 or any
    # S3-compatible provider (Cloudflare R2, DigitalOcean Spaces,
    # Backblaze B2, MinIO) via s3_endpoint_url.
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    # Optional CDN/public bucket base URL, e.g.
    # "https://cdn.example.com" or an R2 public bucket URL. When
    # unset, get_url() returns a 7-day presigned URL instead.
    s3_public_base_url: str | None = None

    # How long a vision analysis result is cached (redis), keyed by
    # image content hash + task. Re-analyzing the same photo is
    # wasted provider spend.
    vision_cache_ttl_seconds: int = 86400

    # Maximum number of matched products returned for an image.
    vision_max_matched_products: int = 5

    # Comma-separated list of origins allowed to call the API
    # from a browser (needed for the embeddable merchant widget,
    # which runs on arbitrary merchant domains). "*" allows any
    # origin — safe here because auth is a custom `x-api-key`
    # header, not a cookie, so allow_credentials stays False.
    cors_allow_origins: str = "*"

    # ---------------------------------
    # Observability
    # ---------------------------------

    # JSON logs by default (what log aggregators expect in
    # production). Set false for human-readable plain-text output
    # in local dev.
    log_json: bool = True

    # Optional. A plain JSON-POST webhook URL (Slack incoming
    # webhook, PagerDuty/Opsgenie inbound integration, or your own
    # endpoint) that gets a payload whenever an unhandled exception
    # reaches the top-level handler. Unset by default — errors are
    # always in the structured logs regardless; this is an
    # additional, optional push channel.
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
    # Dashboard auth (merchant email/password login, separate from
    # the x-api-key auth used by the embeddable widget / storefront)
    # ---------------------------------

    # HMAC signing secret for dashboard session JWTs. Required in
    # production — generate with:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    # Rotating it invalidates every issued session token.
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60 * 24 * 7  # 7 days
    admin_jwt_access_token_minutes: int = 60 * 8  # 8 hours

    # Base URL of the deployed React dashboard, used to build Stripe
    # Checkout / Billing Portal redirect URLs.
    frontend_url: str = "http://localhost:5173"

    # ---------------------------------
    # Billing (Stripe)
    # ---------------------------------

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    # One recurring Stripe Price ID per plan (Dashboard -> Product
    # catalog -> create a monthly recurring price, copy its
    # price_... ID). Plans without a configured price ID can't be
    # checked out via Stripe (see app/billing/service.py).
    stripe_price_starter: str | None = None
    stripe_price_growth: str | None = None
    stripe_price_pro: str | None = None

    # ---------------------------------
    # Pydantic Settings
    # ---------------------------------

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
        """
        Tolerate Windows-authored .env files (CRLF line
        endings) and stray whitespace around values.

        Without this, a trailing CR breaks SQLAlchemy URL
        parsing on POSIX systems.
        """

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

        origins = get_cors_origins_for_validation(self.cors_allow_origins)
        if not origins or "*" in origins:
            raise ValueError(
                "CORS_ALLOW_ORIGINS must list explicit origins in production"
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