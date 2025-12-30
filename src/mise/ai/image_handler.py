"""Image handling utilities for Claude's vision API."""

import base64
from pathlib import Path
from PIL import Image


def load_image_as_base64(image_path: Path | str) -> dict:
    """
    Load an image file and convert to base64 for Claude's vision API.

    Automatically converts unsupported formats (like MPO, HEIC) to JPEG.

    Args:
        image_path: Path to the image file

    Returns:
        dict: Image data in Claude API format with keys:
            - type: "base64"
            - media_type: MIME type (e.g., "image/jpeg")
            - data: Base64-encoded image data

    Raises:
        FileNotFoundError: If image file doesn't exist
        ValueError: If file cannot be processed
    """
    from io import BytesIO

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # Try to open with PIL to handle format conversion
    try:
        with Image.open(image_path) as img:
            # Get original format
            original_format = img.format

            # Supported formats for Claude API
            supported_formats = {'JPEG', 'PNG', 'GIF', 'WEBP'}

            if original_format and original_format.upper() in supported_formats:
                # Format is supported, read file directly
                extension = image_path.suffix.lower()
                mime_type_map = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp'
                }
                media_type = mime_type_map.get(extension, 'image/jpeg')

                with open(image_path, 'rb') as f:
                    image_data = base64.standard_b64encode(f.read()).decode('utf-8')
            else:
                # Convert unsupported format (MPO, HEIC, BMP, etc.) to JPEG
                # Convert to RGB if needed (handles RGBA, P, etc.)
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')

                # Save to BytesIO as JPEG
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=95)
                buffer.seek(0)

                image_data = base64.standard_b64encode(buffer.read()).decode('utf-8')
                media_type = 'image/jpeg'

    except Exception as e:
        raise ValueError(f"Failed to process image: {e}")

    return {
        "type": "base64",
        "media_type": media_type,
        "data": image_data
    }


def get_image_dimensions(image_path: Path | str) -> tuple[int, int]:
    """
    Get image dimensions using PIL.

    Args:
        image_path: Path to the image file

    Returns:
        tuple[int, int]: (width, height) in pixels

    Raises:
        FileNotFoundError: If image file doesn't exist
    """
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with Image.open(image_path) as img:
        return img.size  # Returns (width, height)


def validate_image_for_api(image_path: Path | str) -> None:
    """
    Validate that an image meets Claude API requirements.

    Accepts any format that PIL can open (will be converted if needed).

    Args:
        image_path: Path to the image file

    Raises:
        FileNotFoundError: If image file doesn't exist
        ValueError: If image doesn't meet API requirements
    """
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # Check file size (Claude API limit is 5MB per image)
    # Note: After conversion, size may differ, but original shouldn't be too huge
    file_size = image_path.stat().st_size
    max_size = 10 * 1024 * 1024  # 10 MB threshold (will compress if needed)

    if file_size > max_size:
        raise ValueError(
            f"Image file too large: {file_size / (1024*1024):.2f}MB. "
            f"Maximum size is 10MB (will be compressed for API)."
        )

    # Verify image can be opened by PIL
    try:
        with Image.open(image_path) as img:
            # Just verify it's a valid image
            img.verify()
    except Exception as e:
        raise ValueError(f"Failed to open image (not a valid image file): {e}")
