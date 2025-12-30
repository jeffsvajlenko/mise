"""Models for recipe ingestion service."""

from typing import Literal
from pydantic import BaseModel, Field, HttpUrl
from uuid import UUID


class IngestionInput(BaseModel):
    """
    Input specification for recipe ingestion.

    Clean, source-agnostic model describing what to ingest.
    Not tied to database schema.
    """

    source_type: Literal["webpage", "youtube", "text", "image"] = Field(
        description="Type of source to ingest from"
    )
    url: HttpUrl | None = Field(
        default=None,
        description="URL for webpage or YouTube sources"
    )
    text: str | None = Field(
        default=None,
        description="Text content for text sources"
    )
    image_path: str | None = Field(
        default=None,
        description="Path to image file for image sources"
    )
    metadata: dict | None = Field(
        default=None,
        description="Optional metadata (tags, notes, etc.)"
    )

    def validate_inputs(self) -> None:
        """
        Validate that required fields are present for source type.

        Raises:
            ValueError: If required fields are missing
        """
        if self.source_type in ("webpage", "youtube"):
            if not self.url:
                raise ValueError(f"{self.source_type} source requires 'url' field")
        elif self.source_type == "text":
            if not self.text:
                raise ValueError("text source requires 'text' field")
        elif self.source_type == "image":
            if not self.image_path:
                raise ValueError("image source requires 'image_path' field")


class IngestionResult(BaseModel):
    """
    Result of recipe ingestion operation.

    Returned by IngestionService to communicate success or failure.
    """

    success: bool = Field(
        description="Whether ingestion succeeded"
    )
    recipe_id: int | None = Field(
        default=None,
        description="Database ID of created recipe (if successful)"
    )
    recipe_uuid: UUID | None = Field(
        default=None,
        description="UUID of created recipe (if successful)"
    )
    ingestion_id: int | None = Field(
        default=None,
        description="Database ID of ingestion request (managed by worker, not service)"
    )
    error_message: str | None = Field(
        default=None,
        description="Error message (if failed)"
    )
    retryable: bool = Field(
        default=False,
        description="Whether this failure is retryable"
    )
    processing_metadata: dict | None = Field(
        default=None,
        description="AI processing metadata (tokens, timing, etc.)"
    )

    @classmethod
    def success_result(
        cls,
        recipe_id: int,
        recipe_uuid: UUID,
        ingestion_id: int | None,
        processing_metadata: dict
    ) -> "IngestionResult":
        """
        Create a success result.

        Args:
            recipe_id: Database ID of created recipe
            recipe_uuid: UUID of created recipe
            ingestion_id: Database ID of ingestion request (optional, managed by worker)
            processing_metadata: AI processing metadata

        Returns:
            IngestionResult: Success result
        """
        return cls(
            success=True,
            recipe_id=recipe_id,
            recipe_uuid=recipe_uuid,
            ingestion_id=ingestion_id,
            processing_metadata=processing_metadata
        )

    @classmethod
    def failure_result(
        cls,
        ingestion_id: int | None,
        error_message: str,
        retryable: bool = False
    ) -> "IngestionResult":
        """
        Create a failure result.

        Args:
            ingestion_id: Database ID of ingestion request (optional, managed by worker)
            error_message: Error message
            retryable: Whether this failure is retryable

        Returns:
            IngestionResult: Failure result
        """
        return cls(
            success=False,
            ingestion_id=ingestion_id,
            error_message=error_message,
            retryable=retryable
        )
