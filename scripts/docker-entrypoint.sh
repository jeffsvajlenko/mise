#!/bin/bash
set -e

echo "Starting Mise application..."

# Wait for postgres to be ready
if [ -n "$DATABASE_URL" ]; then
    echo "Waiting for PostgreSQL..."

    # Extract connection details from DATABASE_URL
    # Format: postgresql+psycopg://user:password@host:port/database
    DB_HOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\).*/\1/p')
    DB_USER=$(echo $DATABASE_URL | sed -n 's/.*\/\/\([^:]*\).*/\1/p')
    DB_NAME=$(echo $DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')

    until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; do
      echo "PostgreSQL is unavailable - sleeping"
      sleep 2
    done

    echo "PostgreSQL is ready"

    # Run database migrations
    echo "Running database migrations..."
    uv run alembic upgrade head
    echo "Migrations complete"
fi

# Execute the main command
echo "Starting application with command: $@"
exec "$@"
