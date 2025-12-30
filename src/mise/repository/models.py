"""Repository layer models that include database metadata."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from mise.schema.recipe import Recipe


class RecipeRecord(BaseModel):
    """
    Recipe with database metadata.

    Combines the business domain Recipe with infrastructure fields
    from the database layer (id, timestamps, soft delete).

    Note: Source tracking is in the IngestionRequest table, not here.
    To find the source of a recipe, query via recipe.ingestions relationship.
    """
    model_config = ConfigDict(from_attributes=True)  # Enable ORM mode for SQLAlchemy

    # Database metadata
    id: int = Field(description="Database primary key (auto-generated)")
    uuid: UUID = Field(description="Globally unique business identifier")
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    deleted_at: datetime | None = Field(
        default=None,
        description="Soft delete timestamp (None if not deleted)"
    )

    # Business data
    recipe: Recipe = Field(description="The recipe business domain object")

    @property
    def is_deleted(self) -> bool:
        """Check if this record is soft-deleted."""
        return self.deleted_at is not None
