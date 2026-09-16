from __future__ import annotations

import os
from sqlmodel import SQLModel, create_engine, Session

# DATABASE_URL (e.g. postgresql+psycopg2://user:pass@host:5432/dbname) takes over in
# production — see docker-compose.yml. Local dev with no DATABASE_URL set keeps using a
# SQLite file under storage/, exactly as before, so `uvicorn main:app --reload` still
# works with zero setup.
_database_url = os.environ.get("DATABASE_URL")

if _database_url:
    engine = create_engine(_database_url, pool_pre_ping=True)
else:
    DB_PATH = os.environ.get("APP_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "storage", "app.db"))
    DB_PATH = os.path.abspath(DB_PATH)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db() -> None:
    # Import models so their tables are registered on SQLModel.metadata
    from models import models  # noqa: F401
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
