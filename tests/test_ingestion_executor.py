"""Tests for ingestion executor."""

import pytest
from uuid import uuid4
from unittest.mock import patch
from mise.ingestion.executor import execute_ingestion_request
from mise.ingestion.models import IngestionInput
from mise.ingestion.exceptions import DuplicateRecipeError
from mise.schema.recipe import Recipe, Ingredient, RecipeStep


@pytest.fixture
def mock_uow(uow):
    """Provide a UnitOfWork for testing."""
    return uow


@pytest.mark.integration
@patch("mise.ingestion.executor.IngestionService")
def test_execute_ingestion_request_success(mock_service_class, mock_uow):
    """Test successful execution with ingestion request management."""
    # Setup mock service
    mock_service = mock_service_class.return_value
    mock_recipe = Recipe(
        title="Test Recipe",
        ingredients=[Ingredient(text="1 cup flour", name="flour", quantity=1.0, unit="cup")],
        steps=[RecipeStep(instruction="Mix ingredients")]
    )
    mock_processing_metadata = {"model": "claude-haiku-4-5-20251001", "input_tokens": 100}

    # Mock service to return success
    from mise.ingestion.models import IngestionResult
    test_uuid = uuid4()
    mock_service.ingest_recipe.return_value = IngestionResult.success_result(
        recipe_id=1,
        recipe_uuid=test_uuid,
        ingestion_id=None,
        processing_metadata=mock_processing_metadata
    )

    # Create input
    input_data = IngestionInput(source_type="text", text="Test recipe")

    # Execute
    result = execute_ingestion_request(mock_uow, input_data)

    # Verify result
    assert result.success is True
    assert result.recipe_id == 1
    assert result.ingestion_id is not None  # Executor populates this
    assert result.processing_metadata == mock_processing_metadata

    # Verify ingestion request was created and completed
    ingestion = mock_uow.ingestions.get_by_id(result.ingestion_id)
    assert ingestion is not None
    assert ingestion.status.value == "completed"
    assert ingestion.recipe_id == 1


@pytest.mark.integration
@patch("mise.ingestion.executor.IngestionService")
def test_execute_ingestion_request_failure(mock_service_class, mock_uow):
    """Test failed execution with ingestion request management."""
    # Setup mock service to return failure
    mock_service = mock_service_class.return_value
    from mise.ingestion.models import IngestionResult
    mock_service.ingest_recipe.return_value = IngestionResult.failure_result(
        ingestion_id=None,
        error_message="AI extraction failed",
        retryable=True
    )

    # Create input
    input_data = IngestionInput(source_type="text", text="Test recipe")

    # Execute
    result = execute_ingestion_request(mock_uow, input_data)

    # Verify result
    assert result.success is False
    assert result.recipe_id is None
    assert result.ingestion_id is not None  # Executor populates this
    assert "AI extraction failed" in result.error_message
    assert result.retryable is True

    # Verify ingestion request was created and marked as failed
    ingestion = mock_uow.ingestions.get_by_id(result.ingestion_id)
    assert ingestion is not None
    assert ingestion.status.value == "pending"  # Pending for retry since retryable=True


@pytest.mark.integration
def test_execute_ingestion_request_duplicate_detection(mock_uow):
    """Test that duplicate recipes are detected at executor level."""
    # Create a test recipe directly
    test_recipe = Recipe(
        title="Test Recipe",
        ingredients=[Ingredient(text="1 cup flour", name="flour", quantity=1.0, unit="cup")],
        steps=[RecipeStep(instruction="Mix ingredients")]
    )
    recipe_record = mock_uow.recipes.create_recipe(test_recipe)
    mock_uow.session.flush()

    # Manually create an ingestion request that's already completed with this recipe
    from mise.db.models import SourceType
    import hashlib
    text = "Test recipe content"
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    source_key = f"text:{text_hash}"

    ingestion_request = mock_uow.ingestions.create_request(
        source_type=SourceType.custom,
        source_key=source_key,
        source_url=None,
        request_params={}
    )
    mock_uow.session.flush()
    mock_uow.ingestions.mark_completed(ingestion_request.id, recipe_record.id, {})

    # Create input with same text
    input_data = IngestionInput(source_type="text", text=text)

    # Try to execute - should raise DuplicateRecipeError
    with pytest.raises(DuplicateRecipeError) as exc_info:
        execute_ingestion_request(mock_uow, input_data)

    assert exc_info.value.existing_recipe_id == recipe_record.id


@pytest.mark.integration
@patch("mise.ingestion.executor.IngestionService")
def test_execute_ingestion_request_exception_handling(mock_service_class, mock_uow):
    """Test that unexpected exceptions are caught and recorded."""
    # Setup mock service to raise unexpected exception
    mock_service = mock_service_class.return_value
    mock_service.ingest_recipe.side_effect = RuntimeError("Unexpected error")

    # Create input
    input_data = IngestionInput(source_type="text", text="Test recipe")

    # Execute - should not raise, but return failure result
    result = execute_ingestion_request(mock_uow, input_data)

    # Verify result
    assert result.success is False
    assert result.recipe_id is None
    assert result.ingestion_id is not None
    assert "Unexpected error" in result.error_message
    assert result.retryable is False

    # Verify ingestion request was marked as failed
    ingestion = mock_uow.ingestions.get_by_id(result.ingestion_id)
    assert ingestion is not None
    assert ingestion.status.value == "failed"
    assert ingestion.recipe_id is None
