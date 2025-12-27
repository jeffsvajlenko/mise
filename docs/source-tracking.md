# Source Tracking & Deduplication

This document describes the source tracking system for recipe ingestion and deduplication.

## Overview

Every recipe can optionally be tagged with a **source** to track its origin and prevent duplicates when ingesting from external sources like YouTube, webpages, or photos.

## Database Schema

### Source Columns

Added to the `recipes` table:

```sql
-- Type of source (e.g., 'youtube', 'webpage', 'photo', 'custom')
source_type VARCHAR(50) NULL

-- Unique identifier within that source type
source_key VARCHAR(500) NULL

-- Additional metadata (JSONB for flexibility)
source_metadata JSONB NULL
```

### Unique Constraint

A partial unique index prevents duplicate ingestion:

```sql
CREATE UNIQUE INDEX idx_recipe_source_unique
ON recipes(source_type, source_key)
WHERE source_type IS NOT NULL
  AND source_key IS NOT NULL
  AND deleted_at IS NULL;
```

This means:
- ✅ Can't create duplicate from same YouTube video
- ✅ Can't create duplicate from same webpage URL
- ✅ Can have multiple NULL sources (user-created without tracking)
- ✅ Soft-deleted recipes don't block new imports

## Source Types

### 1. YouTube (`youtube`)

**Source Key:** Video ID (11 characters)

```python
from mise.ingestion import SourceType, extract_youtube_video_id

video_id = extract_youtube_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ")
# Returns: "dQw4w9WgXcQ"

record, created = repo.upsert_from_source(
    recipe,
    source_type=SourceType.YOUTUBE,
    source_key=video_id,
    source_metadata={
        "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "channel_id": "UCxyz",
        "channel_name": "Channel Name",
        "uploaded_date": "2024-01-15",
        "duration_seconds": 420
    }
)
```

### 2. Webpage (`webpage`)

**Source Key:** Normalized URL

```python
from mise.ingestion import SourceType, normalize_url

url = normalize_url("https://www.example.com/recipes/pasta/")
# Returns: "https://example.com/recipes/pasta"

record, created = repo.upsert_from_source(
    recipe,
    source_type=SourceType.WEBPAGE,
    source_key=url,
    source_metadata={
        "scraped_at": "2024-01-15T10:30:00Z",
        "site_name": "Example Recipes",
        "author": "John Doe",
        "last_modified": "2024-01-10"
    }
)
```

### 3. Photo (`photo`)

**Source Key:** Perceptual image hash

```python
from mise.ingestion import SourceType

# Compute perceptual hash (e.g., using imagehash library)
image_hash = "a1b2c3d4e5f6g7h8"  # Example hash

record, created = repo.upsert_from_source(
    recipe,
    source_type=SourceType.PHOTO,
    source_key=image_hash,
    source_metadata={
        "file_path": "/uploads/recipe_photo_123.jpg",
        "ocr_confidence": 0.95,
        "extracted_at": "2024-01-15T11:00:00Z"
    }
)
```

### 4. Custom (`custom`)

**Source Key:** Recipe UUID (from business schema)

```python
from mise.ingestion import SourceType

# User-created recipe
recipe = Recipe(title="My Recipe", ...)

record, created = repo.upsert_from_source(
    recipe,
    source_type=SourceType.CUSTOM,
    source_key=str(recipe.id),  # Use the UUID from Recipe schema
    source_metadata=None  # Usually no metadata needed
)
```

## Repository Methods

### `find_by_source(source_type, source_key)`

Find an existing recipe by source:

```python
existing = repo.find_by_source("youtube", "dQw4w9WgXcQ")
if existing:
    print(f"Already have this recipe: {existing.recipe.title}")
```

### `create_from_source(recipe, source_type, source_key, source_metadata)`

Create a new recipe with source tracking:

```python
try:
    record = repo.create_from_source(
        recipe,
        source_type="youtube",
        source_key="VIDEO_ID",
        source_metadata={...}
    )
    repo.commit()
    print(f"Created: {record.id}")
except IntegrityError:
    print("Duplicate source!")
    repo.rollback()
```

### `upsert_from_source(recipe, source_type, source_key, source_metadata, update_if_exists)`

Create or update based on source (recommended):

```python
record, was_created = repo.upsert_from_source(
    recipe,
    source_type="youtube",
    source_key="VIDEO_ID",
    source_metadata={...},
    update_if_exists=True  # Update if exists, or False to skip update
)

if was_created:
    print(f"Created new recipe: {record.id}")
else:
    print(f"Found existing recipe: {record.id}")

repo.commit()
```

### `get_by_source_type(source_type, skip, limit)`

Get all recipes from a specific source:

```python
youtube_recipes = repo.get_by_source_type("youtube", skip=0, limit=100)
print(f"Found {len(youtube_recipes)} YouTube recipes")
```

## Source Normalization Utilities

Located in `mise.ingestion.source_utils`:

### `normalize_url(url)`

Normalizes URLs for consistent deduplication:
- Converts to lowercase
- Removes `www.` prefix
- Removes trailing slashes
- Removes URL fragments (#...)
- Keeps query parameters

```python
from mise.ingestion import normalize_url

normalize_url("https://WWW.Example.COM/recipes/pasta/#comments")
# Returns: "https://example.com/recipes/pasta"
```

### `extract_youtube_video_id(url)`

Extracts video ID from various YouTube URL formats:

```python
from mise.ingestion import extract_youtube_video_id

extract_youtube_video_id("https://youtube.com/watch?v=ABC123XYZ")
# Returns: "ABC123XYZ"

extract_youtube_video_id("https://youtu.be/ABC123XYZ")
# Returns: "ABC123XYZ"
```

### `create_source_key(source_type, identifier)`

Auto-normalizes based on source type:

```python
from mise.ingestion import create_source_key, SourceType

create_source_key(SourceType.YOUTUBE, "https://youtube.com/watch?v=ABC")
# Returns: "ABC" (extracted video ID)

create_source_key(SourceType.WEBPAGE, "https://WWW.site.com/recipe/")
# Returns: "https://site.com/recipe" (normalized URL)
```

## Migration

To add source tracking to an existing database:

```bash
# Apply migration
uv run python scripts/migrate_add_source_tracking.py

# Rollback (if needed)
uv run python scripts/migrate_add_source_tracking.py down
```

## Example Usage

See [scripts/example_source_tracking.py](../scripts/example_source_tracking.py) for a complete working example.

```bash
uv run python scripts/example_source_tracking.py
```

## Best Practices

1. **Always use source tracking for external sources** - Prevents duplicate ingestion
2. **Normalize identifiers** - Use utility functions for consistency
3. **Use upsert_from_source** - Handles both create and update cases
4. **Store useful metadata** - Include URLs, timestamps, confidence scores, etc.
5. **Handle IntegrityError** - Unique constraint violations indicate duplicates

## Ingestion Workflow Example

```python
from sqlalchemy.orm import Session
from mise.db.database import engine
from mise.repository import RecipeRepository
from mise.ingestion import SourceType, extract_youtube_video_id
from mise.schema.recipe import Recipe

def ingest_from_youtube(url: str, recipe_data: dict):
    """Ingest a recipe from YouTube, handling duplicates."""

    with Session(engine) as session:
        repo = RecipeRepository(session)

        # Extract video ID
        video_id = extract_youtube_video_id(url)
        if not video_id:
            raise ValueError(f"Invalid YouTube URL: {url}")

        # Check if already exists
        existing = repo.find_by_source(SourceType.YOUTUBE, video_id)
        if existing and not should_update(existing):
            print(f"Skipping duplicate: {existing.recipe.title}")
            return existing

        # Parse recipe
        recipe = Recipe(**recipe_data)

        # Upsert
        record, created = repo.upsert_from_source(
            recipe,
            source_type=SourceType.YOUTUBE,
            source_key=video_id,
            source_metadata={
                "url": url,
                "ingested_at": datetime.utcnow().isoformat(),
                # ... other metadata
            },
            update_if_exists=True
        )

        session.commit()

        action = "Created" if created else "Updated"
        print(f"{action}: {record.recipe.title}")
        return record

def should_update(existing_record):
    """Decide whether to update an existing recipe."""
    # Example: Update if older than 7 days
    age_days = (datetime.utcnow() - existing_record.updated_at).days
    return age_days > 7
```

## Querying by Source

```python
# Get all YouTube recipes
youtube_recipes = repo.get_by_source_type("youtube")

# Get statistics
from collections import Counter
sources = [r.source_type or "unknown" for r in repo.get_all_recipes()]
stats = Counter(sources)
print(f"YouTube: {stats['youtube']}, Webpage: {stats['webpage']}")

# Find specific recipe
recipe = repo.find_by_source("youtube", "VIDEO_ID")
if recipe:
    print(f"Metadata: {recipe.source_metadata}")
```

## Future Enhancements

Potential additions:

1. **Batch upsert** - Process multiple recipes efficiently
2. **Source priority** - Prefer certain sources over others
3. **Conflict resolution** - Merge recipes from multiple sources
4. **Source validation** - Verify source URLs still exist
5. **Source attribution** - Display source in UI/API responses
