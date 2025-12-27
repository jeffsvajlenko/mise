# Ingestion System Design v2 - Decoupled Tables

## Design Principles

1. **Recipe table** = Clean domain model with reader-relevant source info
2. **Ingestion table** = Processing/queue model with full technical details
3. **Minimal coupling** = Can delete old ingestions without affecting recipes
4. **Optional history** = Can track multiple ingestions per recipe if needed

---

# Core Schema Design

## 1. Recipes Table (Domain Model)

The recipe table stores the final recipe plus **reader-relevant** source information.

```python
class RecipeDbModel(Base):
    __tablename__ = "recipes"

    # Identity
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[UUID] = mapped_column(default=uuid4, unique=True, index=True)

    # Timestamps
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None]

    # Reader-relevant source info (what they care about)
    source_display: Mapped[str | None] = mapped_column(
        String(100),
        comment="Human-readable source: 'YouTube: Gordon Ramsay', 'My grandmother', etc."
    )
    source_url: Mapped[str | None] = mapped_column(
        String(500),
        comment="Original URL if applicable (for reader to visit)"
    )
    source_attribution: Mapped[str | None] = mapped_column(
        Text,
        comment="Author/creator attribution, copyright info, etc."
    )

    # Recipe data (JSONB)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)

    # Indexes
    __table_args__ = (
        Index("idx_recipe_created_at", "created_at"),
        Index("idx_recipe_source_display", "source_display"),
    )
```

**What goes here:**
- ✅ "Source: YouTube - Gordon Ramsay"
- ✅ "https://youtube.com/watch?v=abc123"
- ✅ "Recipe by J. Kenji López-Alt"
- ❌ Technical ingestion metadata (model, tokens, worker ID)
- ❌ Download logs, processing steps
- ❌ Retry counts, error messages

## 2. Ingestion Requests Table (Processing Model)

The ingestion table handles all the processing, queueing, and technical details.

```python
class IngestionRequest(Base):
    __tablename__ = "ingestion_requests"

    # Identity
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[UUID] = mapped_column(default=uuid4, unique=True, index=True)

    # Link to created recipe (nullable until completed)
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"),
        index=True,
        comment="Recipe created from this ingestion (NULL if pending/failed)"
    )

    # Source identification (for deduplication)
    source_type: Mapped[str] = mapped_column(
        String(50),
        comment="Type: youtube, webpage, photo, custom"
    )
    source_key: Mapped[str] = mapped_column(
        String(500),
        comment="Unique identifier: video_id, normalized URL, image hash, etc."
    )
    source_url: Mapped[str | None] = mapped_column(
        String(1000),
        comment="Original URL submitted by user"
    )

    # Queue/Status management
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        comment="Status: pending, processing, completed, failed, cancelled"
    )
    priority: Mapped[int] = mapped_column(
        default=0,
        comment="Higher = process first (0 = normal)"
    )

    # Timestamps
    requested_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    processing_started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]

    # Processing tracking
    retry_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=3)
    worker_id: Mapped[str | None] = mapped_column(String(100))

    # User tracking (optional)
    requested_by: Mapped[str | None] = mapped_column(String(100))

    # Processing data (JSONB)
    request_params: Mapped[dict | None] = mapped_column(
        JSONB,
        comment="Original request: {priority, notes, extract_images, etc.}"
    )

    processing_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        comment="Downloads, AI outputs, logs, errors - everything technical"
    )

    # Indexes
    __table_args__ = (
        Index("idx_ingestion_status", "status"),
        Index("idx_ingestion_source_key", "source_key"),
        Index("idx_ingestion_requested_at", "requested_at"),
        Index("idx_ingestion_queue", "status", "priority", "requested_at"),
        UniqueConstraint("source_key", name="uq_ingestion_source_key"),
    )
```

### `processing_metadata` JSONB Structure

```json
{
  "downloads": {
    "transcript": {
      "content": "full transcript text...",
      "downloaded_at": "2025-12-27T16:00:10Z",
      "size_bytes": 15234
    },
    "video_metadata": {
      "title": "Perfect Scrambled Eggs",
      "channel": "Gordon Ramsay",
      "duration": 420,
      "views": 5000000
    },
    "thumbnail_url": "https://i.ytimg.com/..."
  },

  "ai_extraction": {
    "model": "claude-sonnet-4.5",
    "prompt_version": "recipe_extract_v2.1",
    "tokens_input": 8500,
    "tokens_output": 4000,
    "cost_usd": 0.15,
    "confidence_score": 0.95,
    "extracted_at": "2025-12-27T16:01:00Z",
    "warnings": [
      "Cooking time unclear - estimated based on context",
      "Salt measurement not specified - used 'to taste'"
    ]
  },

  "processing_log": [
    {
      "step": "validate_url",
      "status": "success",
      "timestamp": "2025-12-27T16:00:05Z",
      "duration_ms": 50
    },
    {
      "step": "download_transcript",
      "status": "retry",
      "timestamp": "2025-12-27T16:00:10Z",
      "error": "Rate limit hit",
      "retry_after_seconds": 5
    },
    {
      "step": "download_transcript",
      "status": "success",
      "timestamp": "2025-12-27T16:00:15Z",
      "duration_ms": 1200
    },
    {
      "step": "ai_extraction",
      "status": "success",
      "timestamp": "2025-12-27T16:01:00Z",
      "duration_ms": 45000
    }
  ],

  "errors": [
    {
      "timestamp": "2025-12-27T16:00:10Z",
      "stage": "download",
      "error_type": "RateLimitError",
      "message": "YouTube rate limit exceeded",
      "retry_count": 1,
      "resolved": true
    }
  ],

  "files": {
    "thumbnail": "s3://mise-recipes/ingestions/abc123/thumb.jpg",
    "video": "s3://mise-recipes/ingestions/abc123/video.mp4",
    "images": [
      "s3://mise-recipes/ingestions/abc123/step1.jpg",
      "s3://mise-recipes/ingestions/abc123/step2.jpg"
    ]
  }
}
```

---

# Linking Options: 3 Approaches

## Option A: Foreign Key Only (Recommended for v1)

**Storage:** `IngestionRequest.recipe_id` points to `Recipe.id`

```python
class IngestionRequest(Base):
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
```

### Queries

```python
# Find recipe from ingestion
ingestion = session.get(IngestionRequest, ingestion_id)
recipe = session.get(RecipeDbModel, ingestion.recipe_id)

# Find all ingestions that created a recipe
ingestions = session.scalars(
    select(IngestionRequest).where(IngestionRequest.recipe_id == recipe.id)
).all()
```

**Pros:**
- ✅ Simple, standard pattern
- ✅ One query to go from ingestion → recipe
- ✅ FK ensures referential integrity
- ✅ `ondelete="SET NULL"` lets you delete recipes without breaking ingestions

**Cons:**
- ❌ No relationship helper (need manual queries)
- ❌ Going from recipe → ingestions requires manual query

**Best for:** MVP, simple cases where you mostly query ingestion → recipe

---

## Option B: Bidirectional Relationship (Recommended for v2)

**Storage:** Same FK, but add SQLAlchemy relationships

```python
class RecipeDbModel(Base):
    # ...
    ingestions: Mapped[list["IngestionRequest"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan"  # Or leave orphans
    )

class IngestionRequest(Base):
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
    recipe: Mapped["RecipeDbModel | None"] = relationship(back_populates="ingestions")
```

### Queries

```python
# Load recipe with all ingestion attempts
recipe = session.get(RecipeDbModel, recipe_id)
for ingestion in recipe.ingestions:
    print(f"Attempt {ingestion.retry_count}: {ingestion.status}")

# Load ingestion with recipe
ingestion = session.get(IngestionRequest, ingestion_id)
if ingestion.recipe:
    print(f"Created recipe: {ingestion.recipe.data['title']}")
```

**Pros:**
- ✅ Pythonic - use `.recipe` and `.ingestions` properties
- ✅ SQLAlchemy handles loading
- ✅ Can eager load with `joinedload`

**Cons:**
- ❌ Slightly more complex
- ❌ Need to decide on cascade behavior

**Best for:** When you frequently need to navigate both directions

---

## Option C: Separate Mapping Table

**Storage:** `recipe_ingestion_mappings` table

```python
class RecipeIngestionMapping(Base):
    __tablename__ = "recipe_ingestion_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    ingestion_id: Mapped[int] = mapped_column(ForeignKey("ingestion_requests.id", ondelete="CASCADE"))

    # Why this mapping exists
    relationship_type: Mapped[str] = mapped_column(
        String(20),
        comment="created_by, updated_by, derived_from, etc."
    )
    created_at: Mapped[datetime]

    __table_args__ = (
        UniqueConstraint("recipe_id", "ingestion_id", name="uq_recipe_ingestion"),
    )
```

**Pros:**
- ✅ Can track multiple types of relationships (created, updated, merged)
- ✅ Can link one ingestion to multiple recipes (e.g., "combined two recipes")
- ✅ Can link one recipe to multiple ingestions (e.g., "improved with new extraction")
- ✅ Most flexible for future features

**Cons:**
- ❌ More complex - extra table, extra queries
- ❌ Overkill if you only ever have 1:1 or 1:many

**Best for:** Complex scenarios with recipe versioning, merging, re-ingestion

---

# Recipe Revisions: To Track or Not?

## The Question

Should every edit to a recipe create a new revision in the database?

## Option 1: No Revisions (Current Approach)

Just update the recipe in place.

```python
recipe.data = updated_recipe_dict
recipe.updated_at = datetime.now(timezone.utc)
session.commit()
```

**Pros:**
- ✅ Simple
- ✅ No extra storage
- ✅ Fast

**Cons:**
- ❌ Can't undo changes
- ❌ Can't see history
- ❌ Can't compare versions

**Good for:** MVP, homelab where you trust yourself

---

## Option 2: Lightweight Audit Log

Don't version the full recipe, just track what changed.

```python
class RecipeAuditLog(Base):
    __tablename__ = "recipe_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    changed_at: Mapped[datetime]
    changed_by: Mapped[str | None]
    change_type: Mapped[str]  # created, updated, deleted, restored

    # What changed (lightweight)
    changes: Mapped[dict | None] = mapped_column(
        JSONB,
        comment="JSON patch or summary: {field: old_value → new_value}"
    )
```

**Example:**
```json
{
  "field": "data.ingredients[2].amount",
  "old": "1 tsp",
  "new": "2 tsp",
  "reason": "User correction after first attempt"
}
```

**Pros:**
- ✅ See what changed and when
- ✅ Much smaller than full revisions
- ✅ Can track who changed what

**Cons:**
- ❌ Can't reconstruct full old versions
- ❌ Still extra storage

**Good for:** Accountability without huge overhead

---

## Option 3: Full Revision History

Store every version of the recipe.

```python
class RecipeRevision(Base):
    __tablename__ = "recipe_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    revision_number: Mapped[int]

    created_at: Mapped[datetime]
    created_by: Mapped[str | None]
    change_notes: Mapped[str | None]

    # Full snapshot
    data: Mapped[dict] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("recipe_id", "revision_number"),
    )
```

**Pros:**
- ✅ Full undo/redo capability
- ✅ Can compare any two versions
- ✅ Time-travel queries

**Cons:**
- ❌ Lots of storage (full recipe copy each time)
- ❌ More complex queries
- ❌ Need to decide when to create revisions (every edit? manual only?)

**Good for:** Collaborative editing, wiki-style systems

---

## My Recommendation: Phases

### Phase 1: No Revisions (Start Here)
- Just track `updated_at` timestamp
- Simple and fast
- Good enough for homelab

### Phase 2: Link Ingestions to Recipes
- Use **Option A (FK only)** or **Option B (Bidirectional relationship)**
- This gives you "original ingestion" history
- Can see "this recipe came from YouTube ingestion #123"

### Phase 3: Optional Audit Log (Later)
- If you start making lots of manual edits and want to track them
- Add lightweight `RecipeAuditLog` table
- Don't need full revisions unless you're building a wiki

### Future: Full Revisions (If Needed)
- Only if you have multiple users editing
- Or if you want to experiment with different AI extractions

---

# Recommended Schema for v1

## Summary

```
┌─────────────────────────────────┐
│     RecipeDbModel               │
│  - id (PK)                      │
│  - uuid                         │
│  - source_display (reader info) │◄─┐
│  - source_url                   │  │
│  - data (JSONB)                 │  │
└─────────────────────────────────┘  │
                                     │ FK
┌─────────────────────────────────┐  │
│   IngestionRequest              │  │
│  - id (PK)                      │  │
│  - recipe_id (FK) ──────────────┘  │
│  - source_type                  │
│  - source_key (unique)          │
│  - status                       │
│  - processing_metadata (JSONB) │
└─────────────────────────────────┘
```

### Key Points

1. **Recipe has reader-relevant source info**
   - Display name, URL, attribution
   - No technical processing details

2. **Ingestion has all technical details**
   - Downloads, AI metadata, logs, errors
   - Can be purged after 90 days

3. **Simple FK relationship**
   - `IngestionRequest.recipe_id → Recipe.id`
   - With `ondelete="SET NULL"` so deleting recipe doesn't break ingestion history

4. **No revisions initially**
   - Just track `updated_at`
   - Add audit log later if needed

---

# Data Flow Example

## User submits YouTube URL

```python
# 1. Create ingestion request
ingestion = IngestionRequest(
    source_type="youtube",
    source_url="https://youtube.com/watch?v=abc123",
    source_key="youtube:abc123",
    status="pending",
    requested_by="user_456"
)
session.add(ingestion)
session.commit()

# 2. Background worker picks it up
ingestion.status = "processing"
ingestion.worker_id = "worker-1"
ingestion.processing_started_at = datetime.now(timezone.utc)
session.commit()

# 3. Download and process
transcript = download_youtube_transcript("abc123")
video_metadata = get_youtube_metadata("abc123")

ingestion.processing_metadata = {
    "downloads": {
        "transcript": {"content": transcript, ...},
        "video_metadata": video_metadata
    }
}
session.commit()

# 4. AI extraction
ai_result = extract_recipe_with_ai(transcript)

ingestion.processing_metadata["ai_extraction"] = {
    "model": "claude-sonnet-4.5",
    "confidence": ai_result.confidence,
    ...
}
session.commit()

# 5. Create recipe
recipe = RecipeDbModel(
    source_display=f"YouTube: {video_metadata['channel']}",
    source_url=ingestion.source_url,
    source_attribution=f"Recipe from {video_metadata['channel']} ({video_metadata['title']})",
    data=ai_result.recipe_data
)
session.add(recipe)
session.commit()

# 6. Link back
ingestion.recipe_id = recipe.id
ingestion.status = "completed"
ingestion.completed_at = datetime.now(timezone.utc)
session.commit()
```

---

# Questions for You

1. **Linking approach:** Option A (FK only) or Option B (Bidirectional relationship)?
   - A is simpler, B is more Pythonic

2. **Source info on recipe:** Does this split make sense?
   - Reader info (display, URL, attribution) on Recipe
   - Technical info (downloads, AI, logs) on Ingestion

3. **Revisions:** Start without? Add audit log later?

4. **Purging old ingestions:** Should we auto-delete after X days?
   - Keep recipe forever
   - Delete ingestion metadata after 90 days to save space

Let me know which approach you prefer and I can start implementing!
