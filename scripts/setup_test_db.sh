#!/bin/bash
# Setup test database from scratch

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Setting up test database ===${NC}\n"

# Check if postgres is running
if ! docker-compose ps postgres | grep -q "Up"; then
    echo -e "${RED}PostgreSQL is not running. Start it with: docker-compose up -d postgres${NC}"
    exit 1
fi

# Drop and recreate test database
echo -e "${YELLOW}Dropping existing test database...${NC}"
docker-compose exec -T postgres psql -U mise_user -d postgres -c "DROP DATABASE IF EXISTS mise_test" 2>/dev/null || true

echo -e "${YELLOW}Creating test database...${NC}"
docker-compose exec -T postgres psql -U mise_user -d postgres -c "CREATE DATABASE mise_test"

# Run migrations
echo -e "${YELLOW}Running migrations...${NC}"
DATABASE_URL=postgresql+psycopg://mise_user:mise_password@localhost:5432/mise_test uv run alembic upgrade head

echo -e "\n${GREEN}✓ Test database ready!${NC}"
echo -e "Run tests with: ${YELLOW}./scripts/test.sh${NC}"
