#!/usr/bin/env python3
"""Manual test script for worker process."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mise.db.unit_of_work import UnitOfWork
from mise.db.models import SourceType
from mise.worker.processor import WorkerProcessor
from mise.worker.config import WorkerConfig

from dotenv import load_dotenv

# Load variables from .env into the environment
load_dotenv()


def create_test_jobs():
    """Create test ingestion requests in the database."""
    print("=== Creating Test Jobs ===")

    with UnitOfWork() as uow:
        # Create a text ingestion job
        job1 = uow.ingestions.create_request(
            source_type=SourceType.custom,
            source_key="text:test123",
            source_url=None,
            request_params={"text": "Simple test recipe: Mix 1 cup flour, 1 egg. Bake at 350°F for 20 minutes."}
        )
        uow.session.flush()
        print(f"Created text job: ID={job1.id}, source_key={job1.source_key}")

        # Create a URL ingestion job (will fail without real URL, but tests job claiming)
        job2 = uow.ingestions.create_request(
            source_type=SourceType.webpage,
            source_key="https://example.com/recipe",
            source_url="https://example.com/recipe",
            request_params={}
        )
        uow.session.flush()
        print(f"Created webpage job: ID={job2.id}, source_key={job2.source_key}")

        uow.session.commit()

    print(f"\n✓ Created 2 test jobs\n")


def test_single_mode():
    """Test worker in single-job mode."""
    print("=== Testing Worker (Single Mode) ===\n")

    config = WorkerConfig(
        worker_id="test-worker-single",
        poll_interval=1.0,
    )

    worker = WorkerProcessor(config)
    worker.start(mode="single")

    print("\n✓ Worker processed one job and exited\n")


def test_continuous_mode():
    """Test worker in continuous mode (runs for a few seconds)."""
    print("=== Testing Worker (Continuous Mode) ===")
    print("Worker will run for 10 seconds, processing all pending jobs...")
    print("Press Ctrl+C to stop early\n")

    import threading
    import time

    config = WorkerConfig(
        worker_id="test-worker-continuous",
        poll_interval=2.0,
        poll_interval_busy=0.5,
    )

    worker = WorkerProcessor(config)

    # Start worker in background thread
    worker_thread = threading.Thread(target=lambda: worker.start(mode="continuous"))
    worker_thread.daemon = True
    worker_thread.start()

    try:
        # Let it run for 10 seconds
        time.sleep(10)
        print("\nStopping worker...")
        worker.stop()
        worker_thread.join(timeout=5)
    except KeyboardInterrupt:
        print("\nCtrl+C received, stopping worker...")
        worker.stop()
        worker_thread.join(timeout=5)

    print("✓ Worker stopped\n")


def check_results():
    """Check the results in the database."""
    print("=== Checking Results ===")

    with UnitOfWork() as uow:
        from sqlalchemy import text

        # Check ingestion requests
        result = uow.session.execute(text("""
            SELECT id, source_key, status, recipe_id
            FROM ingestion_requests
            ORDER BY id DESC
            LIMIT 5
        """))

        print("\nRecent ingestion requests:")
        for row in result:
            status_indicator = "✓" if row[2] == "completed" else "✗" if row[2] == "failed" else "⋯"
            print(f"  {status_indicator} ID={row[0]}, status={row[2]}, source_key={row[1]}, recipe_id={row[3]}")

        # Check recipes
        result = uow.session.execute(text("""
            SELECT id, uuid, data->'title' as title
            FROM recipes
            ORDER BY id DESC
            LIMIT 5
        """))

        print("\nRecent recipes:")
        for row in result:
            print(f"  • ID={row[0]}, UUID={row[1]}, Title={row[2]}")


if __name__ == "__main__":
    print("Worker Process Test")
    print("=" * 50)

    import argparse

    parser = argparse.ArgumentParser(description="Test worker process")
    parser.add_argument(
        "mode",
        choices=["create", "single", "continuous", "check"],
        help="Test mode: create (make jobs), single (process one), continuous (run for 10s), check (view results)"
    )

    args = parser.parse_args()

    if args.mode == "create":
        create_test_jobs()
    elif args.mode == "single":
        test_single_mode()
    elif args.mode == "continuous":
        test_continuous_mode()
    elif args.mode == "check":
        check_results()

    print("=" * 50)
    print("Test completed!")
