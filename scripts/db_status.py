#!/usr/bin/env python3
"""
Database status check script.

Usage:
    python scripts/db_status.py
    uv run python scripts/db_status.py
"""
import sys
import os
from sqlalchemy import inspect, text

# Disable SQLAlchemy echo for this script to keep output clean
os.environ['SQLALCHEMY_ECHO'] = 'False'

from mise.db.database import engine, DATABASE_URL


def check_status():
    """Check database connection and display table information."""
    # Mask password in URL for display
    display_url = DATABASE_URL
    if "@" in display_url:
        parts = display_url.split("@")
        user_pass = parts[0].split("//")[1]
        if ":" in user_pass:
            user = user_pass.split(":")[0]
            display_url = display_url.replace(user_pass, f"{user}:****")

    print(f"Database URL: {display_url}\n")

    try:
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print("✓ Database connection successful!")
            if version:
                print(f"  PostgreSQL version: {version.split(' on ')[0]}\n")
            else:
                print()

        # Get table information
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        if not tables:
            print("⚠ No tables found")
            print("  Run: alembic upgrade head")
        else:
            print(f"✓ Found {len(tables)} table(s):")
            for table in tables:
                columns = inspector.get_columns(table)
                indexes = inspector.get_indexes(table)
                print(f"  - {table} ({len(columns)} columns, {len(indexes)} indexes)")

    except Exception as e:
        print(f"✗ Database connection failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    check_status()
