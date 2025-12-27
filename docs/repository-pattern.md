# Repository Pattern Implementation

This document describes the repository pattern implementation for the Mise recipe application.

## Overview

The repository pattern provides a clean abstraction layer between business logic and data access, separating concerns between:

- **Business Domain** ([Recipe](../src/mise/schema/recipe.py)) - Pure business data
- **Storage Layer** (SQLAlchemy ORM [models](../src/mise/db/models.py)) - Database representation
- **Repository Layer** ([RecipeRepository](../src/mise/repository/recipe.py)) - Data access operations

## Architecture

### Schema Separation

We use two distinct schemas:

#### 1. Recipe (Business Domain)
Located in `src/mise/schema/recipe.py`

Pure business logic schema with no database concerns:
- Contains only recipe data (title, ingredients, steps, tags, etc.)
- Has a UUID `id` field for business identification
- No timestamps, no soft-delete flags
- Used by business logic and API layers

```python
recipe = Recipe(
    title="Pasta Carbonara",
    ingredients=[...],
    steps=[...],
    tags=[Tag(key="cuisine", value="italian")]
)
```

#### 2. RecipeRecord (Storage with Metadata)
Located in `src/mise/repository/models.py`

Combines business data with database infrastructure:
- Database `id` (integer primary key)
- `created_at`, `updated_at` timestamps
- `deleted_at` for soft deletes
- Embedded `recipe` (Recipe schema)

```python
record = RecipeRecord(
    id=1,
    created_at=datetime(...),
    updated_at=datetime(...),
    deleted_at=None,
    recipe=recipe  # The business domain object
)
```

## Repository Classes

### BaseRepository
Generic CRUD operations for any model:
- `get_by_id(id)` - Retrieve single record
- `get_all(skip, limit)` - List with pagination
- `create(instance)` - Create new record
- `update(instance)` - Update existing record
- `delete(instance)` - Hard delete
- `commit()` / `rollback()` - Transaction control

### RecipeRepository
Recipe-specific data access operations:

#### CRUD Operations
- `create_recipe(recipe: Recipe) -> RecipeRecord`
- `get_recipe_by_id(id, include_deleted) -> RecipeRecord | None`
- `get_all_recipes(skip, limit, include_deleted) -> list[RecipeRecord]`
- `update_recipe(id, recipe: Recipe) -> RecipeRecord | None`

#### Soft Delete Operations
- `soft_delete(id) -> bool` - Mark as deleted
- `restore(id) -> bool` - Unmark deleted
- `hard_delete(id) -> bool` - Permanently remove

#### Query Methods
- `search_by_title(query) -> list[RecipeRecord]` - Case-insensitive title search
- `find_by_tag(tag_key, tag_value) -> list[RecipeRecord]` - JSONB tag filtering
- `count(include_deleted) -> int` - Total count

## JSONB Storage

Recipes are stored in a single JSONB `data` column for flexibility:

### Benefits
- Schema evolution without migrations
- Efficient indexing on nested fields
- Full PostgreSQL JSONB query capabilities
- GIN indexes for fast searches

### Indexes
- **B-tree on title** - Fast title lookups and searches
- **GIN on data** - Full JSONB content search
- **Partial indexes** - Exclude soft-deleted records

### Example Queries

```python
# Search by title
results = repo.search_by_title("carbonara")

# Find by tag
italian = repo.find_by_tag("cuisine", "italian")
dinners = repo.find_by_tag("meal-type", "dinner")

# All recipes with pagination
page_1 = repo.get_all_recipes(skip=0, limit=20)
page_2 = repo.get_all_recipes(skip=20, limit=20)
```

## Usage Example

```python
from sqlalchemy.orm import Session
from mise.db.database import engine
from mise.repository import RecipeRepository
from mise.schema.recipe import Recipe, Ingredient, RecipeStep, Tag

with Session(engine) as session:
    repo = RecipeRepository(session)

    # Create
    recipe = Recipe(
        title="Pasta Carbonara",
        ingredients=[
            Ingredient(
                text="400g spaghetti",
                name="spaghetti",
                quantity=400,
                unit="g"
            )
        ],
        steps=[
            RecipeStep(instruction="Boil pasta")
        ],
        tags=[
            Tag(key="cuisine", value="italian")
        ]
    )

    record = repo.create_recipe(recipe)
    repo.commit()
    print(f"Created recipe {record.id}")

    # Read
    found = repo.get_recipe_by_id(record.id)
    print(f"Title: {found.recipe.title}")

    # Update
    recipe.servings = 6
    updated = repo.update_recipe(record.id, recipe)
    repo.commit()

    # Search
    results = repo.search_by_title("carbonara")
    italian_recipes = repo.find_by_tag("cuisine", "italian")

    # Soft delete
    repo.soft_delete(record.id)
    repo.commit()

    # Restore
    repo.restore(record.id)
    repo.commit()
```

## Transaction Management

The repository uses SQLAlchemy sessions for transaction management:

- **Session** - Created per request/operation
- **Flush** - Write to DB without committing (gets generated IDs)
- **Commit** - Persist changes permanently
- **Rollback** - Undo changes on error

### Best Practices

1. **Use context managers** for automatic session cleanup
2. **Commit explicitly** after successful operations
3. **Rollback on errors** to maintain consistency
4. **One session per request** in API handlers

```python
# Good - explicit transaction control
with Session(engine) as session:
    repo = RecipeRepository(session)
    try:
        record = repo.create_recipe(recipe)
        repo.commit()
    except Exception:
        repo.rollback()
        raise

# Also good - let context manager handle cleanup
with Session(engine) as session:
    repo = RecipeRepository(session)
    record = repo.create_recipe(recipe)
    # Commit happens automatically if no exception
    session.commit()
```

## Testing

Run the example usage script to see all features in action:

```bash
uv run python scripts/example_usage.py
```

This demonstrates:
- Creating recipes
- Retrieving by ID
- Updating records
- Title search
- Tag filtering
- Soft delete and restore
- Counting records

## Future Enhancements

Potential additions to consider:

1. **Query Objects** - Encapsulate complex filters
2. **Service Layer** - Business logic above repositories
3. **Caching** - Add Redis/in-memory caching
4. **Bulk Operations** - Batch inserts/updates
5. **Full-text Search** - PostgreSQL tsvector for better search
6. **More Query Methods** - By ingredient, prep time, etc.

## Files

- `src/mise/schema/recipe.py` - Business domain schemas
- `src/mise/db/models.py` - SQLAlchemy ORM models
- `src/mise/repository/base.py` - Generic repository base class
- `src/mise/repository/models.py` - RecipeRecord schema
- `src/mise/repository/recipe.py` - Recipe-specific repository
- `scripts/example_usage.py` - Usage demonstration
