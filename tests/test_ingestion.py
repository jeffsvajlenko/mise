"""Tests for ingestion utilities."""
import pytest

from mise.ingestion.source_utils import (
    normalize_url,
    extract_youtube_video_id,
    create_source_key,
    SourceType
)


@pytest.mark.unit
class TestURLNormalization:
    """Tests for URL normalization."""

    def test_normalize_basic_url(self):
        """Test normalizing a basic URL."""
        url = "https://example.com/recipe"
        normalized: str = normalize_url(url)

        assert normalized == "https://example.com/recipe"

    def test_remove_www_prefix(self):
        """Test that www. prefix is removed."""
        url = "https://www.example.com/recipe"
        normalized: str = normalize_url(url)

        assert normalized == "https://example.com/recipe"

    def test_remove_trailing_slash(self):
        """Test that trailing slashes are removed."""
        url = "https://example.com/recipe/"
        normalized: str = normalize_url(url)

        assert normalized == "https://example.com/recipe"

    def test_remove_fragment(self):
        """Test that URL fragments (#) are removed."""
        url = "https://example.com/recipe#comments"
        normalized: str = normalize_url(url)

        assert normalized == "https://example.com/recipe"

    def test_lowercase_conversion(self):
        """Test that URLs are converted to lowercase."""
        url = "https://EXAMPLE.COM/Recipe"
        normalized: str = normalize_url(url)

        assert normalized == "https://example.com/recipe"

    def test_youtube_url_preserved(self):
        """Test that YouTube video IDs are preserved in query params."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        normalized: str = normalize_url(url)

        assert "v=dqw4w9wgxcq" in normalized.lower()

    def test_duplicate_urls_normalize_same(self):
        """Test that different forms of same URL normalize identically."""
        urls = [
            "https://example.com/recipe",
            "https://www.example.com/recipe/",
            "https://EXAMPLE.com/recipe#top",
            "https://example.com/recipe/"
        ]

        normalized = [normalize_url(url) for url in urls]

        # All should normalize to the same value
        assert len(set(normalized)) == 1


@pytest.mark.unit
class TestYouTubeExtraction:
    """Tests for YouTube video ID extraction."""

    def test_extract_youtube_standard_url(self):
        """Test extracting video ID from standard YouTube URL."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        video_id: str | None = extract_youtube_video_id(url)

        assert video_id == "dQw4w9WgXcQ"

    def test_extract_youtube_short_url(self):
        """Test extracting video ID from youtu.be short URL."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        video_id: str | None = extract_youtube_video_id(url)

        assert video_id == "dQw4w9WgXcQ"

    def test_extract_youtube_mobile_url(self):
        """Test extracting video ID from mobile YouTube URL."""
        url = "https://m.youtube.com/watch?v=dQw4w9WgXcQ"
        video_id: str | None = extract_youtube_video_id(url)

        assert video_id == "dQw4w9WgXcQ"

    def test_extract_youtube_embed_url(self):
        """Test extracting video ID from embed URL."""
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        video_id: str | None = extract_youtube_video_id(url)

        assert video_id == "dQw4w9WgXcQ"

    def test_non_youtube_url_returns_none(self):
        """Test that non-YouTube URLs return None."""
        url = "https://example.com/video"
        video_id: str | None = extract_youtube_video_id(url)

        assert video_id is None


@pytest.mark.unit
class TestSourceKeyCreation:
    """Tests for source key creation."""

    def test_create_youtube_source_key_from_video_id(self):
        """Test creating source key from YouTube video ID."""
        source_key: str = create_source_key(SourceType.youtube, "dQw4w9WgXcQ")

        # Should return just the video ID
        assert source_key == "dQw4w9WgXcQ"

    def test_create_youtube_source_key_from_url(self):
        """Test creating source key from full YouTube URL."""
        source_key: str = create_source_key(
            SourceType.youtube,
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )

        # Should extract and return video ID
        assert source_key == "dQw4w9WgXcQ"

    def test_create_webpage_source_key(self):
        """Test creating source key for webpage."""
        source_key: str = create_source_key(
            SourceType.webpage,
            "https://example.com/recipe"
        )

        # Should normalize the URL
        assert source_key == "https://example.com/recipe"

    def test_create_custom_source_key(self):
        """Test creating source key for custom type."""
        source_key: str = create_source_key(SourceType.custom, "my-custom-id")

        # Should return as-is
        assert source_key == "my-custom-id"
