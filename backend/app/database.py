"""SQLAlchemy Database configuration and session management."""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

# Handle relative SQLite paths correctly
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite:///./"):
    backend_root = Path(__file__).resolve().parent.parent
    rel_path = db_url.replace("sqlite:///./", "")
    abs_path = backend_root / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{abs_path}"

engine = create_engine(
    db_url,
    connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI Dependency for database session management."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
