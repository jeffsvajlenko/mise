from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Index, String, ForeignKey, Integer, Enum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4
from enum import Enum as PyEnum
from mise.db.database import TimestampedModel


class SourceType(str, PyEnum):
    """Source types for recipe ingestion."""
    youtube = "youtube"
    webpage = "webpage"
    photo = "photo"
    custom = "custom"


class IngestionStatus(str, PyEnum):
    """Status values for ingestion requests."""
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"

class RecipeDbModel(TimestampedModel):
    """
    Recipe domain model - pure recipe data.

    This table stores only the recipe content in JSONB.
    Source tracking, deduplication, and file metadata are all in the recipe data.
    Use IngestionRequest table to find source/ingestion info.

    Inherits from TimestampedModel: id, created_at, updated_at, deleted_at, is_deleted
    """
    __tablename__ = "recipes"

    # Business identifier (in addition to db id from TimestampedModel)
    uuid: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid4,
        index=True,
        comment="Globally unique business identifier (UUID v4)"
    )

    # Recipe data (JSONB - everything goes here!)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        comment="Complete recipe data (title, ingredients, steps, files, etc.)"
    )

    # Relationship to ingestion requests (for source info)
    ingestions: Mapped[list["IngestionRequest"]] = relationship(
        back_populates="recipe",
        cascade="save-update, merge"
    )

    def __repr__(self):
        name = self.data.get('name', 'Unknown')
        return f"Recipe(id={self.id}, name='{name}')"


class IngestionRequest(TimestampedModel):
    """
    Ingestion processing model for background job queue.

    This table handles:
    - Queue management (pending/processing/completed/failed)
    - Source deduplication checking
    - Processing artifacts (downloads, AI calls, logs)
    - Links to created recipes

    Processing artifacts can be purged after 90 days without affecting recipes.

    Inherits from TimestampedModel: id, created_at, updated_at, deleted_at, is_deleted
    """
    __tablename__ = "ingestion_requests"

    # Business identifier (in addition to db id from TimestampedModel)
    uuid: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid4,
        index=True,
        comment="Unique identifier for this ingestion request"
    )

    # Link to created recipe (nullable until completed)
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"),
        index=True,
        comment="Recipe created from this ingestion (NULL if pending/failed)"
    )

    recipe: Mapped["RecipeDbModel | None"] = relationship(
        back_populates="ingestions"
    )

    # Source identification (for deduplication)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False),
        index=True,
        comment="Source type: youtube, webpage, photo, custom"
    )

    source_key: Mapped[str] = mapped_column(
        String(500),
        unique=True,
        comment="Unique identifier: video_id, normalized URL, image hash, etc."
    )

    source_url: Mapped[str | None] = mapped_column(
        String(1000),
        comment="Original URL submitted by user"
    )

    # Queue/Status management
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, native_enum=False),
        default=IngestionStatus.pending,
        index=True,
        comment="Status: pending, processing, completed, failed, cancelled"
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Higher = process first (0 = normal)"
    )

    # Timestamps
    requested_at: Mapped[datetime] = mapped_column(
        insert_default=lambda: datetime.now(timezone.utc)
    )

    processing_started_at: Mapped[datetime | None] = mapped_column(
        default=None
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        default=None
    )

    # Processing tracking
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=3
    )

    worker_id: Mapped[str | None] = mapped_column(
        String(100),
        comment="ID of worker processing this request"
    )

    # User tracking (optional)
    requested_by: Mapped[str | None] = mapped_column(
        String(100),
        comment="User who requested this ingestion"
    )

    # Processing data (JSONB - can be purged)
    request_params: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        default=None,
        comment="Original request parameters"
    )

    processing_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        default=None,
        comment="Downloads, AI outputs, logs, errors - everything technical"
    )

    def __repr__(self):
        return f"IngestionRequest(id={self.id}, status='{self.status}', source_type='{self.source_type}')"


# Indexes for RecipeDbModel
# Note: These indexes use PostgreSQL-specific JSONB operators

# Index on recipe name (JSONB field)
Index(
    'idx_recipe_name',
    RecipeDbModel.data['name'].as_string(),
    postgresql_where=RecipeDbModel.deleted_at.is_(None)
)

# Index on cuisine (JSONB field)
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


# Indexes for IngestionRequest

# Composite index for queue queries (status + priority + requested_at)
Index(
    'idx_ingestion_queue',
    IngestionRequest.status,
    IngestionRequest.priority.desc(),
    IngestionRequest.requested_at,
    postgresql_where=IngestionRequest.status.in_([IngestionStatus.pending, IngestionStatus.processing])
)