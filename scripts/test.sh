#!/bin/bash
# Test runner script for mise project

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Mise Test Suite ===${NC}\n"

# Set test database URL
export TEST_DATABASE_URL="postgresql+psycopg://mise_user:mise_password@localhost:5432/mise_test"

# Check if database is running
if ! docker-compose exec -T postgres psql -U mise_user -d mise_test -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${YELLOW}Setting up test database...${NC}"

    # Check if database exists, create if not
    docker-compose exec -T postgres psql -U mise_user -d postgres -c "SELECT 1 FROM pg_database WHERE datname = 'mise_test'" | grep -q 1 || \
        docker-compose exec -T postgres psql -U mise_user -d postgres -c "CREATE DATABASE mise_test"

    # Run migrations
    echo -e "${YELLOW}Running migrations on test database...${NC}"
    DATABASE_URL=$TEST_DATABASE_URL uv run alembic upgrade head
fi

# Parse command line arguments
PYTEST_ARGS=()
COVERAGE=false
MARKERS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --unit|-u)
            MARKERS="unit"
            shift
            ;;
        --integration|-i)
            MARKERS="integration"
            shift
            ;;
        --verbose|-v)
            PYTEST_ARGS+=("-v")
            shift
            ;;
        --failfast|-x)
            PYTEST_ARGS+=("-x")
            shift
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# Add marker if specified
if [ ! -z "$MARKERS" ]; then
    PYTEST_ARGS+=("-m" "$MARKERS")
fi

# Run tests
echo -e "${YELLOW}Running tests...${NC}\n"

if [ "$COVERAGE" = true ]; then
    uv run pytest tests/ "${PYTEST_ARGS[@]}" --cov=src/mise --cov-report=term-missing --cov-report=html
    echo -e "\n${GREEN}Coverage report generated in htmlcov/index.html${NC}"
else
    uv run pytest tests/ "${PYTEST_ARGS[@]}"
fi

# Check exit code
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✓ All tests passed!${NC}"
else
    echo -e "\n${RED}✗ Some tests failed${NC}"
    exit 1
fi
