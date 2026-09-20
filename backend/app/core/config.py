import logging
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("proxybusters.config")

# Substrings that only ever appear in the .env.example / docker-compose throwaway values.
_PLACEHOLDER_MARKERS = ("change-me", "changeme", "dev_only", "your-", "your_")
_MIN_SECRET_LENGTH = 32


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    # "development" | "test" | "production". In production the app refuses to start with weak,
    # placeholder or shared secrets (see _check_production_safety) instead of silently running
    # with them.
    environment: str = "development"

    database_url: str

    supabase_url: str = ""
    supabase_anon_key: str = ""

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    qr_signing_secret: str
    qr_token_ttl_seconds: int = 5

    cooldown_minutes: int = 60

    # Short server-enforced cooldown applied after every successful QR scan (distinct from
    # cooldown_minutes, which is a longer penalty for voluntary logout). Prevents a student
    # from immediately marking attendance again in a different ad-hoc session.
    scan_cooldown_seconds: int = 60

    # SQLAlchemy connection pool. Supabase's session-mode pooler allows only ~15 client
    # connections IN TOTAL (migrations, dashboards and other tools share that budget) and refuses
    # extra ones outright (EMAXCONNSESSION) instead of queueing them. The old defaults (5 + 10
    # overflow = 15) could exhaust it alone and surface as HTTP 500s, so stay well below it;
    # requests that need a connection beyond that wait up to pool_timeout for one.
    db_pool_size: int = 5
    db_max_overflow: int = 4
    db_pool_timeout_seconds: int = 20

    cors_origins: str = "http://localhost:3000"

    # Gates professor self-registration. Deliberately backend-only, never returned by any
    # API response, never logged. Empty string means professor registration is disabled
    # entirely (safe default) rather than silently accepting any/no code.
    professor_invite_code: str = ""

    # Public student self-registration. Admins normally create students (see /admin/students);
    # once a college has been imported, turn this off so outsiders cannot squat on roll numbers.
    allow_public_student_registration: bool = True

    # Brute-force protection: after this many failed logins for one account inside the window,
    # further attempts are rejected (429) until the window rolls over — regardless of source IP.
    login_max_failures: int = 8
    login_failure_window_minutes: int = 15

    # Background maintenance loop (expires overdue sessions, resumes QR rotation after a
    # restart, prunes old QR tokens). Disabled in tests.
    enable_background_tasks: bool = True
    qr_token_retention_hours: int = 24

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS is a comma-separated list of allowed origins, e.g.
        'http://localhost:3000,https://proxy-buster.vercel.app'. Whitespace around
        each entry is stripped and empty entries are dropped."""
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        problems: list[str] = []
        for name, value in (("JWT_SECRET", self.jwt_secret), ("QR_SIGNING_SECRET", self.qr_signing_secret)):
            if len(value) < _MIN_SECRET_LENGTH:
                problems.append(f"{name} must be at least {_MIN_SECRET_LENGTH} characters")
            if _looks_like_placeholder(value):
                problems.append(f"{name} still contains a placeholder value")
        if self.jwt_secret == self.qr_signing_secret:
            problems.append("JWT_SECRET and QR_SIGNING_SECRET must be different")
        if "*" in self.cors_origins_list:
            problems.append("CORS_ORIGINS must list explicit origins, not '*'")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point at PostgreSQL")
        if self.qr_token_ttl_seconds < 2:
            problems.append("QR_TOKEN_TTL_SECONDS must be at least 2")

        if not problems:
            return self
        if self.is_production:
            # Names only — never echo the offending values.
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        # Outside production, don't block local work but make the weakness visible.
        if self.environment.strip().lower() != "test":
            logger.warning("Configuration would be rejected in production: %s", "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
