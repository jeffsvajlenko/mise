"""File serving endpoints."""

import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/{file_path:path}")
def serve_file(file_path: str) -> FileResponse:
    """
    Serve recipe files (images, etc.).

    Args:
        file_path: Relative path from storage root (e.g., recipes/uuid/filename.jpg)

    Returns:
        FileResponse: File with appropriate Content-Type

    Raises:
        HTTPException: 404 if file not found, 400 if path invalid
    """
    # Get file storage path from environment
    from mise.config import load_env

    load_env()
    storage_path = os.getenv("FILE_STORAGE_PATH", "./data/files")

    # Construct full path
    full_path = Path(storage_path) / file_path

    # Security: Prevent directory traversal
    try:
        full_path = full_path.resolve()
        storage_root = Path(storage_path).resolve()

        if not str(full_path).startswith(str(storage_root)):
            raise HTTPException(status_code=400, detail="Invalid file path")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file path")

    # Check if file exists
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type from extension
    content_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".pdf": "application/pdf",
    }

    extension = full_path.suffix.lower()
    media_type = content_type_map.get(extension, "application/octet-stream")

    return FileResponse(path=full_path, media_type=media_type)
