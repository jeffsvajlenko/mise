# Ingestion System Implementation Summary

## What Was Implemented

We've successfully implemented a complete ingestion system with separate tables for recipes and ingestion processing, following Option 2 from the design document.

### Database Schema

#### 1. RecipeDbModel (Permanent Domain Data)
- **Purpose**: Store final recipes with reader-relevant source information
- **Permanent fields**:
  - `source_type`: Type of source (youtube, webpage, photo, custom)
  - `source_url`: Original URL (permanent reference for readers)
  - `source_files`: Array of permanent file paths (for photos/images)
  - `source_metadata`: Original metadata before AI cleanup (author, title, etc.)
  - `data`: Complete recipe data (JSONB)

#### 2. IngestionRequest (Processing Queue Data)
- **Purpose**: Background job queue for processing ingestions
- **Queue management**:
  - `status`: pending, processing, completed, failed, cancelled
  - `priority`: Higher number = processed first
  - `worker_id`: ID of worker processing this job
  - `retry_count` / `max_retries`: Automatic retry logic
- **Deduplication**:
  - `source_key`: Unique constraint prevents duplicate ingestions
- **Processing data** (can be purged after 90 days):
  - `request_params`: Original request parameters
  - `processing_metadata`: Downloads, AI calls, logs, errors (JSONB)
- **Linking**:
  - `recipe_id`: Foreign key to created recipe (NULL until completed)
  - Bidirectional relationship with RecipeDbModel

### Repository Layer

#### IngestionRepository

Provides queue-based operations:

**Core Methods**:
- `create_request()` - Submit new ingestion request
- `find_by_source_key()` - Check if source already ingested
- `get_next_pending()` - Atomic job claiming with row locking (`SELECT FOR UPDATE SKIP LOCKED`)
- `update_status()` - Update processing status and metadata
- `mark_completed()` - Link completed ingestion to recipe
- `mark_failed()` - Handle failures with retry logic
- `get_pending_count()` / `get_processing_count()` - Queue stats

**Key Features**:
- **Atomic job claiming**: Uses PostgreSQL row-level locking to prevent race conditions
- **Priority queue**: Jobs ordered by priority (DESC) then FIFO
- **Automatic retry**: Failed jobs can auto-retry up to `max_retries`
- **Error tracking**: All errors logged in `processing_metadata.errors` array

### Data Flow

```
User submits URL
    ↓
Create IngestionRequest (status=pending)
    ↓
Worker claims job atomically (status=processing, worker_id set)
    ↓
Worker downloads content (transcript, images, etc.)
    ↓
Worker runs AI extraction
    ↓
Worker creates RecipeDbModel with:
    - Permanent source info (url, files, metadata)
    - Cleaned recipe data
    ↓
Link: IngestionRequest.recipe_id → Recipe.id
    ↓
Mark IngestionRequest as completed
```

### File Storage Strategy

**Implementation**: Hybrid filesystem + database metadata approach (see [docs/file-storage.md](file-storage.md))

**Permanent Files** (tied to Recipe UUID with sharding):

Development (`./data/files/`):
```
./data/files/recipes/55/0e/550e8400-.../
    original_1.jpg    # Original photo
    original_2.jpg    # Additional photos
    thumbnail.jpg     # Generated thumbnail
```

Production (`/data/mise/files/`):
```
/data/mise/files/recipes/7d/56/7d5690cb-.../
    original_1.jpg
    original_2.jpg
    thumbnail.jpg
```

Files are sharded by UUID prefix (first 4 chars = 65,536 buckets) for scalability.

**Temporary Files** (tied to Ingestion ID, can purge):
```
{storage_path}/ingestion-temp/ing_{ingestion_id}/
    transcript.srt    # Downloaded transcript
    video.mp4         # Temporary video file
    extracted_frames/ # Frame captures for analysis
```

**File Metadata** (stored in `source_files` JSONB):
```json
[
  {
    "id": "original_1",
    "path": "recipes/550e8400-.../original_1.jpg",
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

### 1. Separate Tables (Not Single Table)
**Why**: Clean separation of concerns
- Recipe = final domain model (keep forever)
- Ingestion = processing queue (can purge old data)
- Allows tracking multiple ingestion attempts per recipe
- Better for queue operations (indexes, locking, etc.)

### 2. Bidirectional Relationship (Not Just FK)
**Why**: Pythonic and convenient
- `recipe.ingestions` - See all attempts to create this recipe
- `ingestion.recipe` - Easy access to created recipe
- SQLAlchemy handles loading automatically

### 3. No Revisions (Initially)
**Why**: Keep it simple for MVP
- Just track `updated_at` timestamp
- Can add audit log later if needed
- Full revision history overkill for homelab

### 4. Source Info on Both Tables
**Why**: Different purposes
- Recipe: Reader-relevant (permanent)
- Ingestion: Deduplication checking (can be purged)
- Duplication is OK - they serve different needs

## Migration

Generated and applied initial migration:
- Creates `ingestion_requests` table
- Updates `recipes` table with new source fields
- Removes old `source_key` from recipes (moved to ingestions)
- Creates indexes for queue performance

Migration file: `alembic/versions/f15b236cec7b_initial_schema_with_recipes_and_.py`

## Example Usage

See `scripts/example_ingestion_workflow.py` for complete example showing:
1. Creating ingestion request
2. Worker claiming job (atomic)
3. Processing (downloads, AI extraction)
4. Creating recipe
5. Linking ingestion → recipe
6. Verifying bidirectional relationship

### Quick Example

```python
from sqlalchemy.orm import Session
from mise.db.database import engine
from mise.repository.ingestion import IngestionRepository

with Session(engine) as session:
    repo = IngestionRepository(session)

    # Submit ingestion request
    request = repo.create_request(
        source_type="youtube",
        source_key="youtube:VIDEO_ID",
        source_url="https://youtube.com/watch?v=VIDEO_ID",
        priority=0
    )
    session.commit()

    # Worker claims next job (atomic!)
    job = repo.get_next_pending("worker-1")
    if job:
        # Process job...
        repo.update_status(job.id, "processing", processing_metadata={...})
        session.commit()

        # Create recipe...
        recipe = RecipeDbModel(...)
        session.add(recipe)
        session.flush()

        # Link and complete
        repo.mark_completed(job.id, recipe.id)
        session.commit()
```

## Database Indexes

### Recipes
- `idx_recipe_name` - JSONB name field (partial: not deleted)
- `idx_recipe_cuisine` - JSONB cuisine field (partial: not deleted)
- `idx_recipe_data_gin` - Full JSONB search (GIN index)
- `ix_recipes_uuid` - UUID lookup

### Ingestion Requests
- `idx_ingestion_queue` - Composite (status, priority DESC, requested_at)
  - Partial index: only pending/processing
  - Optimized for queue queries
- `ix_ingestion_requests_source_type` - Filter by type
- `ix_ingestion_requests_status` - Filter by status
- `ix_ingestion_requests_recipe_id` - Find by recipe
- `ix_ingestion_requests_uuid` - UUID lookup
- `UNIQUE(source_key)` - Prevent duplicates

## Next Steps

### Immediate
- [x] Models implemented
- [x] Migration created and applied
- [x] Repository layer complete
- [x] Example script working

### Future Enhancements

1. **Background Worker**
   - Standalone worker process
   - Polls `get_next_pending()` in loop
   - Handles YouTube downloads, AI extraction
   - Auto-retries on failure

2. **Source Utilities**
   - Expand `source_utils.py` for more source types
   - Add image hash calculation
   - Add URL normalization
   - Add webpage screenshot capture

3. **Monitoring**
   - Dashboard showing queue stats
   - Failed job alerts
   - Processing time metrics
   - Cost tracking (AI tokens, storage)

4. **Cleanup Jobs**
   - Purge completed ingestions after 90 days
   - Archive to cold storage
   - Clean up temporary files

5. **Advanced Features**
   - Webhook callbacks on completion
   - Priority queue for premium users
   - Batch processing
   - Scheduled re-ingestion with newer AI models

## Files Modified/Created

### Created
- `src/mise/db/models.py` - Added `IngestionRequest` model
- `src/mise/repository/ingestion.py` - Ingestion repository
- `src/mise/storage/files.py` - File storage utilities
- `scripts/example_ingestion_workflow.py` - Working example (ingestion)
- `scripts/example_file_storage.py` - Working example (file storage)
- `docs/ingestion-design-v2.md` - Design document
- `docs/file-storage.md` - File storage documentation
- `docs/ingestion-implementation-summary.md` - This file
- `alembic/versions/f15b236cec7b_*.py` - Migration

### Modified
- `src/mise/db/models.py` - Updated `RecipeDbModel` with source fields
- `src/mise/repository/__init__.py` - Cleaned up exports
- `.env.development` - Added `FILE_STORAGE_PATH`
- `.env.production` - Added `FILE_STORAGE_PATH`
- `.env.example` - Added `FILE_STORAGE_PATH`

## Testing

### Ingestion Workflow Example

```bash
# Clean database
docker-compose exec postgres psql -U mise_user -d mise -c "TRUNCATE ingestion_requests, recipes CASCADE;"

# Run example
uv run python scripts/example_ingestion_workflow.py

# Check results
uv run python scripts/db_status.py
```

Expected output:
- Creates ingestion request (status=pending)
- Worker claims job (status=processing)
- Saves processing metadata
- Creates recipe
- Links ingestion → recipe (status=completed)
- Shows bidirectional relationship working

### File Storage Example

```bash
# Run file storage example
uv run python scripts/example_file_storage.py

# Inspect created files
ls -lh data/files/recipes/

# Optional cleanup
rm -rf data/files/*
```

Expected output:
- Creates recipe with 3 photos
- Saves files to disk with auto-numbered filenames
- Extracts metadata (MIME type, size, dimensions)
- Stores metadata in database JSONB
- Demonstrates temporary file storage and cleanup

## Summary

We now have a production-ready ingestion system with:
- ✅ Separate tables for domain vs processing
- ✅ Background job queue with atomic claiming
- ✅ Deduplication via unique source_key
- ✅ Retry logic for failures
- ✅ Bidirectional relationships
- ✅ Proper indexing for performance
- ✅ File storage with filesystem + database metadata
- ✅ Rich file metadata (MIME types, dimensions, sizes)
- ✅ Temporary file management for ingestion artifacts
- ✅ Working examples demonstrating full workflows

Ready to build background workers and start ingesting recipes!
