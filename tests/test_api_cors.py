"""Tests for CORS configuration."""

import os
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_cors_disabled_by_default(setup_test_database):
    """CORS should be disabled when API_CORS_ORIGINS is not set."""
    from mise.api.main import create_app

    # Ensure no CORS configuration
    if "API_CORS_ORIGINS" in os.environ:
        del os.environ["API_CORS_ORIGINS"]

    app = create_app()
    client = TestClient(app)

    # Make a request with Origin header (simulates browser)
    response = client.get(
        "/api/health",
        headers={"Origin": "https://evil.com"}
    )

    # Response should succeed (API works)
    assert response.status_code == 200

    # But no CORS headers should be present (browser would block)
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.integration
def test_cors_enabled_with_specific_origin(setup_test_database):
    """CORS should allow only configured origins."""
    from mise.api.main import create_app

    # Configure specific origin
    os.environ["API_CORS_ORIGINS"] = "https://mise.elidibus.com"

    app = create_app()
    client = TestClient(app)

    # Request from allowed origin
    response = client.get(
        "/api/health",
        headers={"Origin": "https://mise.elidibus.com"}
    )

    assert response.status_code == 200
    # CORS header should match the allowed origin
    assert response.headers["access-control-allow-origin"] == "https://mise.elidibus.com"

    # Cleanup
    del os.environ["API_CORS_ORIGINS"]


@pytest.mark.integration
def test_cors_blocks_unauthorized_origin(setup_test_database):
    """CORS should not allow origins not in the list."""
    from mise.api.main import create_app

    # Configure specific origin
    os.environ["API_CORS_ORIGINS"] = "https://mise.elidibus.com"

    app = create_app()
    client = TestClient(app)

    # Request from different origin
    response = client.get(
        "/api/health",
        headers={"Origin": "https://evil.com"}
    )

    # API still works (server doesn't block)
    assert response.status_code == 200

    # But CORS header should not allow evil.com
    # Browser would block this based on CORS policy
    if "access-control-allow-origin" in response.headers:
        assert response.headers["access-control-allow-origin"] != "https://evil.com"

    # Cleanup
    del os.environ["API_CORS_ORIGINS"]


@pytest.mark.integration
def test_cors_multiple_origins(setup_test_database):
    """CORS should support multiple configured origins."""
    from mise.api.main import create_app

    # Configure multiple origins
    os.environ["API_CORS_ORIGINS"] = "https://mise.elidibus.com,https://www.elidibus.com"

    app = create_app()
    client = TestClient(app)

    # Test first origin
    response1 = client.get(
        "/api/health",
        headers={"Origin": "https://mise.elidibus.com"}
    )
    assert response1.status_code == 200
    assert response1.headers["access-control-allow-origin"] == "https://mise.elidibus.com"

    # Test second origin
    response2 = client.get(
        "/api/health",
        headers={"Origin": "https://www.elidibus.com"}
    )
    assert response2.status_code == 200
    assert response2.headers["access-control-allow-origin"] == "https://www.elidibus.com"

    # Cleanup
    del os.environ["API_CORS_ORIGINS"]


@pytest.mark.integration
def test_cors_preflight_request(setup_test_database):
    """CORS preflight (OPTIONS) requests should work when CORS is enabled."""
    from mise.api.main import create_app

    # Configure CORS
    os.environ["API_CORS_ORIGINS"] = "https://mise.elidibus.com"

    app = create_app()
    client = TestClient(app)

    # Preflight request
    response = client.options(
        "/api/recipes",
        headers={
            "Origin": "https://mise.elidibus.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key"
        }
    )

    # Should return 200 OK
    assert response.status_code == 200

    # Should include CORS headers
    assert "access-control-allow-origin" in response.headers
    assert "access-control-allow-methods" in response.headers
    assert "access-control-allow-headers" in response.headers

    # Cleanup
    del os.environ["API_CORS_ORIGINS"]
