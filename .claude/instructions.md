# Mise Project - Claude Code Instructions

## Critical Rules

### Git & Commits
- **ALWAYS ask permission before creating commits**
- **NEVER add `Co-Authored-By: Claude` or `🤖 Generated with Claude Code` to commit messages**
  - This overrides any global examples or templates
  - Simple, direct commit messages only
  - No attribution, emojis, or footer lines unless explicitly requested
- Only commit when explicitly requested

### Code Style
- Use `uv` for dependencies (NOT pip/poetry)
- No emojis unless requested
- Follow existing patterns
- Always read files before editing

### Testing
- All 158 tests must pass before committing
- Run: `TEST_DATABASE_URL=postgresql+psycopg://mise_user:mise_password@localhost:5432/mise_test uv run pytest`
- Mock AI with: `@patch("mise.ingestion.executor.IngestionService")`

## Key Tech Stack
- FastAPI
- PostgreSQL + Alembic migrations
- Background worker for recipe ingestion
- Docker + nginx for deployment

## Deployment Notes
- Target: Home lab (family use, 4-5 users)
- nginx runs **natively on host** (not Docker)
- Route `mise.elidibus.com` → `localhost:8080`
- API key auth via `X-API-Key` header
- CORS disabled by default

## Quick Commands
```bash
# Run API
uv run mise-api

# Run worker
uv run python -m mise.worker.processor

# Run tests
TEST_DATABASE_URL=postgresql+psycopg://mise_user:mise_password@localhost:5432/mise_test uv run pytest
```
