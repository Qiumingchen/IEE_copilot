from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


_engine = None
_engine_database_url: str | None = None
_session_local = None


def build_engine(database_url: str | None = None):
    settings = get_settings()
    url = database_url or settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


def reset_engine() -> None:
    global _engine, _engine_database_url, _session_local

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_database_url = None
    _session_local = None


def get_engine():
    global _engine, _engine_database_url

    database_url = get_settings().database_url
    if _engine is None or _engine_database_url != database_url:
        if _engine is not None:
            _engine.dispose()
        _engine = build_engine(database_url)
        _engine_database_url = database_url
    return _engine


def get_session_local():
    global _session_local

    engine = get_engine()
    if _session_local is None or _session_local.kw["bind"] is not engine:
        _session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _session_local


class _SessionLocalProxy:
    def __call__(self, *args, **kwargs):
        return get_session_local()(*args, **kwargs)


class _EngineProxy:
    def __getattr__(self, name: str):
        return getattr(get_engine(), name)


engine = _EngineProxy()
SessionLocal = _SessionLocalProxy()


def get_db() -> Generator[Session, None, None]:
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()


def ping_database() -> bool:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
