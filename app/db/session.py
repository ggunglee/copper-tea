from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import ROOT_DIR, get_settings


def _normalize_sqlite_url(url: str) -> str:
    if not url.startswith("sqlite:///"):
        return url
    raw_path = url.replace("sqlite:///", "", 1)
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


settings = get_settings()
database_url = _normalize_sqlite_url(settings.database_url)
engine_kwargs = {"future": True}
if database_url.startswith("sqlite:///"):
    engine_kwargs["connect_args"] = {"timeout": 20, "check_same_thread": False}

engine = create_engine(database_url, **engine_kwargs)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Session:
    return SessionLocal()
