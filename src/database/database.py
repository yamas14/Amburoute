"""
Database connection and session management.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
import os

# SQLAlchemy Base for declarative models
Base = declarative_base()

# Global engine and thread-local session factory
ENGINE = None
SessionLocal = None

# SQLAlchemy models will inherit from this
def get_engine(database_url=None):
    """Create and return a SQLAlchemy engine."""
    if database_url is None:
        database_url = os.getenv("DATABASE_URL", "sqlite:///./hospitals.db")
    return create_engine(database_url, connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {})

def init_db(database_url=None):
    """Initialize the database connection and create tables."""
    global ENGINE, SessionLocal
    
    engine = get_engine(database_url)
    ENGINE = engine
    SessionLocal = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )
    
    # Import models to ensure they are registered with SQLAlchemy
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    
    return engine

def get_session():
    """Get a database session."""
    if SessionLocal is None:
        init_db()
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
