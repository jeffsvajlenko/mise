from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Index, func, String, and_
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4
from mise.db.database import Base

class RecipeDbModel(Base):
    """
    Minimal database model with JSONB storage.
    All recipe data lives in the 'data' JSONB column.
    """
    __tablename__ = "recipes"
    
    # Infrastructure fields only
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        comment="Integer primary key for database efficiency"
    )

    uuid: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid4,
        index=True,
        comment="Globally unique business identifier (UUID v4)"
    )

    created_at: Mapped[datetime] = mapped_column(
        insert_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        insert_default=func.now(),
        onupdate=func.now()
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        default=None
    )

    # Source tracking for deduplication and provenance
    source_type: Mapped[str | None] = mapped_column(
        String(50),
        default=None,
        index=True,
        comment="Type of source: 'custom', 'youtube', 'photo', 'webpage', etc."
    )

    source_key: Mapped[str | None] = mapped_column(
        String(500),
        default=None,
        comment="Unique identifier within source type (URL, video ID, hash, etc.)"
    )

    source_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        default=None,
        comment="Additional metadata about the source (optional)"
    )

    # All recipe data goes here
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,  # PostgreSQL JSONB type for efficient JSON storage
    )
    
    def __repr__(self):
        name = self.data.get('name', 'Unknown')
        return f"Recipe(id={self.id}, name='{name}')"
    
    @property
    def is_deleted(self) -> bool:
        """Check if recipe is soft-deleted"""
        return self.deleted_at is not None


# Indexes for common queries
# Note: These indexes use PostgreSQL-specific JSONB operators
# They will be created when init_db() is called
Index(
    'idx_recipe_name',
    RecipeDbModel.data['name'].as_string(),
    postgresql_where=RecipeDbModel.deleted_at.is_(None)
)

Index(
    'idx_recipe_cuisine',
    RecipeDbModel.data['cuisine'].as_string(),
    postgresql_where=RecipeDbModel.deleted_at.is_(None)
)

# GIN index for full JSONB search
# Using jsonb_path_ops operator class for better performance
Index(
    'idx_recipe_data_gin',
    RecipeDbModel.data,
    postgresql_using='gin',
    postgresql_ops={'data': 'jsonb_path_ops'}
)

# Unique constraint on source for deduplication
# Only applies to non-deleted recipes with source tracking
Index(
    'idx_recipe_source_unique',
    RecipeDbModel.source_type,
    RecipeDbModel.source_key,
    unique=True,
    postgresql_where=and_(
        RecipeDbModel.source_type.isnot(None),
        RecipeDbModel.source_key.isnot(None),
        RecipeDbModel.deleted_at.is_(None)
    )
)