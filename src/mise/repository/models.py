"""Repository layer models that include database metadata."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from mise.schema.recipe import Recipe


class RecipeRecord(BaseModel):
    """
    Recipe with database metadata.

    Combines the business domain Recipe with infrastructure fields
    from the database layer (id, timestamps, soft delete).
    """
    # Database metadata
    id: int = Field(description="Database primary key (auto-generated)")
    uuid: UUID = Field(description="Globally unique business identifier")
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    deleted_at: datetime | None = Field(
        default=None,
        description="Soft delete timestamp (None if not deleted)"
    )

    # Source tracking for deduplication and provenance
    source_type: str | None = Field(
        default=None,
        description="Source type: 'custom', 'youtube', 'photo', 'webpage'"
    )
    source_key: str | None = Field(
        default=None,
        description="Unique identifier within source type"
    )
    source_metadata: dict | None = Field(
        default=None,
        description="Additional source metadata (URLs, timestamps, etc.)"
    )

    # Business data
    recipe: Recipe = Field(description="The recipe business domain object")

    @property
    def is_deleted(self) -> bool:
        """Check if this record is soft-deleted."""
        return self.deleted_at is not None

    class Config:
        """Pydantic configuration."""
        from_attributes = True  # Enable ORM mode for SQLAlchemy
