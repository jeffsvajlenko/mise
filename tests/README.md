# Mise Test Suite

Comprehensive test suite for the Mise recipe management system.

## Quick Start

```bash
# Setup test database (first time only)
./scripts/setup_test_db.sh

# Run all tests
./scripts/test.sh

# Run with coverage
./scripts/test.sh --coverage

# Run only unit tests
./scripts/test.sh --unit

# Run only integration tests
./scripts/test.sh --integration

# Run with verbose output
./scripts/test.sh -v

# Stop on first failure
./scripts/test.sh -x

# Run specific test file
./scripts/test.sh tests/test_schema.py

# Run specific test
./scripts/test.sh tests/test_schema.py::TestRecipe::test_minimal_recipe
```

## Prerequisites

1. **Docker running** - PostgreSQL runs in Docker
2. **Database ready** - Run `docker-compose up -d postgres`
3. **Test database created** - Run `./scripts/setup_test_db.sh`

## Manual Test Running

If you prefer to run tests manually:

```bash
# Set environment variable
export TEST_DATABASE_URL="postgresql+psycopg://mise_user:mise_password@localhost:5432/mise_test"

# Run migrations on test database
DATABASE_URL=$TEST_DATABASE_URL uv run alembic upgrade head

# Run tests
uv run pytest tests/

# Run with coverage
uv run pytest tests/ --cov=src/mise --cov-report=term-missing --cov-report=html
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures and test configuration
├── test_models.py           # Database model tests (14 tests)
├── test_repositories.py     # Repository layer tests (15 tests)
├── test_unit_of_work.py     # UnitOfWork pattern tests (8 tests)
├── test_schema.py           # Recipe schema validation tests (15 tests)
├── test_ingestion.py        # URL/source utilities tests (16 tests)
└── test_integration.py      # End-to-end integration tests (10 tests)
```

## Test Categories

Tests are marked with pytest markers:

- `@pytest.mark.unit` - Fast unit tests, no database required
- `@pytest.mark.integration` - Integration tests with database

Filter by marker:

```bash
pytest -m unit          # Run only unit tests
pytest -m integration   # Run only integration tests
```

## Test Coverage

Current coverage: **~90%** (70+ tests)

### Well Tested
- ✅ Database models (RecipeDbModel, IngestionRequest)
- ✅ Repository layer (RecipeRepository, IngestionRepository)
- ✅ Unit of Work pattern
- ✅ Recipe schema validation
- ✅ URL normalization and source utilities
- ✅ Integration workflows (ingestion, recipe CRUD)

### Gaps
- ⚠️ File storage operations (partial coverage)
- ⚠️ Error handling edge cases
- ⚠️ Concurrent access scenarios

## Test Database

The test suite uses a separate `mise_test` database to avoid contaminating production data.

**Important:**
- Tests automatically clean up data between runs
- Production database (`mise`) is never touched during tests
- Test database is recreated from scratch by `setup_test_db.sh`

### Database Isolation

Each test gets:
1. Fresh tables (TRUNCATE before each test)
2. Separate database (`mise_test`)
3. Automatic cleanup after test

## Troubleshooting

### "Connection refused" errors

Database isn't running. Start it:

```bash
docker-compose up -d postgres
```

### "relation does not exist"

Test database needs migrations:

```bash
./scripts/setup_test_db.sh
```

### Tests pass but production DB has test data

This shouldn't happen anymore! The `UnitOfWork` fix ensures all tests use `mise_test`. If you see this:

1. Check `TEST_DATABASE_URL` is set correctly
2. Clean production database: `docker-compose exec postgres psql -U mise_user -d mise -c "TRUNCATE TABLE recipes, ingestion_requests CASCADE;"`

### Slow tests

Integration tests hit the database. Run only unit tests:

```bash
./scripts/test.sh --unit
```

## Adding New Tests

1. **Unit tests** - Add to appropriate `test_*.py` file
2. **Integration tests** - Add to `test_integration.py`
3. **New fixtures** - Add to `conftest.py`

Example test:

```python
@pytest.mark.unit
class TestMyFeature:
    """Tests for my new feature."""

    def test_basic_functionality(self):
        """Test basic functionality."""
        result = my_function()
        assert result == expected_value
```

## CI/CD

The test suite is designed to run in CI environments:

```yaml
# Example GitHub Actions
- name: Run tests
  env:
    TEST_DATABASE_URL: postgresql+psycopg://mise_user:mise_password@localhost:5432/mise_test
  run: |
    ./scripts/setup_test_db.sh
    ./scripts/test.sh --coverage
```

## Performance

- **Unit tests**: ~1s (no database)
- **Integration tests**: ~5s (with database)
- **Full suite**: ~6s total

Fast feedback loop for development!
