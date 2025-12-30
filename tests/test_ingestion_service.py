"""Tests for ingestion service."""

import pytest
from unittest.mock import Mock, patch
from mise.ingestion.service import IngestionService
from mise.ingestion.models import IngestionInput, IngestionResult
from mise.ingestion.exceptions import DuplicateRecipeError, ValidationError
from mise.schema.recipe import Recipe, Ingredient, RecipeStep


@pytest.fixture
def mock_uow(uow):
    """Provide a UnitOfWork for testing."""
    return uow


def test_validate_inputs_webpage_missing_url():
    """Test that webpage source requires url field."""
    input_data = IngestionInput(source_type="webpage")

    with pytest.raises(ValueError, match="webpage source requires 'url' field"):
        input_data.validate_inputs()


def test_validate_inputs_youtube_missing_url():
    """Test that youtube source requires url field."""
    input_data = IngestionInput(source_type="youtube")

    with pytest.raises(ValueError, match="youtube source requires 'url' field"):
        input_data.validate_inputs()


def test_validate_inputs_text_missing_text():
    """Test that text source requires text field."""
    input_data = IngestionInput(source_type="text")

    with pytest.raises(ValueError, match="text source requires 'text' field"):
        input_data.validate_inputs()


def test_validate_inputs_image_missing_path():
    """Test that image source requires image_path field."""
    input_data = IngestionInput(source_type="image")

    with pytest.raises(ValueError, match="image source requires 'image_path' field"):
        input_data.validate_inputs()


def test_validate_inputs_valid_webpage():
    """Test that valid webpage input passes validation."""
    input_data = IngestionInput(
        source_type="webpage",
        url="https://example.com/recipe"
    )
    # Should not raise
    input_data.validate_inputs()


@pytest.mark.integration
@patch("mise.ingestion.service.extract_from_text")
def test_ingest_recipe_text_success(mock_extract, mock_uow):
    """Test successful recipe ingestion from text."""
    # Setup mock extraction
    mock_recipe = Recipe(
        title="Test Recipe",
        ingredients=[
            Ingredient(
                text="1 cup flour",
                name="flour",
                quantity=1.0,
                unit="cup"
            )
        ],
        steps=[
            RecipeStep(instruction="Mix ingredients")
        ]
    )
    mock_source_metadata = {
        "source_type": "text",
        "source_key": "text:abc123",
    }
    mock_processing_metadata = {
        "model": "claude-haiku-4-5-20251001",
        "input_tokens": 100,
        "output_tokens": 200,
    }
    mock_extract.return_value = (mock_recipe, mock_source_metadata, mock_processing_metadata)

    # Create service
    service = IngestionService()

    # Create input
    input_data = IngestionInput(
        source_type="text",
        text="Test recipe content"
    )

    # Ingest
    result = service.ingest_recipe(mock_uow, input_data)

    # Verify result
    assert result.success is True
    assert result.recipe_id is not None
    assert result.recipe_uuid is not None
    assert result.ingestion_id is not None
    assert result.error_message is None
    assert result.processing_metadata == mock_processing_metadata

    # Verify recipe was created
    recipe_record = mock_uow.recipes.get_recipe_by_id(result.recipe_id)
    assert recipe_record is not None
    assert recipe_record.recipe.title == "Test Recipe"

    # Verify ingestion was completed
    ingestion = mock_uow.ingestions.get_by_id(result.ingestion_id)
    assert ingestion is not None
    assert ingestion.status.value == "completed"
    assert ingestion.recipe_id == result.recipe_id


@pytest.mark.integration
@patch("mise.ingestion.service.extract_from_text")
def test_ingest_recipe_duplicate_detection(mock_extract, mock_uow):
    """Test that duplicate recipes are detected."""
    # Setup mock extraction
    mock_recipe = Recipe(
        title="Test Recipe",
        ingredients=[
            Ingredient(
                text="1 cup flour",
                name="flour",
                quantity=1.0,
                unit="cup"
            )
        ],
        steps=[
            RecipeStep(instruction="Mix ingredients")
        ]
    )
    mock_source_metadata = {
        "source_type": "text",
        "source_key": "text:abc123",
    }
    mock_processing_metadata = {
        "model": "claude-haiku-4-5-20251001",
        "input_tokens": 100,
        "output_tokens": 200,
    }
    mock_extract.return_value = (mock_recipe, mock_source_metadata, mock_processing_metadata)

    # Create service
    service = IngestionService()

    # Create input
    input_data = IngestionInput(
        source_type="text",
        text="Test recipe content"
    )

    # Ingest once
    result1 = service.ingest_recipe(mock_uow, input_data)
    assert result1.success is True

    # Try to ingest again - should raise DuplicateRecipeError
    with pytest.raises(DuplicateRecipeError) as exc_info:
        service.ingest_recipe(mock_uow, input_data)

    assert exc_info.value.existing_recipe_id == result1.recipe_id


@pytest.mark.integration
@patch("mise.ingestion.service.extract_from_text")
def test_ingest_recipe_extraction_failure(mock_extract, mock_uow):
    """Test handling of extraction failures."""
    # Setup mock to raise exception
    mock_extract.side_effect = Exception("AI extraction failed")

    # Create service
    service = IngestionService()

    # Create input
    input_data = IngestionInput(
        source_type="text",
        text="Test recipe content"
    )

    # Ingest - should return failure result
    result = service.ingest_recipe(mock_uow, input_data)

    assert result.success is False
    assert result.recipe_id is None
    assert "AI extraction failed" in result.error_message
    assert result.retryable is False  # Unknown errors are not retryable

    # Verify ingestion was marked as failed
    ingestion = mock_uow.ingestions.get_by_id(result.ingestion_id)
    assert ingestion is not None
    assert ingestion.status.value == "failed"
    assert ingestion.recipe_id is None


def test_ingestion_result_success():
    """Test IngestionResult success factory method."""
    from uuid import uuid4

    recipe_uuid = uuid4()
    result = IngestionResult.success_result(
        recipe_id=123,
        recipe_uuid=recipe_uuid,
        ingestion_id=456,
        processing_metadata={"tokens": 100}
    )

    assert result.success is True
    assert result.recipe_id == 123
    assert result.recipe_uuid == recipe_uuid
    assert result.ingestion_id == 456
    assert result.processing_metadata == {"tokens": 100}
    assert result.error_message is None
    assert result.retryable is False


def test_ingestion_result_failure():
    """Test IngestionResult failure factory method."""
    result = IngestionResult.failure_result(
        ingestion_id=456,
        error_message="Something went wrong",
        retryable=True
    )

    assert result.success is False
    assert result.recipe_id is None
    assert result.recipe_uuid is None
    assert result.ingestion_id == 456
    assert result.error_message == "Something went wrong"
    assert result.retryable is True
