"""Tests for API key authentication."""

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_client(setup_test_database):
    """
    Create a test client with API key authentication enabled.

    Unlike the standard api_client fixture, this one requires authentication.
    """
    from mise.api.main import create_app

    # Set up API key for testing
    os.environ["API_KEYS"] = "test-key-123,test-key-456"

    app = create_app()
    client = TestClient(app)

    yield client

    # Cleanup
    if "API_KEYS" in os.environ:
        del os.environ["API_KEYS"]


@pytest.mark.integration
def test_health_endpoint_public(auth_client):
    """Health endpoint should be accessible without authentication."""
    response = auth_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.integration
def test_missing_api_key(auth_client):
    """Requests without API key should return 401."""
    response = auth_client.get("/api/recipes")

    assert response.status_code == 401
    assert "Missing API key" in response.json()["detail"]


@pytest.mark.integration
def test_invalid_api_key(auth_client):
    """Requests with invalid API key should return 403."""
    response = auth_client.get(
        "/api/recipes",
        headers={"X-API-Key": "invalid-key"}
    )

    assert response.status_code == 403
    assert "Invalid API key" in response.json()["detail"]


@pytest.mark.integration
def test_valid_api_key(auth_client):
    """Requests with valid API key should be allowed."""
    response = auth_client.get(
        "/api/recipes",
        headers={"X-API-Key": "test-key-123"}
    )

    # Should return 200 with empty list (no recipes in DB)
    assert response.status_code == 200
    data = response.json()
    assert "recipes" in data


@pytest.mark.integration
def test_multiple_valid_keys(auth_client):
    """Both configured API keys should work."""
    # Test first key
    response1 = auth_client.get(
        "/api/recipes",
        headers={"X-API-Key": "test-key-123"}
    )
    assert response1.status_code == 200

    # Test second key
    response2 = auth_client.get(
        "/api/recipes",
        headers={"X-API-Key": "test-key-456"}
    )
    assert response2.status_code == 200


@pytest.mark.integration
def test_all_protected_endpoints_require_auth(auth_client):
    """All non-health endpoints should require authentication."""
    protected_endpoints = [
        "/api/recipes",
        "/api/ingestions",
        "/api/files/test.jpg",
    ]

    for endpoint in protected_endpoints:
        response = auth_client.get(endpoint)
        assert response.status_code == 401, f"Endpoint {endpoint} should require auth"


@pytest.mark.integration
def test_development_mode_no_auth(setup_test_database):
    """When API_KEYS is not set, authentication is disabled."""
    from mise.api.main import create_app

    # Ensure API_KEYS is not set (development mode)
    if "API_KEYS" in os.environ:
        del os.environ["API_KEYS"]

    app = create_app()
    client = TestClient(app)

    # Should be able to access without auth in development mode
    response = client.get("/api/recipes")
    assert response.status_code == 200
