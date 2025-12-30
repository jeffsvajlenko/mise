"""Recipe ingestion service layer."""

import logging
from pathlib import Path

from mise.ai.recipe_extractor import (
    extract_from_webpage,
    extract_from_youtube,
    extract_from_text,
    extract_from_image,
)
from mise.db.models import SourceType, IngestionStatus
from mise.db.unit_of_work import UnitOfWork
from mise.ingestion.exceptions import (
    ExtractionError,
    SourceFetchError,
    DuplicateRecipeError,
    ValidationError,
)
from mise.ingestion.models import IngestionInput, IngestionResult
from mise.ingestion.source_utils import create_source_key, normalize_url
from mise.schema.recipe import Recipe

logger = logging.getLogger(__name__)


class IngestionService:
    """
    Service for ingesting recipes from various sources.

    This service orchestrates the entire ingestion process:
    1. Validates input and checks for duplicates
    2. Creates IngestionRequest in database (pending)
    3. Calls AI extraction
    4. Saves recipe and files to database
    5. Updates IngestionRequest status (completed/failed)
    6. Returns structured result

    The service is stateless. Callers must manage UnitOfWork contexts.
    """

    def ingest_recipe(self, uow: UnitOfWork, input_data: IngestionInput) -> IngestionResult:
        """
        Ingest a recipe from the specified source.

        This service focuses on the core ingestion logic:
        - Input validation
        - AI extraction
        - Recipe database persistence

        Note: This does NOT manage IngestionRequest records. The caller (worker)
        is responsible for creating/updating IngestionRequest status.

        Args:
            uow: Unit of Work (must be in active transaction context)
            input_data: Input specification with source type and data

        Returns:
            IngestionResult: Success with recipe_id or failure with error

        Example:
            >>> service = IngestionService()
            >>> with UnitOfWork() as uow:
            ...     input_data = IngestionInput(
            ...         source_type="webpage",
            ...         url="https://example.com/recipe"
            ...     )
            ...     result = service.ingest_recipe(uow, input_data)
            ...     if result.success:
            ...         print(f"Created recipe {result.recipe_id}")
            ...     else:
            ...         print(f"Failed: {result.error_message}")
        """
        # Validate inputs
        try:
            input_data.validate_inputs()
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
            raise ValidationError(str(e))

        # Extract recipe using AI
        try:
            recipe, source_metadata, processing_metadata = self._extract_recipe(input_data)
            logger.info(f"Extracted recipe: {recipe.title}")
        except Exception as e:
            # Classify and wrap errors
            error_message = str(e)
            error_type = type(e).__name__
            retryable = isinstance(e, (ExtractionError, SourceFetchError)) and e.retryable

            logger.error(f"Extraction failed: {error_type}: {error_message}")

            return IngestionResult.failure_result(
                ingestion_id=None,  # No ingestion_id - caller manages this
                error_message=error_message,
                retryable=retryable
            )

        # Save recipe to database
        try:
            recipe_record = uow.recipes.create_recipe(recipe)
            uow.session.flush()  # Get the ID without committing
            recipe_id = recipe_record.id
            recipe_uuid = recipe_record.uuid
            logger.info(f"Saved recipe {recipe_id} ({recipe_uuid})")
        except Exception as e:
            logger.error(f"Failed to save recipe: {e}")

            return IngestionResult.failure_result(
                ingestion_id=None,  # No ingestion_id - caller manages this
                error_message=f"Failed to save recipe: {e}",
                retryable=False
            )

        return IngestionResult.success_result(
            recipe_id=recipe_id,
            recipe_uuid=recipe_uuid,
            ingestion_id=None,  # No ingestion_id - caller manages this
            processing_metadata=processing_metadata
        )

    def _extract_recipe(self, input_data: IngestionInput) -> tuple[Recipe, dict, dict]:
        """
        Extract recipe from source using AI.

        Args:
            input_data: Input specification

        Returns:
            tuple: (Recipe, source_metadata, processing_metadata)

        Raises:
            ExtractionError: If AI extraction fails
            SourceFetchError: If source cannot be fetched
        """
        try:
            if input_data.source_type == "webpage":
                assert input_data.url is not None
                return extract_from_webpage(str(input_data.url))
            elif input_data.source_type == "youtube":
                assert input_data.url is not None
                return extract_from_youtube(str(input_data.url))
            elif input_data.source_type == "text":
                assert input_data.text is not None
                source_url = str(input_data.url) if input_data.url else None
                return extract_from_text(input_data.text, source_url=source_url)
            elif input_data.source_type == "image":
                assert input_data.image_path is not None
                return extract_from_image(input_data.image_path)
            else:
                raise ValueError(f"Unknown source_type: {input_data.source_type}")
        except Exception as e:
            # Classify errors
            error_message = str(e)

            # Network/fetch errors are retryable
            if any(keyword in error_message.lower() for keyword in [
                "connection", "timeout", "network", "unreachable", "404", "503"
            ]):
                raise SourceFetchError(f"Failed to fetch source: {e}", retryable=True)

            # AI/extraction errors are typically retryable
            if any(keyword in error_message.lower() for keyword in [
                "tool_use", "extract_recipe", "claude", "api"
            ]):
                raise ExtractionError(f"Failed to extract recipe: {e}", retryable=True)

            # Other errors
            raise ExtractionError(f"Unexpected error during extraction: {e}", retryable=False)
