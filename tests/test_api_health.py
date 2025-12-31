"""Tests for health check API endpoint."""

import pytest


@pytest.mark.integration
def test_health_check_success(api_client):
    """Health endpoint returns ok when database is connected."""
    response = api_client.get("/api/health")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"


@pytest.mark.integration
def test_health_check_structure(api_client):
    """Health endpoint returns expected response structure."""
    response = api_client.get("/api/health")

    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "database" in data
    assert isinstance(data["status"], str)
    assert isinstance(data["database"], str)
