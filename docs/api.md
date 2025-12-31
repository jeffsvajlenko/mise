# Mise API Documentation

## Overview

The Mise API is a RESTful service for recipe management and ingestion. It provides endpoints for:
- Creating recipe ingestion requests
- Monitoring ingestion status
- Retrieving and searching recipes
- Serving recipe files (images, etc.)

## Getting Started

### Start the API Server

```bash
# Default (localhost:8000)
uv run mise-api

# Custom host and port
uv run mise-api --host 0.0.0.0 --port 3000

# Development mode with auto-reload
uv run mise-api --reload

# With custom log level
uv run mise-api --log-level debug
```

### Start the Worker

The API creates ingestion requests, but a worker process must be running to process them:

```bash
uv run python -m mise.worker.processor
```

### API Documentation

Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Endpoints

### Health Check

#### `GET /api/health`

Check API and database health.

**Response:**
```json
{
  "status": "ok",
  "database": "connected"
}
```

---

### Ingestions

#### `POST /api/ingestions`

Create a new recipe ingestion request.

**Request Body:**
```json
{
  "source_type": "text",
  "text": "Recipe content here...",
  "metadata": {}
}
```

**Source Types:**
- `text` - Raw text recipe (requires `text` field)
- `webpage` - Web URL (requires `url` field)
- `youtube` - YouTube video (requires `url` field)
- `image` - Image file (not yet implemented via API)

**Response (201 Created):**
```json
{
  "id": 123,
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "source_type": "custom",
  "source_key": "text:abc123",
  "source_url": null,
  "recipe_id": null,
  "recipe_uuid": null,
  "created_at": "2025-01-01T12:00:00",
  "updated_at": "2025-01-01T12:00:00",
  "processing_started_at": null,
  "processing_completed_at": null,
  "worker_id": null,
  "retry_count": 0,
  "max_retries": 3
}
```

#### `GET /api/ingestions/{id}`

Get an ingestion request by ID.

**Response (200 OK):**
```json
{
  "id": 123,
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "source_type": "custom",
  "source_key": "text:abc123",
  "source_url": null,
  "recipe_id": 456,
  "recipe_uuid": "7d5690cb-e29b-41d4-a716-446655440001",
  "created_at": "2025-01-01T12:00:00",
  "updated_at": "2025-01-01T12:00:10",
  "processing_started_at": "2025-01-01T12:00:01",
  "processing_completed_at": "2025-01-01T12:00:10",
  "worker_id": "worker-1",
  "retry_count": 0,
  "max_retries": 3
}
```

#### `GET /api/ingestions`

List ingestion requests with optional filtering.

**Query Parameters:**
- `status` (optional) - Filter by status: `pending`, `processing`, `completed`, `failed`, `cancelled`
- `skip` (optional) - Number of records to skip (default: 0)
- `limit` (optional) - Maximum records to return (default: 20, max: 100)

**Response (200 OK):**
```json
{
  "ingestions": [
    {
      "id": 123,
      "uuid": "...",
      "status": "completed",
      ...
    }
  ],
  "total": 100,
  "skip": 0,
  "limit": 20
}
```

---

### Recipes

#### `GET /api/recipes/{uuid}`

Get a recipe by UUID.

**Response (200 OK):**
```json
{
  "id": "7d5690cb-e29b-41d4-a716-446655440001",
  "title": "Chocolate Chip Cookies",
  "description": "Classic homemade cookies",
  "ingredients": [
    {
      "text": "2 cups all-purpose flour",
      "name": "flour",
      "preparation": "all-purpose",
      "quantity": 2.0,
      "unit": "cups",
      "notes": null,
      "optional": false
    }
  ],
  "steps": [
    {
      "instruction": "Preheat oven to 350°F",
      "substeps": null,
      "time_minutes": null,
      "notes": null
    }
  ],
  "tags": [
    {"key": "cuisine", "value": "american"},
    {"key": "meal-type", "value": "dessert"}
  ],
  "prep_time": 15,
  "cook_time": 12,
  "total_time": 27,
  "servings": 24,
  "yield_amount": "24 cookies",
  "image_url": null,
  "video_url": null,
  "source_url": null,
  "author": null,
  "notes": null,
  "cuisine": "American",
  "files": [],
  "resource_urls": []
}
```

#### `GET /api/recipes`

List recipes with optional search.

**Query Parameters:**
- `search` (optional) - Search term (searches title)
- `skip` (optional) - Number of records to skip (default: 0)
- `limit` (optional) - Maximum records to return (default: 20, max: 100)

**Response (200 OK):**
```json
{
  "recipes": [
    {
      "id": "...",
      "title": "Chocolate Chip Cookies",
      ...
    }
  ],
  "total": 50,
  "skip": 0,
  "limit": 20
}
```

---

### Files

#### `GET /api/files/{path}`

Serve recipe files (images, videos, etc.).

**Example:**
```
GET /api/files/recipes/7d5690cb-e29b-41d4-a716-446655440001/original_1.jpg
```

**Response:**
- File content with appropriate Content-Type header
- 404 if file not found
- 400 if path is invalid (security check)

**Supported file types:**
- Images: .jpg, .jpeg, .png, .gif, .webp
- Videos: .mp4
- Documents: .pdf

---

## Typical Workflow

### 1. Create an Ingestion Request

```bash
curl -X POST http://localhost:8000/api/ingestions \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "text",
    "text": "Chocolate Chip Cookies\n\nIngredients:\n- 2 cups flour\n..."
  }'
```

Response:
```json
{
  "id": 123,
  "status": "pending",
  ...
}
```

### 2. Monitor Ingestion Status

```bash
curl http://localhost:8000/api/ingestions/123
```

Response:
```json
{
  "id": 123,
  "status": "completed",
  "recipe_id": 456,
  "recipe_uuid": "7d5690cb-...",
  ...
}
```

### 3. Retrieve the Recipe

```bash
curl http://localhost:8000/api/recipes/7d5690cb-e29b-41d4-a716-446655440001
```

---

## Error Responses

### 400 Bad Request

Invalid request (missing required fields, invalid data, etc.)

```json
{
  "detail": "text source requires 'text' field"
}
```

### 404 Not Found

Resource not found

```json
{
  "detail": "Recipe not found"
}
```

### 500 Internal Server Error

Server error (check logs)

```json
{
  "detail": "Internal server error"
}
```

---

## Manual Testing

Use the provided test script to verify the API:

```bash
# Start API server
uv run mise-api

# In another terminal, start worker
uv run python -m mise.worker.processor

# In a third terminal, run tests
uv run python scripts/test_api.py
```

The test script will:
1. Check health endpoint
2. Create a text ingestion
3. Monitor ingestion status
4. Retrieve the created recipe
5. List recipes and ingestions

---

## Configuration

### Environment Variables

See `.env.development` for configuration options:

```bash
# Database
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/mise

# File Storage
FILE_STORAGE_PATH=./data/files

# AI (for recipe extraction)
ANTHROPIC_API_KEY=sk-...
AI_MODEL=claude-haiku-4-5-20251001

# Logging
SQLALCHEMY_ECHO=False
```

### CLI Options

```
mise-api --help

options:
  --host TEXT         Host to bind to (default: 0.0.0.0)
  --port INTEGER      Port to bind to (default: 8000)
  --reload            Enable auto-reload on code changes
  --log-level TEXT    Logging level: debug, info, warning, error
```

---

## Next Steps

Future enhancements to consider:

1. **Authentication** - Add API key or JWT authentication
2. **Rate Limiting** - Prevent API abuse
3. **Image Upload** - Support direct image file uploads
4. **Recipe Updates** - `PUT /api/recipes/{uuid}` endpoint
5. **Recipe Deletion** - `DELETE /api/recipes/{uuid}` endpoint
6. **Advanced Search** - Full-text search, tag filtering
7. **Pagination Improvements** - Cursor-based pagination
8. **WebSocket Support** - Real-time ingestion status updates
9. **Batch Operations** - Upload multiple recipes at once
10. **Export Endpoints** - Export recipes to various formats

---

## Implementation Files

```
src/mise/api/
├── main.py              # FastAPI app initialization
├── cli.py               # CLI for starting API server
├── dependencies.py      # Dependency injection
└── routes/
    ├── health.py        # Health check endpoints
    ├── ingestions.py    # Ingestion endpoints
    ├── recipes.py       # Recipe endpoints
    └── files.py         # File serving endpoints
```
