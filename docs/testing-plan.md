# Testing Plan for Mise

## Overview

This document outlines the testing strategy for the Mise recipe management system, covering all layers from AI extraction to the API.

## Current Test Coverage

### ✅ Completed Tests

#### Worker Tests (`tests/test_worker*.py`)
- **Unit tests** (121 passing)
  - Worker configuration
  - Job claiming with row-level locking
  - Status transitions
  - Error handling and retries
  - Graceful shutdown
  - Orphaned job recovery

- **Integration tests**
  - End-to-end job processing
  - Multiple concurrent workers
  - Database transaction handling

- **Manual tests** (`scripts/test_worker.py`)
  - Job creation and monitoring
  - Real-time status updates
  - Recipe verification

#### Repository Tests (`tests/test_repositories.py`)
- RecipeRepository CRUD operations
- IngestionRepository job queue operations
- Source deduplication
- Soft delete functionality

#### Schema Tests (`tests/test_schema.py`)
- Recipe validation
- Ingredient parsing
- Step structure validation

#### Ingestion Tests (`tests/test_ingestion*.py`)
- AI extraction validation
- Service layer logic
- Executor lifecycle management

#### Unit of Work Tests (`tests/test_unit_of_work.py`)
- Transaction management
- Rollback behavior
- Multi-repository transactions

#### Integration Tests (`tests/test_integration.py`)
- Full pipeline testing
- Database migrations

---

## 🚧 Missing: API Tests

### Required API Test Coverage

#### 1. Health Check Endpoint Tests

**File:** `tests/test_api_health.py`

```python
def test_health_check_success():
    """Health endpoint returns ok when database connected."""

def test_health_check_db_failure():
    """Health endpoint shows disconnected when DB fails."""
```

#### 2. Ingestion Endpoint Tests

**File:** `tests/test_api_ingestions.py`

**Creation:**
```python
def test_create_text_ingestion():
    """POST /api/ingestions creates text ingestion request."""

def test_create_webpage_ingestion():
    """POST /api/ingestions creates webpage ingestion request."""

def test_create_youtube_ingestion():
    """POST /api/ingestions creates YouTube ingestion request."""

def test_create_ingestion_missing_text():
    """POST /api/ingestions returns 400 when text source missing text field."""

def test_create_ingestion_missing_url():
    """POST /api/ingestions returns 400 when webpage source missing url field."""

def test_create_ingestion_image_not_implemented():
    """POST /api/ingestions returns 400 for image type (not yet implemented)."""
```

**Retrieval:**
```python
def test_get_ingestion_by_id():
    """GET /api/ingestions/{id} returns ingestion details."""

def test_get_ingestion_not_found():
    """GET /api/ingestions/{id} returns 404 for non-existent ID."""

def test_get_ingestion_with_completed_recipe():
    """GET /api/ingestions/{id} includes recipe_uuid when completed."""
```

**Listing:**
```python
def test_list_ingestions():
    """GET /api/ingestions returns paginated list."""

def test_list_ingestions_with_status_filter():
    """GET /api/ingestions?status=pending filters by status."""

def test_list_ingestions_pagination():
    """GET /api/ingestions respects skip and limit parameters."""

def test_list_ingestions_limit_max():
    """GET /api/ingestions enforces max limit of 100."""
```

#### 3. Recipe Endpoint Tests

**File:** `tests/test_api_recipes.py`

**Retrieval:**
```python
def test_get_recipe_by_uuid():
    """GET /api/recipes/{uuid} returns recipe details."""

def test_get_recipe_not_found():
    """GET /api/recipes/{uuid} returns 404 for non-existent UUID."""

def test_get_recipe_includes_all_fields():
    """GET /api/recipes/{uuid} returns complete recipe structure."""
```

**Listing:**
```python
def test_list_recipes():
    """GET /api/recipes returns paginated list."""

def test_list_recipes_search():
    """GET /api/recipes?search=pasta filters by title."""

def test_list_recipes_pagination():
    """GET /api/recipes respects skip and limit parameters."""

def test_list_recipes_excludes_deleted():
    """GET /api/recipes excludes soft-deleted recipes."""
```

#### 4. File Serving Endpoint Tests

**File:** `tests/test_api_files.py`

```python
def test_serve_image_file():
    """GET /api/files/{path} serves image with correct content-type."""

def test_serve_file_not_found():
    """GET /api/files/{path} returns 404 for non-existent file."""

def test_serve_file_path_traversal_blocked():
    """GET /api/files/{path} returns 400 for directory traversal attempts."""

def test_serve_file_content_types():
    """GET /api/files/{path} returns correct MIME types for different extensions."""
```

#### 5. Integration Tests

**File:** `tests/test_api_integration.py`

```python
def test_end_to_end_text_ingestion():
    """
    Full workflow:
    1. POST /api/ingestions (text)
    2. Worker processes job
    3. GET /api/ingestions/{id} shows completed
    4. GET /api/recipes/{uuid} returns recipe
    """

def test_end_to_end_with_files():
    """
    Full workflow with file storage:
    1. Create ingestion with image
    2. Worker processes and stores file
    3. GET /api/files/{path} serves image
    """

def test_concurrent_ingestions():
    """Multiple simultaneous API requests handled correctly."""
```

---

## Testing Implementation Plan

### Phase 1: API Unit Tests (Priority: HIGH)

**Estimated effort:** 4-6 hours

1. **Setup test infrastructure**
   - Create `tests/test_api_*.py` files
   - Configure FastAPI TestClient
   - Setup test database fixtures
   - Create helper functions for common operations

2. **Write endpoint tests**
   - Health check (simple, start here)
   - Ingestion endpoints (most important)
   - Recipe endpoints
   - File serving (requires file fixtures)

3. **Run tests**
   - `pytest tests/test_api_*.py -v`
   - Target: 100% coverage of API endpoints
   - Fix any failures

### Phase 2: API Integration Tests (Priority: MEDIUM)

**Estimated effort:** 2-3 hours

1. **End-to-end workflows**
   - API → Worker → Recipe retrieval
   - File upload → Storage → Serving

2. **Error scenarios**
   - Database failures
   - Worker offline
   - Invalid input handling

### Phase 3: Manual Testing (Priority: MEDIUM)

**Estimated effort:** 1-2 hours

1. **Enhance test script**
   - Add more error scenarios to `scripts/test_api.py`
   - Test all source types (text/webpage/youtube)
   - Verify OpenAPI docs accuracy

2. **Performance testing**
   - Load testing with multiple concurrent requests
   - Large file uploads
   - Search performance with many recipes

---

## Test Structure

### Test File Organization

```
tests/
├── test_api_health.py           # Health check endpoint
├── test_api_ingestions.py       # Ingestion CRUD endpoints
├── test_api_recipes.py          # Recipe endpoints
├── test_api_files.py            # File serving endpoint
├── test_api_integration.py      # End-to-end API tests
├── test_worker.py               # Worker unit tests ✅
├── test_worker_manual.py        # Worker integration tests ✅
└── conftest.py                  # Shared fixtures
```

### Fixtures Needed

**Add to `conftest.py`:**

```python
@pytest.fixture
def api_client():
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    from mise.api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client

@pytest.fixture
def sample_text_ingestion_payload():
    """Sample payload for text ingestion."""
    return {
        "source_type": "text",
        "text": "Pasta: boil noodles, add sauce",
        "metadata": {"test": True}
    }

@pytest.fixture
def sample_recipe_uuid(uow):
    """Create a sample recipe and return its UUID."""
    # Create recipe via repository
    # Return UUID for testing
    pass
```

---

## Success Criteria

### API Tests ✅ Complete when:
- [ ] All endpoints have unit tests
- [ ] All edge cases covered (400, 404, 500 errors)
- [ ] Integration tests pass end-to-end
- [ ] Test coverage > 90% for API routes
- [ ] Manual test script validates all workflows
- [ ] OpenAPI documentation matches implementation

### Current Test Status:
- ✅ Worker: 121 tests passing
- ✅ Repositories: All passing
- ✅ Schemas: All passing
- ✅ Ingestion: All passing
- ⏳ API: **Not yet implemented** (0 tests)

---

## Running Tests

### All Tests
```bash
pytest
```

### API Tests Only
```bash
pytest tests/test_api_*.py -v
```

### With Coverage
```bash
pytest --cov=src/mise/api --cov-report=html
```

### Integration Tests Only
```bash
pytest -m integration
```

### Manual Tests
```bash
# Worker
uv run python scripts/test_worker.py

# API (requires worker + API running)
uv run python scripts/test_api.py
```

---

## Next Steps

1. **Create API test files** - Start with `test_api_health.py`
2. **Add FastAPI TestClient fixture** - Update `conftest.py`
3. **Write endpoint tests** - Cover all 7 endpoints
4. **Run and fix** - Iterate until all tests pass
5. **Measure coverage** - Target 90%+ for API routes
6. **Document results** - Update this plan with results

---

## Notes

- Use `pytest-mock` for mocking external dependencies
- Use `TestClient` from FastAPI (synchronous, simpler than async)
- Reuse existing database fixtures from `conftest.py`
- Consider adding `pytest-xdist` for parallel test execution
- Add tests to CI/CD pipeline when available
