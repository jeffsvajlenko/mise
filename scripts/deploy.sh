#!/bin/bash
set -e

# Mise Homelab Deployment Script
# This script pulls the latest code, rebuilds Docker images, and restarts services

echo "========================================="
echo "Mise Homelab Deployment"
echo "========================================="
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo "Error: Not a git repository!"
    exit 1
fi

# Show current status
echo "Current branch: $(git branch --show-current)"
echo "Current commit: $(git rev-parse --short HEAD)"
echo ""

# Pull latest changes
echo "Pulling latest changes from git..."
git pull
echo ""

# Show new commit
echo "Updated to commit: $(git rev-parse --short HEAD)"
echo ""

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose not found!"
    exit 1
fi

# Use proxy docker-compose file (for Caddy reverse proxy setup)
# Use docker-compose.prod.yml if you want built-in nginx instead
export COMPOSE_FILE="docker-compose.proxy.yml"

echo "Building Docker images..."
docker-compose build --no-cache api worker
echo ""

echo "Running database migrations..."
docker-compose run --rm api uv run alembic upgrade head
echo ""

echo "Restarting services..."
docker-compose up -d
echo ""

echo "Waiting for services to be healthy..."
sleep 5

# Check service status
docker-compose ps
echo ""

# Check API health
echo "Checking API health..."
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -f http://localhost:8000/api/health &> /dev/null; then
        echo "✓ API is healthy!"
        break
    fi
    attempt=$((attempt + 1))
    echo "Waiting for API to be ready... ($attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "Warning: API health check failed after $max_attempts attempts"
    echo "Check logs with: docker-compose logs api"
fi

echo ""
echo "========================================="
echo "Deployment complete!"
echo "========================================="
echo ""
echo "Useful commands:"
echo "  View logs:        docker-compose logs -f"
echo "  View API logs:    docker-compose logs -f api"
echo "  View worker logs: docker-compose logs -f worker"
echo "  Check status:     docker-compose ps"
echo "  Stop services:    docker-compose down"
echo ""
