# Ingestion System Design

## Problem Statement

We need to design a system that:
1. Tracks ingestion requests (user submits a YouTube URL, webpage, photo, etc.)
2. Supports background/async processing (download, AI extraction, etc.)
3. Stores ingestion metadata (raw downloads, AI outputs, processing logs)
4. Handles retries and failure cases
5. Allows querying ingestion status and history
6. Links ingestion attempts to recipe records

## Key Questions

### Should ingestion data live in the recipe table or separate tables?

This is the core architectural decision. Let's explore both approaches.

---

# Design Option 1: Single Table (Embedded in Recipe)

Store all ingestion data directly in the `recipes` table using JSONB columns.

## Schema

```python
class RecipeDbModel(Base):
    __tablename__ = "recipes"

    # Core fields
    id: Mapped[int]
    uuid: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None]

    # Source tracking (for deduplication)
    source_type: Mapped[str | None]
    source_key: Mapped[str | None]
    source_metadata: Mapped[dict | None]  # JSONB

    # Ingestion tracking
    ingestion_status: Mapped[str | None]  # "pending", "processing", "completed", "failed"
    ingestion_metadata: Mapped[dict | None]  # JSONB - all processing data

    # Recipe data
    data: Mapped[dict]  # JSONB - the actual recipe
```

### `ingestion_metadata` Structure

```json
{
  "request": {
    "requested_at": "2025-12-27T16:00:00Z",
    "requested_by": "user_123",
    "request_method": "api",
    "priority": "normal"
  },
  "processing": {
    "started_at": "2025-12-27T16:00:05Z",
    "completed_at": "2025-12-27T16:01:30Z",
    "duration_ms": 85000,
    "worker_id": "worker-3",
    "retry_count": 0
  },
  "downloads": {
    "transcript": {
      "url": "https://youtube.com/...",
      "downloaded_at": "2025-12-27T16:00:10Z",
      "size_bytes": 15234,
      "content": "..."
    },
    "video_metadata": {...},
    "thumbnail": "s3://bucket/..."
  },
  "ai_extraction": {
    "model": "claude-sonnet-4.5",
    "prompt_version": "v2.1",
    "tokens_used": 12500,
    "confidence": 0.95,
    "extracted_at": "2025-12-27T16:01:00Z",
    "warnings": ["unclear_timing"]
  },
  "errors": [
    {
      "timestamp": "2025-12-27T16:00:15Z",
      "stage": "download",
      "message": "Rate limit hit, retrying...",
      "resolved": true
    }
  ]
}
```

## Pros
- ✅ Simple - everything in one place
- ✅ No joins needed to see recipe + ingestion data
- ✅ Easy to understand and query
- ✅ JSONB is flexible for varied ingestion methods
- ✅ Natural lifecycle: request → processing → completed recipe

## Cons
- ❌ Large JSONB fields can bloat the table
- ❌ Querying "all pending ingestions" requires scanning recipe table
- ❌ Hard to track multiple ingestion attempts for same recipe
- ❌ Processing/worker concerns mixed with domain model
- ❌ Can't easily purge old ingestion metadata without affecting recipes
- ❌ Background job queue needs to query main recipe table

## Query Examples

```python
# Find pending ingestions
stmt = select(RecipeDbModel).where(
    RecipeDbModel.ingestion_status == "pending"
)

# Find failed ingestions from last hour
stmt = select(RecipeDbModel).where(
    RecipeDbModel.ingestion_status == "failed",
    RecipeDbModel.updated_at > datetime.now() - timedelta(hours=1)
)

# Get recipe with full ingestion history - just one query!
recipe = session.get(RecipeDbModel, recipe_id)
```

---

# Design Option 2: Separate Ingestion Table (Linked)

Create a dedicated `ingestion_requests` table that links to recipes.

## Schema

### Recipes Table (Clean Domain Model)

```python
class RecipeDbModel(Base):
    __tablename__ = "recipes"

    # Core fields
    id: Mapped[int]
    uuid: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None]

    # Source tracking (for deduplication)
    source_type: Mapped[str | None]
    source_key: Mapped[str | None]
    source_metadata: Mapped[dict | None]  # JSONB - lightweight

    # Recipe data
    data: Mapped[dict]  # JSONB

    # Relationship
    ingestions: Mapped[list["IngestionRequest"]] = relationship(back_populates="recipe")
```

### Ingestion Requests Table (Processing Model)

```python
class IngestionRequest(Base):
    __tablename__ = "ingestion_requests"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[UUID] = mapped_column(default=uuid4, unique=True, index=True)

    # Link to recipe (nullable - recipe created after processing)
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
    recipe: Mapped["RecipeDbModel | None"] = relationship(back_populates="ingestions")

    # Request metadata
    source_type: Mapped[str]  # youtube, webpage, photo, custom
    source_url: Mapped[str | None]  # Original URL/identifier
    source_key: Mapped[str]  # For deduplication

    # Status tracking
    status: Mapped[str]  # pending, processing, completed, failed, cancelled
    priority: Mapped[int] = mapped_column(default=0)  # For queue ordering

    # Timestamps
    requested_at: Mapped[datetime]
    processing_started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]

    # Processing metadata
    retry_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=3)
    worker_id: Mapped[str | None]

    # User tracking (optional)
    requested_by: Mapped[str | None]

    # Processing data (JSONB)
    request_data: Mapped[dict | None]  # Original request parameters
    processing_log: Mapped[list[dict] | None]  # Step-by-step logs
    downloads: Mapped[dict | None]  # Downloaded content/files
    ai_metadata: Mapped[dict | None]  # AI extraction details
    error_details: Mapped[dict | None]  # Error messages, stack traces

    # Indexes
    __table_args__ = (
        Index("idx_ingestion_status", "status"),
        Index("idx_ingestion_source_key", "source_key"),
        Index("idx_ingestion_requested_at", "requested_at"),
    )
```

## Pros
- ✅ Clean separation of concerns (domain vs processing)
- ✅ Can track multiple ingestion attempts per recipe
- ✅ Easy to query job queue ("give me pending jobs")
- ✅ Can add worker-specific fields (retry logic, locks, etc.)
- ✅ Can purge old ingestion records without affecting recipes
- ✅ Better for background job systems (Celery, RQ, etc.)
- ✅ Can have ingestion requests that never become recipes (failures)
- ✅ Easier to add features like priority queues, rate limiting

## Cons
- ❌ More complex - requires joins to see full picture
- ❌ Two tables to maintain
- ❌ Need to handle recipe_id being NULL initially
- ❌ More code to write and test

## Lifecycle Flow

```
1. User submits URL
   → Create IngestionRequest (status=pending, recipe_id=NULL)

2. Background worker picks it up
   → Update status=processing, worker_id=worker-3

3. Worker downloads content
   → Update downloads field with transcript, etc.

4. Worker runs AI extraction
   → Update ai_metadata with extraction results

5. Worker creates Recipe
   → Create RecipeDbModel
   → Update IngestionRequest.recipe_id = new_recipe.id
   → Update status=completed

6. (Optional) Purge old ingestion logs after 90 days
   → Keep recipes, delete old IngestionRequest records
```

## Query Examples

```python
# Find pending ingestions (efficient index scan)
stmt = select(IngestionRequest).where(
    IngestionRequest.status == "pending"
).order_by(IngestionRequest.priority.desc(), IngestionRequest.requested_at)

# Find recipe with ingestion history
recipe = session.get(RecipeDbModel, recipe_id)
ingestions = recipe.ingestions  # All attempts

# Check if source already ingested
existing = session.scalar(
    select(IngestionRequest)
    .where(IngestionRequest.source_key == key)
    .where(IngestionRequest.status.in_(["completed", "processing"]))
)

# Worker query: claim next job
stmt = (
    select(IngestionRequest)
    .where(IngestionRequest.status == "pending")
    .order_by(IngestionRequest.priority.desc())
    .limit(1)
    .with_for_update(skip_locked=True)  # Prevent race conditions
)
```

---

# Design Option 3: Hybrid (Minimal Ingestion Table)

Keep most data in recipes table, but add a lightweight ingestion queue table.

## Schema

### Recipes Table (With Ingestion Summary)

```python
class RecipeDbModel(Base):
    # ... same as Option 1 ...

    # Just a summary of latest ingestion
    last_ingestion_status: Mapped[str | None]
    last_ingestion_at: Mapped[datetime | None]
    ingestion_metadata: Mapped[dict | None]  # Full details
```

### Ingestion Queue Table (Minimal)

```python
class IngestionQueue(Base):
    __tablename__ = "ingestion_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    status: Mapped[str]  # pending, processing, completed, failed
    priority: Mapped[int]
    requested_at: Mapped[datetime]
    worker_id: Mapped[str | None]

    # Index for queue queries
    __table_args__ = (
        Index("idx_queue_status_priority", "status", "priority"),
    )
```

## Pros
- ✅ Fast queue queries (small table)
- ✅ Recipe table has full history
- ✅ Can purge completed queue items easily

## Cons
- ❌ Still need joins
- ❌ Duplicate data (status in both tables)
- ❌ More complex state management

---

# Comparison Matrix

| Feature | Option 1: Single Table | Option 2: Separate Table | Option 3: Hybrid |
|---------|----------------------|-------------------------|------------------|
| Simplicity | ⭐⭐⭐ | ⭐ | ⭐⭐ |
| Queue Performance | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| History Tracking | ⭐ | ⭐⭐⭐ | ⭐⭐ |
| Data Size | ⭐ (bloated) | ⭐⭐⭐ | ⭐⭐ |
| Separation of Concerns | ⭐ | ⭐⭐⭐ | ⭐⭐ |
| Integration with Job Queues | ⭐ | ⭐⭐⭐ | ⭐⭐ |
| Multiple Attempts | ⭐ | ⭐⭐⭐ | ⭐⭐ |

---

# Recommendation: Option 2 (Separate Tables)

## Why?

1. **You mentioned background processing** - This strongly suggests you'll need proper job queue semantics:
   - Claiming jobs atomically (`SELECT ... FOR UPDATE SKIP LOCKED`)
   - Priority queues
   - Retry logic
   - Worker coordination

2. **Natural separation**: Recipe creation is the *result* of ingestion, not the same thing. The ingestion request exists *before* the recipe.

3. **Scalability**: As you add more ingestion sources (YouTube, photos, webpages), each might fail differently or need retries. A dedicated table handles this cleanly.

4. **Observability**: You can easily see:
   - "Show me all failed ingestions from yesterday"
   - "How long does YouTube ingestion take on average?"
   - "Which worker is processing the most jobs?"

5. **Data lifecycle**: You might want to keep recipes forever but purge old ingestion logs after 90 days.

## Implementation Plan

### Phase 1: Core Tables
1. Create `IngestionRequest` model
2. Add relationship to `RecipeDbModel`
3. Create migration

### Phase 2: Repository Layer
1. `IngestionRequestRepository` with methods:
   - `create_request(source_type, source_url, priority)`
   - `get_next_pending(worker_id)` - Claims job atomically
   - `update_status(id, status, metadata)`
   - `mark_completed(id, recipe_id)`
   - `mark_failed(id, error_details)`
   - `find_by_source_key(key)` - Check for duplicates

### Phase 3: Background Worker Integration
1. Worker picks up jobs from queue
2. Processes downloads/AI
3. Creates recipe when done
4. Links back to ingestion request

### Phase 4: Optional Enhancements
- Status webhooks/callbacks
- Progress tracking (0-100%)
- Scheduled retries with exponential backoff
- User notifications

---

# Alternative: Task Queue Library

If you're going to build a full job queue system, consider using:

- **Celery** - Full-featured task queue (requires Redis/RabbitMQ)
- **RQ (Redis Queue)** - Simpler, Python-only (requires Redis)
- **Dramatiq** - Modern alternative to Celery
- **Huey** - Lightweight, supports SQLite/Redis

These provide:
- Automatic retries
- Worker pools
- Task scheduling
- Result backends

**If using a task queue library**: You might still want the `IngestionRequest` table to track *what* was requested (domain model), while the task queue handles *how* to process it (infrastructure).

## Hybrid with Task Queue

```python
# Domain: Track what was requested
ingestion_request = IngestionRequest(
    source_type="youtube",
    source_key=video_id,
    status="pending"
)
session.add(ingestion_request)
session.commit()

# Infrastructure: Queue the job
task_id = process_youtube_video.delay(ingestion_request.id)
ingestion_request.task_id = task_id
session.commit()
```

---

# Decision Matrix

## Use Option 1 (Single Table) if:
- ✅ You have simple ingestion (no retries, no queue)
- ✅ You always process synchronously
- ✅ You want to ship quickly

## Use Option 2 (Separate Tables) if:
- ✅ You need background processing
- ✅ You want retry logic
- ✅ You need to track multiple ingestion attempts
- ✅ You want clean separation of concerns
- ✅ You plan to scale this system

## Use Task Queue Library if:
- ✅ You need distributed workers
- ✅ You need scheduled tasks
- ✅ You want proven infrastructure
- ✅ You're okay with external dependencies (Redis)

---

# My Final Recommendation

**Start with Option 2 (Separate Tables)** because:
1. You explicitly mentioned "background processing"
2. It's easier to add a task queue later if needed
3. You maintain full control and visibility
4. The complexity is manageable for a homelab project
5. It teaches you the fundamentals before abstracting with libraries

You can always add Celery/RQ later if you need distributed workers, but for a homelab with 1-2 workers, a PostgreSQL-based queue works great and requires no additional infrastructure.

---

# Next Steps

Would you like me to:
1. Implement Option 2 (Separate Tables)?
2. Create the `IngestionRequest` model and migration?
3. Build the repository layer with queue semantics?
4. Or discuss any aspect of this design further?
