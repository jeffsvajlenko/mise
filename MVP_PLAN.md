# MVP Completion Plan

## Current State

### ✅ Completed
- **Layer 5: AI Extraction** - Claude-based recipe extraction from text, images, YouTube, webpages
- **Layer 4: Ingestion Service** - Recipe extraction, validation, storage (including image files)
- **Layer 3: Ingestion Executor** - IngestionRequest lifecycle management, duplicate detection
- **Database Schema** - Recipes, IngestionRequests, full migration system
- **Repository Layer** - RecipeRepository, IngestionRepository with CRUD operations
- **Unit of Work Pattern** - Transaction management
- **File Storage** - Image storage with metadata

### 🚧 Remaining for MVP

#### 1. **Layer 2: Worker Process** (Priority: HIGH)
Background worker that processes ingestion requests from the queue.

**Files to create:**
- `src/mise/worker/processor.py` - Main worker loop
- `src/mise/worker/config.py` - Worker configuration (polling interval, concurrency)
- `src/mise/worker/__init__.py` - Worker exports

**Key features:**
- Poll `ingestion_requests` table for pending jobs
- Use `IngestionRepository.get_next_pending()` for atomic job claiming
- Call `execute_ingestion_request()` for each job
- Handle graceful shutdown (SIGTERM, SIGINT)
- Configurable polling interval (default: 5 seconds)
- Error handling and retry logic
- Optional: Worker heartbeat/status tracking

**Worker modes:**
1. **Continuous mode** - Long-running process that polls continuously
2. **Single-job mode** - Process one job and exit (for testing/cron)

**Management:**
- Start: `uv run mise-worker` (CLI command)
- Stop: Send SIGTERM signal
- Status: Check worker_id and processing_started_at in DB

**Testing:**
- Unit tests with mocked repository
- Integration tests with actual database
- Manual test script to enqueue and process jobs

---

#### 2. **Layer 1: FastAPI Application** (Priority: HIGH)

RESTful API for recipe management and ingestion.

**Files to create:**
- `src/mise/api/main.py` - FastAPI app initialization
- `src/mise/api/routes/recipes.py` - Recipe CRUD endpoints
- `src/mise/api/routes/ingestions.py` - Ingestion request endpoints
- `src/mise/api/routes/files.py` - File serving endpoints
- `src/mise/api/schemas/` - Pydantic request/response models
- `src/mise/api/dependencies.py` - Dependency injection (UoW, etc.)
- `src/mise/api/__init__.py` - API exports

**Endpoints:**

##### **Recipes** (`/api/recipes`)
- `GET /api/recipes` - List recipes (pagination, filtering)
  - Query params: `skip`, `limit`, `search`, `tag`
  - Response: `{"recipes": [...], "total": 100, "skip": 0, "limit": 20}`
- `GET /api/recipes/{id}` - Get recipe by ID or UUID
  - Support both integer ID and UUID
  - Response: Full recipe with files, source info
- `GET /api/recipes/{id}/source` - Get ingestion source info
  - Returns IngestionRequest details for this recipe
- `PUT /api/recipes/{id}` - Update recipe
  - Request: Partial recipe update
  - Response: Updated recipe
- `DELETE /api/recipes/{id}` - Soft delete recipe
  - Sets `deleted_at` timestamp
- `POST /api/recipes/{id}/restore` - Restore soft-deleted recipe

##### **Ingestions** (`/api/ingestions`)
- `POST /api/ingestions` - Create ingestion request
  - Request: `{"source_type": "text|webpage|youtube|image", "text": "...", "url": "...", "image_data": "base64..."}`
  - Response: `{"ingestion_id": 123, "status": "pending"}`
  - Optionally trigger worker if not running
- `GET /api/ingestions` - List ingestion requests
  - Query params: `status`, `skip`, `limit`
  - Response: List of ingestion requests with status
- `GET /api/ingestions/{id}` - Get ingestion request details
  - Response: Full ingestion request with recipe_id if completed
- `POST /api/ingestions/{id}/retry` - Retry failed ingestion
  - Reset status to pending, increment retry_count

##### **Files** (`/api/files`)
- `GET /api/files/{path:path}` - Serve recipe files
  - Path matches `recipes/{uuid}/{filename}`
  - Returns file with correct Content-Type header
  - Optional: Image thumbnailing/resizing

##### **Health/Status**
- `GET /api/health` - Health check
  - Check database connection
  - Check worker status (last heartbeat)
  - Response: `{"status": "healthy", "database": "ok", "worker": "running"}`
- `GET /api/status` - System status
  - Recipe count, pending jobs, recent activity

**API Configuration:**
- CORS middleware (configurable origins)
- Error handling middleware (structured error responses)
- Request logging
- Authentication (optional for MVP, placeholder for future)

**Testing:**
- FastAPI TestClient for unit tests
- Integration tests with test database
- API documentation (automatic via FastAPI/OpenAPI)

---

#### 3. **CLI Commands** (Priority: MEDIUM)

Command-line interface for management tasks.

**Files to create:**
- `src/mise/cli/__init__.py` - CLI app using `click` or `typer`
- `src/mise/cli/commands.py` - Command implementations

**Commands:**
- `mise-worker` - Start worker process
  - Options: `--mode [continuous|single]`, `--worker-id`, `--poll-interval`
- `mise-api` - Start API server
  - Options: `--host`, `--port`, `--reload`
- `mise-db` - Database management
  - `mise-db migrate` - Run migrations
  - `mise-db status` - Show migration status
  - `mise-db reset` - Reset database (dev only)
- `mise-ingest` - Manual ingestion
  - `mise-ingest text "recipe text"` - Ingest from text
  - `mise-ingest url https://...` - Ingest from URL
  - `mise-ingest image path/to/image.jpg` - Ingest from image

**Update `pyproject.toml`:**
```toml
[project.scripts]
mise-worker = "mise.worker:main"
mise-api = "mise.api:main"
mise-db = "mise.cli:db_command"
mise-ingest = "mise.cli:ingest_command"
```

---

#### 4. **Configuration Management** (Priority: MEDIUM)

Centralized configuration for all components.

**Update `src/mise/config.py`:**
- Database settings (already exists)
- API settings (host, port, CORS origins)
- Worker settings (poll interval, max workers, retry limits)
- File storage settings (already exists)
- AI settings (already exists)
- Logging configuration

**Environment variables (.env.example):**
```bash
# Database
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/mise
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/mise_test

# API
API_HOST=0.0.0.0
API_PORT=8000
API_CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# Worker
WORKER_POLL_INTERVAL=5
WORKER_MAX_CONCURRENT=1
WORKER_ID=worker-1

# File Storage
FILE_STORAGE_PATH=./data/files

# AI
ANTHROPIC_API_KEY=sk-...
AI_MODEL=claude-haiku-4-5-20251001
AI_MAX_TOKENS=4096

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

#### 5. **Docker Setup** (Priority: LOW - Post MVP)

Containerization for easy deployment.

**Files to create:**
- `Dockerfile` - Multi-stage build for app
- `docker-compose.yml` - Full stack (postgres, api, worker)
- `.dockerignore` - Exclude unnecessary files

**Services:**
- `postgres` - Database
- `api` - FastAPI application
- `worker` - Background worker
- Optional: `nginx` - Reverse proxy

---

## Implementation Order

### Phase 1: Worker Process (Days 1-2)
1. Create worker module structure
2. Implement worker loop with job claiming
3. Add graceful shutdown handling
4. Write worker tests
5. Create CLI command for worker
6. Manual testing with test scripts

### Phase 2: FastAPI Application (Days 3-5)
1. Setup FastAPI app structure
2. Implement recipe endpoints (GET, LIST, UPDATE, DELETE)
3. Implement ingestion endpoints (CREATE, LIST, GET)
4. Implement file serving endpoint
5. Add error handling and middleware
6. Write API tests
7. Create CLI command for API server

### Phase 3: Integration & Polish (Day 6)
1. End-to-end testing (API → Worker → Database)
2. Update documentation
3. Create example scripts
4. Performance testing (concurrent ingestions)
5. Bug fixes and refinement

---

## Testing Strategy

### Unit Tests
- Worker: Job claiming, error handling, shutdown
- API: All endpoints with mocked dependencies
- CLI: Command parsing and execution

### Integration Tests
- Worker: Process actual ingestion requests from DB
- API: Full request/response cycle with test DB
- End-to-end: Submit via API, process via worker, retrieve recipe

### Manual Tests
- Start worker, submit jobs via scripts
- Use API via curl/Postman
- Test error scenarios (invalid input, API failures, etc.)

---

## Success Criteria

### Worker
- [ ] Can claim and process pending ingestion requests
- [ ] Handles concurrent workers (no duplicate processing)
- [ ] Graceful shutdown without losing jobs
- [ ] Retry failed jobs according to configuration
- [ ] Logs processing activity clearly

### API
- [ ] Can create ingestion requests for all source types
- [ ] Can retrieve recipes with full details
- [ ] Can list/search/filter recipes
- [ ] Can update and delete recipes
- [ ] Returns proper HTTP status codes and errors
- [ ] API documentation accessible at `/docs`

### CLI
- [ ] Worker starts and processes jobs
- [ ] API server starts and responds to requests
- [ ] Database commands work correctly

### Integration
- [ ] Submit image via API → Worker processes → Recipe retrievable
- [ ] Submit URL via API → Worker fetches and processes → Recipe available
- [ ] Multiple workers can run concurrently without conflicts
- [ ] Failed ingestions can be retried

---

## Dependencies to Add

```toml
[project.dependencies]
# Add these to pyproject.toml
fastapi = ">=0.109.0"
uvicorn = {version = ">=0.27.0", extras = ["standard"]}
click = ">=8.1.0"  # or typer = ">=0.9.0"
python-multipart = ">=0.0.6"  # For file uploads
```

---

## Notes

- **Authentication**: Not included in MVP. Add placeholder middleware for future.
- **Rate limiting**: Not in MVP. Consider for production.
- **Caching**: Not in MVP. Add Redis later if needed.
- **Webhooks**: Not in MVP. Could add for ingestion completion notifications.
- **Admin UI**: Not in MVP. FastAPI admin or separate frontend later.
- **Metrics/Monitoring**: Basic logging only. Add Prometheus/Grafana later.

---

## Post-MVP Enhancements

1. **Batch ingestion** - Upload CSV/JSON with multiple recipes
2. **Scheduled ingestion** - Periodic refresh of YouTube/webpage sources
3. **Image processing** - Thumbnail generation, format conversion
4. **Search improvements** - Full-text search with PostgreSQL FTS or Elasticsearch
5. **Recipe collections/cookbooks** - User-organized recipe groups
6. **Meal planning** - Weekly meal plans with shopping lists
7. **Nutrition calculation** - Parse ingredients for nutritional info
8. **Recipe scaling** - Adjust ingredient quantities for servings
9. **Print formatting** - Generate printable recipe cards
10. **Social features** - Sharing, ratings, comments
