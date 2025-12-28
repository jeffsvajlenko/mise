# File Storage System

## Overview

The file storage system uses a **hybrid approach**: files on disk, metadata in database JSONB fields. This provides the simplicity of filesystem storage with the power of database queries for metadata.

## Architecture

### Storage Structure

**Development** (`./data/files/`):
```
./data/files/
  recipes/
    55/                    # Shard level 1 (first 2 UUID chars)
      0e/                  # Shard level 2 (next 2 UUID chars)
        550e8400-e29b-41d4-a716-446655440000/  # Recipe directory
          original_1.jpg      # First uploaded photo
          original_2.jpg      # Second uploaded photo
          original_3.jpg      # Third uploaded photo
          thumbnail.jpg       # Generated thumbnail
  ingestion-temp/
    ing_{ingestion_id}/
      transcript.srt      # Temporary processing files
      video_frame.jpg     # Frame capture
      raw_data.json       # AI extraction output
```

**Production** (`/data/mise/files/`):
```
/data/mise/files/
  recipes/
    7d/
      56/
        7d5690cb-758d-48a6-b710-bc4f8a8e4f96/
          original_1.jpg
          original_2.jpg
  ingestion-temp/
    ing_{ingestion_id}/
      transcript.srt
```

**Sharding Benefits:**
- Scales to millions of recipes without filesystem performance degradation
- 65,536 shard buckets (16² × 16²) distribute recipes evenly
- Each shard bucket has ~15 recipes for 1M total recipes
- Fast directory operations even at scale

### Database Metadata

File metadata is stored in the `source_files` JSONB column of the `recipes` table:

```json
[
  {
    "id": "original_1",
    "path": "recipes/550e8400-e29b-41d4-a716-446655440000/original_1.jpg",
    "filename": "grandmas-recipe.jpg",
    "content_type": "image/jpeg",
    "size_bytes": 1234567,
    "width": 1920,
    "height": 1080,
    "uploaded_at": "2025-12-27T17:30:00Z"
  }
]
```

## Key Design Decisions

### Why Filesystem Instead of Object Storage?

- **Simplicity**: No extra service to run (MinIO, S3)
- **Homelab-friendly**: Just a directory mount
- **Cost**: Zero external service costs
- **Performance**: Local disk access is fast
- **Backup**: Standard filesystem backup tools work

### Why JSONB Metadata Instead of Separate Table?

- **No joins needed**: All file info loaded with recipe
- **Flexible schema**: Easy to add new metadata fields
- **GIN indexing**: Can search by content_type, size, etc.
- **Simpler queries**: One model, one query

### Why Not Store Everything in Filesystem?

Without database metadata you'd need to:
- Read every file to determine MIME type
- Parse image headers for dimensions
- Track original filenames separately
- Can't query "all recipes with images over 2MB"

Database metadata provides **queryability** and **performance**.

### Why UUID Sharding?

**Problem:** Filesystem performance degrades with 10,000+ files in a single directory

**Solution:** 2-level UUID prefix sharding creates 65,536 buckets

**Benefits:**
- Scales to millions of recipes
- Fast directory operations (ls, find, etc.)
- Even distribution (UUIDs are randomly generated)
- Still human-browsable

**Example:** Recipe `550e8400-e29b-41d4-a716-446655440000`
- Shard 1: `55` (first 2 chars)
- Shard 2: `0e` (next 2 chars)
- Path: `recipes/55/0e/550e8400-.../`

### Portable Exports (Future)

The sharded directory structure enables **complete, portable recipe exports**:

```
recipes/55/0e/550e8400-.../
  original_1.jpg          # Photo 1
  original_2.jpg          # Photo 2
  recipe.json            # Complete recipe data (JSONB export)
  metadata.json          # Source info, timestamps
```

**Benefits:**
- **Self-contained**: All recipe data in one directory
- **Portable**: Copy directory = copy recipe
- **Backup-friendly**: Standard filesystem tools work
- **Import/export**: `rsync` a directory to move recipes between systems
- **Human-readable**: Can inspect recipe without database

**Example export:**
```bash
# Export single recipe (future feature)
mise export recipe 550e8400-... --output=/backup/

# Result:
/backup/55/0e/550e8400-.../
  recipe.json
  original_1.jpg
  original_2.jpg
```

## Configuration

The file storage path is configured via environment variables:

```bash
# .env.development (local development)
FILE_STORAGE_PATH=./data/files

# .env.production (homelab deployment)
FILE_STORAGE_PATH=/data/mise/files
```

**Development**: Uses `./data/files/` relative to project root, git-ignored except for `.gitkeep`

**Production**: Uses absolute path `/data/mise/files/` for system-wide storage

## Usage Examples

### Saving a Recipe Photo

```python
from mise.storage.files import get_default_storage
from mise.db.models import RecipeDbModel
from mise.repository.recipe import RecipeRepository

# Initialize storage
storage = get_default_storage()

# Save file and get metadata
with open("grandmas-recipe.jpg", "rb") as f:
    metadata = storage.save_recipe_file(
        recipe_uuid=recipe.uuid,
        file=f,
        original_filename="grandmas-recipe.jpg"
    )

# Metadata returned:
# {
#   "id": "original_1",
#   "path": "recipes/550e8400-.../original_1.jpg",
#   "filename": "grandmas-recipe.jpg",
#   "content_type": "image/jpeg",
#   "size_bytes": 1234567,
#   "width": 1920,
#   "height": 1080,
#   "uploaded_at": "2025-12-27T17:30:00Z"
# }

# Store metadata in database
recipe.source_files = [metadata]
session.commit()
```

### Multiple Photos for One Recipe

```python
photos = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
metadata_list = []

for photo_path in photos:
    with open(photo_path, "rb") as f:
        metadata = storage.save_recipe_file(
            recipe_uuid=recipe.uuid,
            file=f,
            original_filename=photo_path
        )
        metadata_list.append(metadata)

# Store all metadata
recipe.source_files = metadata_list
session.commit()
```

### Saving Temporary Ingestion Files

```python
# Save transcript during ingestion processing
with open("transcript.srt", "rb") as f:
    temp_path = storage.save_temp_file(
        ingestion_id=ingestion.id,
        file=f,
        filename="transcript.srt"
    )

# Use temp file for processing
# ...

# Clean up after completion
storage.delete_temp_files(ingestion.id)
```

### Serving Files via HTTP

```python
from flask import send_file

@app.route("/recipes/<uuid:recipe_uuid>/files/<file_id>")
def serve_recipe_file(recipe_uuid, file_id):
    # Get recipe from database
    recipe = recipe_repo.get_by_uuid(recipe_uuid)

    # Find file metadata
    file_meta = next(
        (f for f in recipe.source_files if f["id"] == file_id),
        None
    )

    if not file_meta:
        abort(404)

    # Get file path
    file_path = storage.get_file_path(file_meta["path"])

    # Serve with correct content type
    return send_file(
        file_path,
        mimetype=file_meta["content_type"],
        download_name=file_meta["filename"]
    )
```

### Querying by File Metadata

Using PostgreSQL JSONB operators:

```python
from sqlalchemy import func, cast
from sqlalchemy.dialects.postgresql import JSONB

# Find all recipes with JPEG images
stmt = select(RecipeDbModel).where(
    func.jsonb_path_exists(
        RecipeDbModel.source_files,
        '$[*] ? (@.content_type == "image/jpeg")'
    )
)

# Find recipes with large images (>2MB)
stmt = select(RecipeDbModel).where(
    func.jsonb_path_exists(
        RecipeDbModel.source_files,
        '$[*] ? (@.size_bytes > 2000000)'
    )
)

# Find recipes with high-resolution images
stmt = select(RecipeDbModel).where(
    func.jsonb_path_exists(
        RecipeDbModel.source_files,
        '$[*] ? (@.width > 1920)'
    )
)
```

## File Lifecycle

### Recipe Files (Permanent)

1. **Upload**: User uploads photo → saved to `recipes/{uuid}/original_N.jpg`
2. **Metadata**: Extracted (MIME, size, dimensions) → stored in `source_files`
3. **Retention**: Kept forever (or until recipe deleted)
4. **Deletion**: When recipe soft-deleted, files remain (for recovery)
   - Hard delete: Call `storage.delete_recipe_files(uuid)` to purge

### Temporary Ingestion Files

1. **Download**: Worker downloads YouTube transcript → `ingestion-temp/ing_123/transcript.srt`
2. **Process**: AI extraction uses transcript
3. **Cleanup**: After completion, call `storage.delete_temp_files(123)`
4. **Retention**: Could keep for 7-90 days for debugging, then purge

## Storage Management

### Disk Space Monitoring

```python
import shutil

def get_storage_stats(storage: FileStorage):
    """Get disk usage statistics."""
    total, used, free = shutil.disk_usage(storage.base_path)

    return {
        "total_gb": total // (2**30),
        "used_gb": used // (2**30),
        "free_gb": free // (2**30),
        "percent_used": (used / total) * 100
    }
```

### Cleanup Old Temporary Files

```python
from datetime import datetime, timedelta
from mise.repository.ingestion import IngestionRepository

def cleanup_old_temp_files(days: int = 90):
    """Delete temporary files older than N days."""
    cutoff = datetime.now() - timedelta(days=days)

    with Session(engine) as session:
        repo = IngestionRepository(session)

        # Find old completed ingestions
        old_ingestions = session.scalars(
            select(IngestionRequest)
            .where(
                IngestionRequest.status == "completed",
                IngestionRequest.completed_at < cutoff
            )
        ).all()

        storage = get_default_storage()
        for ing in old_ingestions:
            storage.delete_temp_files(ing.id)
            print(f"Deleted temp files for ingestion #{ing.id}")
```

### Orphaned File Detection

```python
def find_orphaned_files(storage: FileStorage):
    """Find recipe files without database records."""
    recipes_dir = storage.base_path / "recipes"

    with Session(engine) as session:
        # Get all recipe UUIDs from database
        db_uuids = set(
            session.scalars(
                select(RecipeDbModel.uuid)
            ).all()
        )

        # Check filesystem
        orphans = []
        for recipe_dir in recipes_dir.iterdir():
            if recipe_dir.is_dir():
                try:
                    uuid_obj = UUID(recipe_dir.name)
                    if uuid_obj not in db_uuids:
                        orphans.append(recipe_dir)
                except ValueError:
                    # Invalid UUID directory
                    orphans.append(recipe_dir)

        return orphans
```

## Image Processing (Future)

### Thumbnail Generation

```python
from PIL import Image

def generate_thumbnail(
    storage: FileStorage,
    recipe_uuid: UUID,
    source_file_id: str,
    size: tuple[int, int] = (300, 300)
) -> FileMetadata:
    """Generate thumbnail from original image."""
    # Get recipe
    recipe = recipe_repo.get_by_uuid(recipe_uuid)

    # Find source file
    source = next(f for f in recipe.source_files if f["id"] == source_file_id)
    source_path = storage.get_file_path(source["path"])

    # Generate thumbnail
    with Image.open(source_path) as img:
        img.thumbnail(size)

        # Save thumbnail
        recipe_dir = storage.base_path / "recipes" / str(recipe_uuid)
        thumb_path = recipe_dir / "thumbnail.jpg"
        img.save(thumb_path, "JPEG", quality=85)

    # Create metadata
    thumb_meta = FileMetadata(
        id="thumbnail",
        path=str(thumb_path.relative_to(storage.base_path)),
        filename="thumbnail.jpg",
        content_type="image/jpeg",
        size_bytes=thumb_path.stat().st_size,
        width=size[0],
        height=size[1],
        uploaded_at=datetime.now(timezone.utc).isoformat()
    )

    # Add to recipe
    recipe.source_files.append(thumb_meta)
    session.commit()

    return thumb_meta
```

## Deployment

### Docker Volume Mount

```yaml
# docker-compose.yml
services:
  app:
    volumes:
      - ./data/files:/data/mise/files
```

### Permissions

```bash
# Create directory with correct ownership
sudo mkdir -p /data/mise/files
sudo chown -R 1000:1000 /data/mise/files
sudo chmod -R 755 /data/mise/files
```

### Backup Strategy

```bash
#!/bin/bash
# Backup script for file storage

BACKUP_DIR="/backup/mise-files"
DATE=$(date +%Y%m%d)

# Create dated backup
rsync -av --delete \
  /data/mise/files/recipes/ \
  "$BACKUP_DIR/recipes-$DATE/"

# Keep last 30 days
find "$BACKUP_DIR" -type d -name "recipes-*" -mtime +30 -exec rm -rf {} \;
```

## Migration from Existing System

If you have existing files stored differently:

```python
def migrate_existing_files():
    """Migrate files from old storage to new structure."""
    storage = get_default_storage()

    with Session(engine) as session:
        recipes = session.scalars(select(RecipeDbModel)).all()

        for recipe in recipes:
            # If old system stored paths differently
            old_paths = recipe.data.get("image_paths", [])

            metadata_list = []
            for idx, old_path in enumerate(old_paths, 1):
                # Copy file to new location
                with open(old_path, "rb") as f:
                    metadata = storage.save_recipe_file(
                        recipe_uuid=recipe.uuid,
                        file=f,
                        original_filename=Path(old_path).name,
                        file_id=f"original_{idx}"
                    )
                    metadata_list.append(metadata)

            # Update recipe
            recipe.source_files = metadata_list

        session.commit()
```

## Summary

This file storage system provides:

- ✅ Simple filesystem storage (no external services)
- ✅ Rich metadata in database (MIME types, dimensions, sizes)
- ✅ Queryable (find recipes by image properties)
- ✅ Organized (UUID-based directories)
- ✅ Clean separation (permanent vs temporary files)
- ✅ Homelab-friendly (just a mounted directory)
- ✅ Future-proof (easy to migrate to S3 later if needed)

The hybrid approach gives you the best of both worlds: filesystem simplicity with database power.
