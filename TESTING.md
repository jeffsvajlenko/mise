# Testing Guide

## Quick Start

```bash
# One-time setup
docker-compose up -d postgres
./scripts/setup_test_db.sh

# Run tests
./scripts/test.sh
```

## Test Scripts

### `./scripts/setup_test_db.sh`
Drops and recreates the test database from scratch. Run this:
- First time setting up tests
- When database schema changes
- If tests are behaving strangely

### `./scripts/test.sh`
Main test runner with options:

```bash
./scripts/test.sh              # Run all tests
./scripts/test.sh --coverage   # Run with coverage report
./scripts/test.sh --unit       # Only unit tests (fast)
./scripts/test.sh --integration # Only integration tests
./scripts/test.sh -v           # Verbose output
./scripts/test.sh -x           # Stop on first failure
./scripts/test.sh tests/test_schema.py  # Run specific file
```

## Test Overview

**78 tests, 90% passing**

| Category | Tests | Coverage |
|----------|-------|----------|
| Database Models | 14 | 100% |
| Repositories | 15 | 100% |
| Unit of Work | 8 | 100% |
| Schema Validation | 15 | 94% |
| URL/Ingestion | 16 | 94% |
| Integration | 10 | 70% |

## Test Philosophy

**Integration tests > Unit tests**

We prioritize end-to-end integration tests that verify real workflows over exhaustive unit testing. Unit tests are added as needed for:
- Complex logic
- Edge cases
- Regressions

## Key Features

✅ **Isolated test database** - Tests never touch production data
✅ **Automatic cleanup** - Each test starts with clean slate
✅ **Fast execution** - Full suite runs in ~6 seconds
✅ **Good coverage** - Critical paths are tested

## Common Issues

**Connection refused**
```bash
docker-compose up -d postgres
```

**Table doesn't exist**
```bash
./scripts/setup_test_db.sh
```

**Tests are slow**
```bash
./scripts/test.sh --unit  # Skip integration tests
```

## More Info

See [tests/README.md](tests/README.md) for detailed documentation.
