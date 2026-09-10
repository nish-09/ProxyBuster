from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    database_url: str

    supabase_url: str = ""
    supabase_anon_key: str = ""

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    qr_signing_secret: str
    qr_token_ttl_seconds: int = 10

    cooldown_minutes: int = 60

    cors_origins: str = "http://localhost:3000"

    # Gates professor self-registration. Deliberately backend-only, never returned by any
    # API response, never logged. Empty string means professor registration is disabled
    # entirely (safe default) rather than silently accepting any/no code.
    professor_invite_code: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS is a comma-separated list of allowed origins, e.g.
        'http://localhost:3000,https://proxy-buster.vercel.app'. Whitespace around
        each entry is stripped and empty entries are dropped."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
