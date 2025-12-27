# Quick Reference

## Common Commands

### Development (Default)

```bash
# Check database status
uv run python scripts/db_status.py

# Run migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Run example scripts
uv run python scripts/example_usage.py
```

### Production

```bash
# Set environment first
export ENV=production

# Or prefix each command
ENV=production alembic upgrade head

# Or use helper script
./scripts/run_prod.sh alembic upgrade head
```

## Environment Files

- **`.env.development`** - Development config (committed to git)
- **`.env.production`** - Production template (committed to git)
- **`.env.production.local`** - Actual production secrets (NOT committed)

## Database URLs

### Development
```
postgresql+psycopg://mise_user:mise_password@localhost:5432/mise
```

### Production (example)
```
postgresql+psycopg://mise_user:STRONG_PASSWORD@localhost:5432/mise_prod
```

## Workflow

### Making Schema Changes

1. Edit models in `src/mise/db/models.py`
2. Create migration: `alembic revision --autogenerate -m "what changed"`
3. Review the generated file in `alembic/versions/`
4. Apply migration: `alembic upgrade head`

### Deploying to Homelab

1. Set up production environment file on server
2. Run migrations: `ENV=production alembic upgrade head`
3. Start app with `ENV=production`

## Documentation

- [Environment Configuration](environment-config.md) - Detailed setup guide
- [Repository Pattern](repository-pattern.md) - Data access layer
- [Source Tracking](source-tracking.md) - Deduplication system
- [Architecture Review](architecture-review.md) - Design decisions
