# Data Directory

This directory contains local development data that is git-ignored.

## Structure

- **`postgres/`** - PostgreSQL database files (mounted from docker-compose)
- **`files/`** - Recipe file storage (photos, temporary ingestion files)
  - `files/recipes/{uuid}/` - Permanent recipe files
  - `files/ingestion-temp/ing_{id}/` - Temporary processing files

## Git Ignore

All contents are ignored by git except for:
- `files/.gitkeep` - Ensures directory structure exists

## Cleanup

To clean up local development data:

```bash
# Clean recipe files only
rm -rf data/files/*
# (Note: .gitkeep will be preserved)

# Clean database (WARNING: destroys all data)
docker-compose down -v
rm -rf data/postgres/
```

## Production

In production, file storage uses `/data/mise/files/` instead of this local directory.

See [docs/file-storage.md](../docs/file-storage.md) for details.
