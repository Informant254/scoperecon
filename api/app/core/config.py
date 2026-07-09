from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "staging", "production"] = "production"
    app_name: str = "ScopeRecon API"
    api_prefix: str = "/v1"
    public_api_url: str = Field(..., description="https://api.scoperecon.app")
    frontend_url: str = Field(..., description="https://scoperecon.app")
    cors_origins: str = ""

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str  # Project Settings → API → JWT Secret

    # Stripe — NEVER trust client price IDs alone; map plan → server price
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_price_pro: str
    stripe_price_team: str

    # Worker
    redis_url: str | None = None
    internal_worker_token: str  # shared secret for worker callbacks
    max_body_bytes: int = 1_048_576

    # Rate limits
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 60
    rate_limit_scan_per_hour: int = 20

    @field_validator("supabase_jwt_secret", "stripe_webhook_secret", "internal_worker_token")
    @classmethod
    def non_empty_secrets(cls, v: str) -> str:
        if not v or len(v) < 16:
            raise ValueError("secret too short")
        return v

    @property
    def allowed_origins(self) -> list[str]:
        origins = [self.frontend_url.rstrip("/")]
        if self.cors_origins:
            origins.extend(o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip())
        return list(dict.fromkeys(origins))

    def price_to_plan(self, price_id: str) -> str | None:
        mapping = {
            self.stripe_price_pro: "pro",
            self.stripe_price_team: "team",
        }
        return mapping.get(price_id)

    def plan_to_price(self, plan: str) -> str | None:
        return {"pro": self.stripe_price_pro, "team": self.stripe_price_team}.get(plan)


@lru_cache
def get_settings() -> Settings:
    return Settings()
