import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

# Load environment-specific configuration
from mise.config import load_env
load_env()

# Get database URL from environment, with fallback to default
# Using postgresql+psycopg for synchronous connections with psycopg3
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://mise_user:mise_password@localhost:5432/mise"
)

# Get echo setting from environment
SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "True").lower() in ("true", "1", "yes")

engine = create_engine(
    DATABASE_URL,
    echo=SQLALCHEMY_ECHO,
    pool_pre_ping=True  # Verify connections before using
)

class Base(DeclarativeBase):
    pass

def get_session():
    """Get a database session"""
    with Session(engine) as session:
        yield session