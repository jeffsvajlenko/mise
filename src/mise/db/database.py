import os
from datetime import datetime
from sqlalchemy import create_engine, func
from sqlalchemy.orm import DeclarativeBase, Session, Mapped, mapped_column

# Load environment-specific configuration
from mise.config import load_env
load_env()

# Get database URL from environment, with fallback to default
# Using postgresql+psycopg for synchronous connections with psycopg3
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://mise_user:mise_password@localhost:5432/mise"
)

# Get echo setting from environment (disabled by default for cleaner logs)
SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "False").lower() in ("true", "1", "yes")

engine = create_engine(
    DATABASE_URL,
    echo=SQLALCHEMY_ECHO,
    pool_pre_ping=True  # Verify connections before using
)

class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class TimestampedModel(Base):
    """
    Abstract base model with standard timestamp fields.

    All models inheriting from this will have:
    - id: Auto-incrementing integer primary key
    - created_at: Timestamp when record was created
    - updated_at: Timestamp when record was last updated (auto-updates)
    - deleted_at: Timestamp for soft delete (NULL if not deleted)
    """
    __abstract__ = True

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        comment="Integer primary key for database efficiency"
    )

    created_at: Mapped[datetime] = mapped_column(
        insert_default=func.now(),
        comment="Timestamp when record was created"
    )

    updated_at: Mapped[datetime] = mapped_column(
        insert_default=func.now(),
        onupdate=func.now(),
        comment="Timestamp when record was last updated"
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        default=None,
        comment="Timestamp for soft delete (NULL if not deleted)"
    )

    @property
    def is_deleted(self) -> bool:
        """Check if this record is soft-deleted."""
        return self.deleted_at is not None

def get_session():
    """Get a database session"""
    with Session(engine) as session:
        yield session