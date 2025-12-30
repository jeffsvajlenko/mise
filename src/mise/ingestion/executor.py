"""Ingestion executor for managing request lifecycle."""

import hashlib
import logging
from pathlib import Path

from mise.db.models import SourceType, IngestionStatus
from mise.db.unit_of_work import UnitOfWork
from mise.ingestion.exceptions import DuplicateRecipeError, ValidationError
from mise.ingestion.models import IngestionInput, IngestionResult
from mise.ingestion.service import IngestionService
from mise.ingestion.source_utils import create_source_key, normalize_url

logger = logging.getLogger(__name__)


def execute_ingestion_request(
    uow: UnitOfWork,
    input_data: IngestionInput
) -> IngestionResult:
    """
    Execute an ingestion request with full lifecycle management.

    This is Layer 3 of the ingestion pipeline:
    - Creates and manages IngestionRequest records
    - Handles duplicate detection
    - Calls the IngestionService (Layer 4)
    - Updates request status based on results

    Used by:
    - Worker process (Layer 2) to execute pending requests
    - API endpoints (Layer 1) for immediate execution
    - Test scripts for manual ingestion

    Args:
        uow: Unit of Work (must be in active transaction context)
        input_data: Input specification with source type and data

    Returns:
        IngestionResult: Success or failure with ingestion_id populated

    Raises:
        DuplicateRecipeError: If recipe already exists from this source
        ValidationError: If input is invalid

    Example:
        >>> with UnitOfWork() as uow:
        ...     input_data = IngestionInput(
        ...         source_type="text",
        ...         text="Recipe content..."
        ...     )
        ...     result = execute_ingestion_request(uow, input_data)
        ...     print(f"Recipe {result.recipe_id} from ingestion {result.ingestion_id}")
    """
    # 1. Map input source_type to SourceType enum and create source_key for deduplication
    if input_data.source_type in ("webpage", "youtube"):
        source_type = SourceType(input_data.source_type)
        assert input_data.url is not None  # Validated by input_data.validate_inputs()
        source_url = str(input_data.url)
        normalized_url: str = normalize_url(source_url)
        source_key = create_source_key(source_type, normalized_url)
    elif input_data.source_type == "text":
        # Text uses "custom" source type with hash-based source_key
        source_type = SourceType.custom
        assert input_data.text is not None  # Validated by input_data.validate_inputs()
        text_hash = hashlib.sha256(input_data.text.encode()).hexdigest()[:16]
        source_key = f"text:{text_hash}"
        source_url = str(input_data.url) if input_data.url else None
        normalized_url = normalize_url(source_url) if source_url else None
    else:  # image
        # Image uses "photo" source type with filename-based source_key
        source_type = SourceType.photo
        assert input_data.image_path is not None  # Validated by input_data.validate_inputs()
        image_name = Path(input_data.image_path).name
        source_key = f"image:{image_name}"
        source_url = None
        normalized_url = None

    # 2. Check for duplicates (completed ingestions only)
    existing = uow.ingestions.find_by_source_key(source_key)
    if existing and existing.recipe_id:
        logger.info(f"Duplicate recipe from source: {source_key}")
        raise DuplicateRecipeError(
            f"Recipe already exists from this source: {source_key}",
            existing_recipe_id=existing.recipe_id
        )

    # 3. Create IngestionRequest (pending status)
    ingestion_request = uow.ingestions.create_request(
        source_type=source_type,
        source_key=source_key,
        source_url=normalized_url,
        request_params=input_data.metadata or {},
    )
    uow.session.flush()  # Get the ID without committing
    ingestion_id = ingestion_request.id
    logger.info(f"Created ingestion request {ingestion_id} for {source_key}")

    # 4. Update to processing status
    uow.ingestions.update_status(
        ingestion_id,
        IngestionStatus.processing
    )

    # 5. Execute the ingestion service (Layer 4)
    service = IngestionService()
    try:
        result = service.ingest_recipe(uow, input_data)
    except ValidationError:
        # Re-raise validation errors as-is
        raise
    except Exception as e:
        # Catch unexpected exceptions and mark as failed
        logger.error(f"Unexpected error during ingestion: {e}")
        uow.ingestions.mark_failed(
            ingestion_id,
            error_message=f"Unexpected error: {e}",
            error_type=type(e).__name__,
            retry=False
        )
        # Return failure result
        return IngestionResult.failure_result(
            ingestion_id=ingestion_id,
            error_message=f"Unexpected error: {e}",
            retryable=False
        )

    # 6. Update IngestionRequest based on result
    if result.success:
        assert result.recipe_id is not None
        uow.ingestions.mark_completed(
            ingestion_id,
            recipe_id=result.recipe_id,
            processing_metadata=result.processing_metadata or {}
        )
        logger.info(f"Completed ingestion {ingestion_id} -> recipe {result.recipe_id}")
    else:
        uow.ingestions.mark_failed(
            ingestion_id,
            error_message=result.error_message or "Unknown error",
            error_type="ExtractionError",
            retry=result.retryable
        )
        logger.error(f"Failed ingestion {ingestion_id}: {result.error_message}")

    # 7. Return result with ingestion_id populated
    result.ingestion_id = ingestion_id
    return result
