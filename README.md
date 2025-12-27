# Mise

Recipe management system with PostgreSQL and SQLAlchemy 2.0.

## Setup

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure Environment

The project uses environment-specific configuration files. For development, the default `.env.development` is automatically loaded (no setup needed).

For production deployment, see [docs/environment-config.md](docs/environment-config.md).

**Quick start (development):** No configuration needed - just run commands and `.env.development` will be used automatically.

### 3. Start PostgreSQL

Using Docker Compose:
```bash
docker-compose up -d
```

Or use your own PostgreSQL instance.

### 4. Initialize Database

Use Alembic to create the database schema:

```bash
# Run migrations to create tables
alembic upgrade head
```

To check database status:
```bash
uv run python scripts/db_status.py
```

## Database Management

### Migrations with Alembic

```bash
# Create a new migration after model changes
alembic revision --autogenerate -m "description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current migration version
alembic current

# View migration history
alembic history
```

### Database Utilities

```bash
# Check database connection and status
uv run python scripts/db_status.py
```

### Environment Management

```bash
# Development (default)
alembic upgrade head

# Production
ENV=production alembic upgrade head

# Or use helper scripts
./scripts/run_dev.sh alembic upgrade head
./scripts/run_prod.sh alembic upgrade head
```

See [docs/environment-config.md](docs/environment-config.md) for detailed configuration.

## Project Structure

```
mise/
├── src/mise/
│   ├── config.py          # Environment configuration loader
│   ├── db/                # Database layer
│   │   ├── database.py    # Engine and session setup
│   │   └── models.py      # ORM models
│   ├── schema/            # Pydantic schemas (business domain)
│   │   └── recipe.py      # Recipe, Ingredient, RecipeStep, Tag
│   ├── repository/        # Data access layer
│   │   ├── base.py        # Generic CRUD operations
│   │   ├── models.py      # RecipeRecord (with metadata)
│   │   └── recipe.py      # RecipeRepository
│   └── ingestion/         # Data ingestion
│       └── source_utils.py # Source tracking utilities
├── alembic/               # Database migrations
│   ├── env.py             # Alembic configuration
│   └── versions/          # Migration scripts
├── scripts/               # Runnable scripts
│   ├── db_status.py       # Check database status
│   ├── run_dev.sh         # Run commands in dev environment
│   ├── run_prod.sh        # Run commands in prod environment
│   └── example_*.py       # Usage examples
├── docs/                  # Documentation
│   ├── repository-pattern.md    # Repository pattern guide
│   ├── source-tracking.md       # Source tracking guide
│   ├── environment-config.md    # Environment setup guide
│   └── quick-reference.md       # Quick command reference
└── data/                  # Data files
```

## Development

### Running the Application
```bash
mise
```

### Repository Pattern

The project uses the Repository Pattern to separate business logic from data access:

- **Recipe** (schema) - Pure business domain, no DB concerns
- **RecipeRecord** (repository) - Includes database metadata (id, timestamps, soft delete)
- **RecipeRepository** - Data access operations (CRUD, search, queries)

See [docs/repository-pattern.md](docs/repository-pattern.md) for detailed documentation.

### Example Usage

```bash
# Run the repository example
uv run python scripts/example_usage.py
```

```python
from sqlalchemy.orm import Session
from mise.db.database import engine
from mise.repository import RecipeRepository
from mise.schema.recipe import Recipe, Tag

with Session(engine) as session:
    repo = RecipeRepository(session)

    # Create
    recipe = Recipe(title="Pasta", ingredients=[...], steps=[...])
    record = repo.create_recipe(recipe)
    repo.commit()

    # Search
    results = repo.search_by_title("pasta")
    italian = repo.find_by_tag("cuisine", "italian")

    # Source tracking for deduplication
    from mise.ingestion import SourceType, extract_youtube_video_id
    video_id = extract_youtube_video_id("https://youtube.com/watch?v=VIDEO_ID")
    record, created = repo.upsert_from_source(
        recipe,
        source_type=SourceType.YOUTUBE,
        source_key=video_id,
        source_metadata={"url": "...", "channel": "..."}
    )
```

### Source Tracking & Deduplication

Recipes can be tracked by source to prevent duplicates:

```bash
# Run source tracking example
uv run python scripts/example_source_tracking.py
```

**Supported source types:**
- `custom` - User-created recipes (uses Recipe UUID)
- `youtube` - YouTube videos (uses video ID)
- `webpage` - Web scraped recipes (uses normalized URL)
- `photo` - OCR from photos (uses image hash)

**Key methods:**
- `find_by_source(type, key)` - Find existing recipe
- `create_from_source(recipe, type, key, metadata)` - Create with source tracking
- `upsert_from_source(...)` - Create or update (prevents duplicates)

### Database Schema

The project uses a JSONB-based schema for flexible recipe storage:

- **recipes** table with JSONB `data` column
- Soft delete support via `deleted_at`
- Source tracking (`source_type`, `source_key`, `source_metadata`) for deduplication
- Unique constraint on `(source_type, source_key)` for non-deleted recipes
- GIN indexes for fast JSONB queries
- B-tree indexes for common fields (title, tags)
