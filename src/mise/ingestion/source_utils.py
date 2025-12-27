"""Utilities for handling recipe source tracking."""
from enum import Enum
from urllib.parse import urlparse, urlunparse
import re


class SourceType(str, Enum):
    """Supported source types for recipes."""
    CUSTOM = "custom"
    YOUTUBE = "youtube"
    WEBPAGE = "webpage"
    PHOTO = "photo"


def normalize_url(url: str) -> str:
    """
    Normalize a URL for consistent deduplication.

    Removes:
    - URL fragments (#...)
    - Query parameters (except for important ones like YouTube video IDs)
    - Trailing slashes
    - www. prefix
    - Converts to lowercase

    Args:
        url: Original URL

    Returns:
        Normalized URL string
    """
    parsed = urlparse(url.lower().strip())

    # Remove www. from hostname
    hostname = parsed.hostname or ""
    if hostname.startswith("www."):
        hostname = hostname[4:]

    # Reconstruct URL without fragment and with normalized hostname
    normalized = urlunparse((
        parsed.scheme,
        hostname + (f":{parsed.port}" if parsed.port else ""),
        parsed.path.rstrip("/"),
        parsed.params,
        parsed.query,  # Keep query params for now
        ""  # Remove fragment
    ))

    return normalized


def extract_youtube_video_id(url: str) -> str | None:
    """
    Extract YouTube video ID from various URL formats.

    Supports:
    - https://youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://m.youtube.com/watch?v=VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID

    Args:
        url: YouTube URL

    Returns:
        Video ID if found, None otherwise
    """
    # Pattern for various YouTube URL formats
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def create_source_key(source_type: SourceType, identifier: str) -> str:
    """
    Create a normalized source key based on source type.

    Args:
        source_type: Type of source
        identifier: Raw identifier (URL, video ID, hash, etc.)

    Returns:
        Normalized source key
    """
    if source_type == SourceType.YOUTUBE:
        # For YouTube, try to extract video ID
        video_id = extract_youtube_video_id(identifier)
        return video_id if video_id else identifier

    elif source_type == SourceType.WEBPAGE:
        # For webpages, normalize the URL
        return normalize_url(identifier)

    elif source_type == SourceType.PHOTO:
        # For photos, assume identifier is already a hash
        return identifier.lower()

    elif source_type == SourceType.CUSTOM:
        # For custom, just return as-is (likely a UUID)
        return identifier

    # Default: return identifier
    return identifier
