"""File storage utilities for managing recipe files.

This module handles:
- Saving files to disk with organized directory structure
- Extracting metadata (MIME type, dimensions, size)
- Generating file references for database storage
- Serving files with correct content types
"""

import os
import mimetypes
from pathlib import Path
from datetime import datetime, timezone
from typing import BinaryIO, TypedDict
from uuid import UUID

from mise.config import load_env


class FileMetadata(TypedDict):
    """Metadata for a stored file."""
    id: str  # File identifier (e.g., "original_1", "thumbnail")
    path: str  # Relative path from storage root
    filename: str  # Original filename
    content_type: str  # MIME type
    size_bytes: int  # File size
    width: int | None  # Image width (if applicable)
    height: int | None  # Image height (if applicable)
    uploaded_at: str  # ISO 8601 timestamp


class FileStorage:
    """Manages file storage on the filesystem."""

    def __init__(self, base_path: Path | str):
        """
        Initialize file storage.

        Args:
            base_path: Root directory for file storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_recipe_dir(self, recipe_uuid: UUID) -> Path:
        """
        Get the directory path for a recipe.

        Args:
            recipe_uuid: UUID of the recipe

        Returns:
            Path to recipe directory

        Example:
            recipes/550e8400-e29b-41d4-a716-446655440000/
        """
        uuid_str = str(recipe_uuid)
        return self.base_path / "recipes" / uuid_str

    def save_recipe_file(
        self,
        recipe_uuid: UUID,
        file: BinaryIO,
        original_filename: str,
        file_id: str | None = None,
    ) -> FileMetadata:
        """
        Save a file for a recipe.

        Args:
            recipe_uuid: UUID of the recipe
            file: File-like object to save
            original_filename: Original filename (for extension/metadata)
            file_id: Optional file identifier (e.g., "original_1", "thumbnail")
                    If not provided, auto-generates "original_N"

        Returns:
            FileMetadata dict with path, content type, size, etc.

        Example:
            >>> storage = FileStorage("/data/mise/files")
            >>> with open("photo.jpg", "rb") as f:
            ...     metadata = storage.save_recipe_file(
            ...         recipe_uuid=uuid4(),
            ...         file=f,
            ...         original_filename="photo.jpg"
            ...     )
            >>> metadata["path"]
            'recipes/550e8400-.../original_1.jpg'
        """
        # Create recipe directory
        recipe_dir = self._get_recipe_dir(recipe_uuid)
        recipe_dir.mkdir(parents=True, exist_ok=True)

        # Auto-generate file_id if not provided
        if file_id is None:
            file_id = self._next_original_id(recipe_dir)

        # Determine file extension
        ext = Path(original_filename).suffix.lower() or ".bin"
        if not ext.startswith("."):
            ext = f".{ext}"

        # Build file path
        filename = f"{file_id}{ext}"
        file_path = recipe_dir / filename
        relative_path = file_path.relative_to(self.base_path)

        # Write file
        content = file.read()
        file_path.write_bytes(content)

        # Extract metadata
        content_type = mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
        size_bytes = len(content)

        # Try to get image dimensions
        width, height = self._get_image_dimensions(file_path, content_type)

        return FileMetadata(
            id=file_id,
            path=str(relative_path),
            filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            width=width,
            height=height,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )

    def save_temp_file(
        self,
        ingestion_id: int,
        file: BinaryIO,
        filename: str,
    ) -> Path:
        """
        Save a temporary file for ingestion processing.

        These files are stored separately and can be purged after processing.

        Args:
            ingestion_id: ID of the ingestion request
            file: File-like object to save
            filename: Filename (with extension)

        Returns:
            Absolute path to saved file

        Example:
            >>> storage = FileStorage("/data/mise/files")
            >>> with open("transcript.srt", "rb") as f:
            ...     path = storage.save_temp_file(
            ...         ingestion_id=123,
            ...         file=f,
            ...         filename="transcript.srt"
            ...     )
            >>> str(path)
            '/data/mise/files/ingestion-temp/ing_123/transcript.srt'
        """
        # Create ingestion temp directory
        temp_dir = self.base_path / "ingestion-temp" / f"ing_{ingestion_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Write file
        file_path = temp_dir / filename
        file_path.write_bytes(file.read())

        return file_path

    def get_file_path(self, relative_path: str) -> Path:
        """
        Get absolute path for a relative file path.

        Args:
            relative_path: Relative path from storage root

        Returns:
            Absolute path to file

        Example:
            >>> storage = FileStorage("/data/mise/files")
            >>> path = storage.get_file_path("recipes/550e8400-.../original_1.jpg")
            >>> str(path)
            '/data/mise/files/recipes/550e8400-.../original_1.jpg'
        """
        return self.base_path / relative_path

    def delete_recipe_files(self, recipe_uuid: UUID) -> None:
        """
        Delete all files for a recipe.

        Args:
            recipe_uuid: UUID of the recipe

        Example:
            >>> storage = FileStorage("/data/mise/files")
            >>> storage.delete_recipe_files(uuid4())
        """
        recipe_dir = self._get_recipe_dir(recipe_uuid)
        if recipe_dir.exists():
            import shutil
            shutil.rmtree(recipe_dir)

    def delete_temp_files(self, ingestion_id: int) -> None:
        """
        Delete temporary files for an ingestion.

        Args:
            ingestion_id: ID of the ingestion request

        Example:
            >>> storage = FileStorage("/data/mise/files")
            >>> storage.delete_temp_files(123)
        """
        temp_dir = self.base_path / "ingestion-temp" / f"ing_{ingestion_id}"
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir)

    def _next_original_id(self, recipe_dir: Path) -> str:
        """
        Generate next original_N identifier.

        Args:
            recipe_dir: Recipe directory to check

        Returns:
            Next available ID (e.g., "original_1", "original_2")
        """
        if not recipe_dir.exists():
            return "original_1"

        # Find existing original_N files
        existing = [
            f.stem for f in recipe_dir.iterdir()
            if f.stem.startswith("original_")
        ]

        # Extract numbers
        numbers = []
        for name in existing:
            try:
                num = int(name.split("_")[1])
                numbers.append(num)
            except (IndexError, ValueError):
                continue

        # Return next number
        next_num = max(numbers, default=0) + 1
        return f"original_{next_num}"

    def _get_image_dimensions(
        self,
        file_path: Path,
        content_type: str
    ) -> tuple[int | None, int | None]:
        """
        Extract image dimensions if file is an image.

        Args:
            file_path: Path to image file
            content_type: MIME type

        Returns:
            Tuple of (width, height) or (None, None) if not an image
        """
        if not content_type.startswith("image/"):
            return None, None

        try:
            from PIL import Image
            with Image.open(file_path) as img:
                return img.width, img.height
        except Exception:
            # PIL not installed or not a valid image
            return None, None


def get_default_storage() -> FileStorage:
    """
    Get the default file storage instance.

    Reads storage path from environment or uses default.

    Returns:
        FileStorage instance

    Example:
        >>> storage = get_default_storage()
        >>> storage.base_path
        PosixPath('/data/mise/files')
    """
    load_env()
    storage_path = os.getenv("FILE_STORAGE_PATH", "/data/mise/files")
    return FileStorage(storage_path)
