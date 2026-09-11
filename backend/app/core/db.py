from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # Recycle connections before Supabase's pooler can silently drop an idle one out from
    # under us — pool_pre_ping already catches a dead connection and reconnects, but doing it
    # proactively avoids paying for that extra failed-ping-then-reconnect round trip on the
    # first request after a quiet period.
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
