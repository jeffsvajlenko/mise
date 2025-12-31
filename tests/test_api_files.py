"""Tests for file serving API endpoint."""

import pytest
from pathlib import Path


@pytest.fixture
def test_image_file(tmp_path):
    """
    Create a test image file and return its path.

    Creates a simple test file structure.
    """
    import os

    # Override FILE_STORAGE_PATH for this test
    storage_path = tmp_path / "files"
    storage_path.mkdir(parents=True, exist_ok=True)

    # Create test directory structure: recipes/{uuid}/file.jpg
    recipe_dir = storage_path / "recipes" / "test-uuid-123"
    recipe_dir.mkdir(parents=True, exist_ok=True)

    # Create a dummy image file
    image_file = recipe_dir / "test_image.jpg"
    image_file.write_bytes(b"fake jpeg data")

    # Set environment variable
    os.environ["FILE_STORAGE_PATH"] = str(storage_path)

    yield storage_path, "recipes/test-uuid-123/test_image.jpg"

    # Cleanup
    if "FILE_STORAGE_PATH" in os.environ:
        del os.environ["FILE_STORAGE_PATH"]


@pytest.mark.integration
def test_serve_image_file(api_client, test_image_file):
    """GET /api/files/{path} serves image with correct content-type."""
    storage_path, file_path = test_image_file

    response = api_client.get(f"/api/files/{file_path}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"fake jpeg data"


@pytest.mark.integration
def test_serve_file_not_found(api_client, test_image_file):
    """GET /api/files/{path} returns 404 for non-existent file."""
    response = api_client.get("/api/files/recipes/nonexistent/file.jpg")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.integration
def test_serve_file_path_traversal_blocked(api_client, test_image_file):
    """GET /api/files/{path} blocks directory traversal attempts."""
    # Try to escape the storage directory
    response = api_client.get("/api/files/../../etc/passwd")

    # Should return error (either 400 invalid path or 404 not found after security check)
    assert response.status_code in (400, 404)
    assert "detail" in response.json()


@pytest.mark.integration
def test_serve_file_content_types(api_client, tmp_path):
    """GET /api/files/{path} returns correct MIME types for different extensions."""
    import os

    # Setup storage
    storage_path = tmp_path / "files"
    storage_path.mkdir(parents=True, exist_ok=True)
    os.environ["FILE_STORAGE_PATH"] = str(storage_path)

    # Create test files with different extensions
    test_files = {
        "test.jpg": ("image/jpeg", b"jpg data"),
        "test.png": ("image/png", b"png data"),
        "test.gif": ("image/gif", b"gif data"),
        "test.webp": ("image/webp", b"webp data"),
        "test.pdf": ("application/pdf", b"pdf data"),
    }

    file_dir = storage_path / "test"
    file_dir.mkdir(parents=True, exist_ok=True)

    for filename, (expected_type, content) in test_files.items():
        file_path = file_dir / filename
        file_path.write_bytes(content)

        response = api_client.get(f"/api/files/test/{filename}")

        assert response.status_code == 200
        assert response.headers["content-type"] == expected_type
        assert response.content == content

    # Cleanup
    if "FILE_STORAGE_PATH" in os.environ:
        del os.environ["FILE_STORAGE_PATH"]
