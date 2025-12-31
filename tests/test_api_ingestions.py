"""Tests for ingestion API endpoints."""

import pytest
from unittest.mock import patch
from uuid import uuid4

from mise.schema.recipe import Recipe, Ingredient, RecipeStep
from mise.ingestion.models import IngestionResult
from mise.db.models import IngestionStatus


@pytest.fixture
def mock_ingestion_service():
    """
    Mock the IngestionService to avoid actual AI calls.

    Returns a patch context that can be used as a decorator or context manager.
    """
    with patch("mise.ingestion.executor.IngestionService") as mock_service_class:
        yield mock_service_class


@pytest.mark.integration
def test_create_text_ingestion(api_client, sample_ingestion_payload, mock_ingestion_service):
    """POST /api/ingestions creates a text ingestion request."""
    # Mock the AI service to return success
    mock_service = mock_ingestion_service.return_value
    test_uuid = uuid4()
    mock_recipe = Recipe(
        title="Test Recipe",
        ingredients=[Ingredient(text="2 cups flour", name="flour", quantity=2.0, unit="cups")],
        steps=[RecipeStep(instruction="Mix ingredients")]
    )

    mock_service.ingest_recipe.return_value = IngestionResult.success_result(
        recipe_id=1,
        recipe_uuid=test_uuid,
        ingestion_id=None,
        processing_metadata={"model": "claude-haiku", "tokens": 100}
    )

    response = api_client.post("/api/ingestions", json=sample_ingestion_payload)

    assert response.status_code == 201

    data = response.json()
    assert data["status"] == "pending"  # Initially pending, worker will process
    assert data["source_type"] == "custom"  # text maps to custom
    assert "id" in data
    assert "uuid" in data
    assert data["recipe_id"] is None  # Not yet processed


@pytest.mark.integration
def test_create_webpage_ingestion(api_client):
    """POST /api/ingestions creates a webpage ingestion request."""
    payload = {
        "source_type": "webpage",
        "url": "https://example.com/recipe",
        "metadata": {}
    }

    response = api_client.post("/api/ingestions", json=payload)

    assert response.status_code == 201

    data = response.json()
    assert data["status"] == "pending"
    assert data["source_type"] == "webpage"
    assert data["source_url"] == "https://example.com/recipe"


@pytest.mark.integration
def test_create_youtube_ingestion(api_client):
    """POST /api/ingestions creates a YouTube ingestion request."""
    payload = {
        "source_type": "youtube",
        "url": "https://youtube.com/watch?v=test123",
        "metadata": {}
    }

    response = api_client.post("/api/ingestions", json=payload)

    assert response.status_code == 201

    data = response.json()
    assert data["status"] == "pending"
    assert data["source_type"] == "youtube"


@pytest.mark.integration
def test_create_ingestion_missing_text(api_client):
    """POST /api/ingestions returns 400 when text source is missing text field."""
    payload = {
        "source_type": "text",
        # Missing "text" field
        "metadata": {}
    }

    response = api_client.post("/api/ingestions", json=payload)

    assert response.status_code == 400
    assert "text" in response.json()["detail"].lower()


@pytest.mark.integration
def test_create_ingestion_missing_url(api_client):
    """POST /api/ingestions returns 400 when webpage source is missing url field."""
    payload = {
        "source_type": "webpage",
        # Missing "url" field
        "metadata": {}
    }

    response = api_client.post("/api/ingestions", json=payload)

    assert response.status_code == 400
    assert "url" in response.json()["detail"].lower()


@pytest.mark.integration
def test_create_ingestion_image_not_implemented(api_client):
    """POST /api/ingestions returns 400 for image type (not yet implemented)."""
    payload = {
        "source_type": "image",
        "metadata": {}
    }

    response = api_client.post("/api/ingestions", json=payload)

    assert response.status_code == 400
    assert "image" in response.json()["detail"].lower()


@pytest.mark.integration
def test_get_ingestion_by_id(api_client, sample_ingestion_payload):
    """GET /api/ingestions/{id} returns ingestion details."""
    # Create an ingestion first
    create_response = api_client.post("/api/ingestions", json=sample_ingestion_payload)
    assert create_response.status_code == 201
    ingestion_id = create_response.json()["id"]

    # Get the ingestion
    response = api_client.get(f"/api/ingestions/{ingestion_id}")

    assert response.status_code == 200

    data = response.json()
    assert data["id"] == ingestion_id
    assert data["status"] in ("pending", "processing", "completed", "failed")
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.integration
def test_get_ingestion_not_found(api_client):
    """GET /api/ingestions/{id} returns 404 for non-existent ID."""
    response = api_client.get("/api/ingestions/99999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.integration
def test_list_ingestions(api_client, sample_ingestion_payload):
    """GET /api/ingestions returns paginated list."""
    # Create a couple of ingestions with unique text
    payload1 = sample_ingestion_payload.copy()
    payload1["text"] = "Recipe 1: Mix ingredients"
    payload2 = sample_ingestion_payload.copy()
    payload2["text"] = "Recipe 2: Bake in oven"

    api_client.post("/api/ingestions", json=payload1)
    api_client.post("/api/ingestions", json=payload2)

    response = api_client.get("/api/ingestions")

    assert response.status_code == 200

    data = response.json()
    assert "ingestions" in data
    assert "total" in data
    assert "skip" in data
    assert "limit" in data
    assert data["total"] >= 2
    assert len(data["ingestions"]) >= 2


@pytest.mark.integration
def test_list_ingestions_with_status_filter(api_client, sample_ingestion_payload):
    """GET /api/ingestions?status=pending filters by status."""
    # Create an ingestion
    api_client.post("/api/ingestions", json=sample_ingestion_payload)

    response = api_client.get("/api/ingestions?status=pending")

    assert response.status_code == 200

    data = response.json()
    assert all(ing["status"] == "pending" for ing in data["ingestions"])


@pytest.mark.integration
def test_list_ingestions_pagination(api_client, sample_ingestion_payload):
    """GET /api/ingestions respects skip and limit parameters."""
    # Create multiple ingestions with unique text
    for i in range(5):
        payload = sample_ingestion_payload.copy()
        payload["text"] = f"Recipe {i}: Unique recipe content"
        api_client.post("/api/ingestions", json=payload)

    # Test limit
    response = api_client.get("/api/ingestions?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["ingestions"]) <= 2
    assert data["limit"] == 2

    # Test skip
    response = api_client.get("/api/ingestions?skip=2&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["skip"] == 2


@pytest.mark.integration
def test_list_ingestions_limit_max(api_client):
    """GET /api/ingestions enforces max limit of 100."""
    response = api_client.get("/api/ingestions?limit=200")

    assert response.status_code == 422  # Validation error
