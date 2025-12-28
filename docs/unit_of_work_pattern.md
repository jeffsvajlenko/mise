# Unit of Work Pattern

## Overview

The Unit of Work pattern provides a clean way to manage database transactions across multiple repositories. It ensures that all database operations within a context either succeed together or fail together (atomicity).

## Why Unit of Work?

**Before (manual session management):**
```python
from sqlalchemy.orm import Session
from mise.db.database import engine

with Session(engine) as session:
    recipe_repo = RecipeRepository(session)
    ingestion_repo = IngestionRepository(session)

    # Do work
    recipe = recipe_repo.create(...)
    ingestion_repo.mark_completed(...)

    # Manual commit
    session.commit()
```

**After (Unit of Work):**
```python
from mise.db.unit_of_work import UnitOfWork

with UnitOfWork() as uow:
    # Do work
    recipe = uow.recipes.create(...)
    uow.ingestions.mark_completed(...)
    # Auto-commits on exit
```

## Benefits

1. **Single Pattern**: One consistent way to interact with the database
2. **Auto-commit/rollback**: No manual transaction management
3. **Type Safety**: Full IDE autocomplete for all repositories
4. **Transaction Boundaries**: Clear `with` block shows transaction scope
5. **Error Safety**: Automatic rollback on exceptions
6. **No Session Leaks**: Session always properly closed

## Usage

### Basic Operations

```python
from mise.db.unit_of_work import UnitOfWork

# Simple create
with UnitOfWork() as uow:
    recipe = uow.recipes.create(recipe_model)

# Simple read
with UnitOfWork() as uow:
    recipe = uow.recipes.get_by_id(123)
```

### Multi-Repository Transactions

```python
with UnitOfWork() as uow:
    # Create recipe
    recipe = uow.recipes.create(recipe_model)

    # Link to ingestion
    uow.ingestions.mark_completed(ingestion_id, recipe.id)

    # Both operations committed together
```

### Exception Handling

```python
try:
    with UnitOfWork() as uow:
        recipe = uow.recipes.create(recipe_model)
        raise ValueError("Oops!")
        # Auto-rollback happens
except ValueError:
    # Changes were rolled back
    pass
```

### Check Before Create

```python
with UnitOfWork() as uow:
    # Check for duplicate
    existing = uow.ingestions.find_by_source_key(source_key)

    if existing:
        return existing.recipe_id

    # Create new
    recipe = uow.recipes.create(recipe_model)
    uow.ingestions.create_request(...)
```

## Available Repositories

Access repositories via properties on the `UnitOfWork` instance:

- `uow.recipes` - RecipeRepository
- `uow.ingestions` - IngestionRepository

## Implementation Details

### Lazy Loading

Repositories are lazy-loaded - they're only created when accessed:

```python
with UnitOfWork() as uow:
    # Session created, but no repositories yet

    recipe = uow.recipes.create(...)
    # RecipeRepository created on first access

    # If you never access uow.ingestions, it's never created
```

### Transaction Lifecycle

```python
with UnitOfWork() as uow:
    # 1. __enter__: Session created

    # 2. Your code runs here
    uow.recipes.create(...)

    # 3. __exit__:
    #    - If no exception: session.commit()
    #    - If exception: session.rollback()
    #    - Always: session.close()
```

### Manual Flush

Sometimes you need an ID before committing:

```python
with UnitOfWork() as uow:
    ingestion = uow.ingestions.create_request(...)

    # Get the ID without committing
    uow.session.flush()

    # Now ingestion.id is available
    recipe = uow.recipes.create_linked_to(ingestion.id)
```

## Adding New Repositories

To add a new repository type:

1. Create the repository class (e.g., `UserRepository`)
2. Add a lazy-loaded property to `UnitOfWork`:

```python
class UnitOfWork:
    def __init__(self):
        self.session = Session(engine)
        self._users: UserRepository | None = None

    @property
    def users(self) -> UserRepository:
        if self._users is None:
            self._users = UserRepository(self.session)
        return self._users
```

## Migration Guide

### Old Pattern (Session)

```python
with Session(engine) as session:
    repo = RecipeRepository(session)
    recipe = repo.create(...)
    session.commit()
```

### New Pattern (UnitOfWork)

```python
with UnitOfWork() as uow:
    recipe = uow.recipes.create(...)
```

## Testing

For testing, you can mock the UnitOfWork:

```python
from unittest.mock import Mock, MagicMock

def test_create_recipe():
    mock_uow = Mock(spec=UnitOfWork)
    mock_uow.recipes = Mock()
    mock_uow.recipes.create = MagicMock(return_value=mock_recipe)

    # Test code using mock_uow
```

## Best Practices

1. **Always use context manager**: Never create `UnitOfWork()` without `with`
2. **Keep transactions short**: Don't perform long operations inside `with` block
3. **One UoW per request**: In web apps, use one UoW per HTTP request
4. **Don't nest UoW**: Each `with UnitOfWork()` is a separate transaction
5. **Use flush sparingly**: Only when you need an ID mid-transaction

## Anti-Patterns

❌ **Don't create without context manager:**
```python
uow = UnitOfWork()  # Session never closed!
```

❌ **Don't nest transactions:**
```python
with UnitOfWork() as uow1:
    with UnitOfWork() as uow2:  # Bad - separate transactions
        ...
```

❌ **Don't perform I/O inside transaction:**
```python
with UnitOfWork() as uow:
    recipe = uow.recipes.create(...)
    send_email(...)  # Bad - keeps transaction open
    upload_to_s3(...)  # Bad - network call in transaction
```

✅ **Do I/O outside transaction:**
```python
with UnitOfWork() as uow:
    recipe = uow.recipes.create(...)
    recipe_id = recipe.id

# Transaction committed and closed
send_email(recipe_id)
upload_to_s3(recipe_id)
```

## Examples

See these example scripts:

- `scripts/example_unit_of_work.py` - Comprehensive examples
- `scripts/example_ingestion_workflow.py` - Old pattern (for comparison)
