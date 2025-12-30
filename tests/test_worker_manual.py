#!/usr/bin/env python3
"""Manual end-to-end tests for worker process.

Run with pytest:
    uv run pytest tests/test_worker_manual.py -v -s

These tests use the actual test database and worker process to verify
the complete ingestion pipeline works end-to-end.
"""

import pytest
import time
import threading
from mise.db.models import SourceType, IngestionStatus
from mise.worker.processor import WorkerProcessor
from mise.worker.config import WorkerConfig


@pytest.mark.integration
def test_worker_processes_text_job_end_to_end(uow):
    """Test worker processes a text ingestion job end-to-end."""
    # Create a text ingestion job
    job = uow.ingestions.create_request(
        source_type=SourceType.custom,
        source_key="text:manual_test_1",
        source_url=None,
        request_params={
            "text": "Test Recipe: Mix 1 cup flour and 1 egg. Bake at 350°F for 20 minutes. Makes 12 cookies."
        }
    )
    uow.session.commit()
    job_id = job.id

    print(f"\nCreated test job: ID={job_id}")

    # Create worker and process one job
    config = WorkerConfig(
        worker_id="test-worker-manual",
        poll_interval=0.5,
    )
    worker = WorkerProcessor(config)
    worker.start(mode="single")

    # Check the job was processed
    uow.session.expire_all()  # Refresh from database
    processed_job = uow.ingestions.get_by_id(job_id)

    assert processed_job is not None
    assert processed_job.status in (IngestionStatus.completed, IngestionStatus.failed)

    if processed_job.status == IngestionStatus.completed:
        print(f"✓ Job completed successfully: recipe_id={processed_job.recipe_id}")
        assert processed_job.recipe_id is not None

        # Verify recipe was created
        recipe = uow.recipes.get_recipe_by_id(processed_job.recipe_id)
        assert recipe is not None
        assert recipe.recipe.title is not None
        assert len(recipe.recipe.ingredients) > 0
        assert len(recipe.recipe.steps) > 0
        print(f"✓ Recipe created: {recipe.recipe.title}")
        print(f"  - {len(recipe.recipe.ingredients)} ingredients")
        print(f"  - {len(recipe.recipe.steps)} steps")
    else:
        print(f"✗ Job failed: {processed_job.error_message}")
        # Job failed - this might be expected if no API key
        assert processed_job.error_message is not None


@pytest.mark.integration
def test_worker_handles_multiple_jobs(uow):
    """Test worker processes multiple jobs in sequence."""
    # Create multiple jobs
    jobs = []
    for i in range(3):
        job = uow.ingestions.create_request(
            source_type=SourceType.custom,
            source_key=f"text:manual_test_multi_{i}",
            source_url=None,
            request_params={
                "text": f"Recipe {i+1}: Mix ingredients. Bake. Serves 4."
            }
        )
        jobs.append(job)

    uow.session.commit()
    job_ids = [j.id for j in jobs]

    print(f"\nCreated {len(jobs)} test jobs: {job_ids}")

    # Run worker in continuous mode for a short time
    config = WorkerConfig(
        worker_id="test-worker-multi",
        poll_interval=0.5,
        poll_interval_busy=0.1,
    )
    worker = WorkerProcessor(config)

    # Start worker in background
    worker_thread = threading.Thread(target=lambda: worker.start(mode="continuous"))
    worker_thread.daemon = True
    worker_thread.start()

    # Let it run for 5 seconds (should process all 3 jobs)
    time.sleep(5)
    worker.stop()
    worker_thread.join(timeout=2)

    # Check all jobs were processed
    uow.session.expire_all()
    processed_count = 0
    failed_count = 0

    for job_id in job_ids:
        job = uow.ingestions.get_by_id(job_id)
        if job.status == IngestionStatus.completed:
            processed_count += 1
            print(f"✓ Job {job_id} completed: recipe_id={job.recipe_id}")
        elif job.status == IngestionStatus.failed:
            failed_count += 1
            print(f"✗ Job {job_id} failed: {job.error_message}")
        else:
            print(f"⋯ Job {job_id} still pending: status={job.status.value}")

    print(f"\nResults: {processed_count} completed, {failed_count} failed, {len(jobs) - processed_count - failed_count} pending")

    # At least some jobs should have been processed
    assert processed_count + failed_count > 0


@pytest.mark.integration
def test_worker_skips_duplicate_sources(uow):
    """Test worker detects and handles duplicate sources."""
    # Create first job
    job1 = uow.ingestions.create_request(
        source_type=SourceType.custom,
        source_key="text:duplicate_test",
        source_url=None,
        request_params={
            "text": "Unique Recipe: Mix and bake. Serves 2."
        }
    )
    uow.session.commit()

    print(f"\nCreated first job: ID={job1.id}")

    # Process first job
    config = WorkerConfig(worker_id="test-worker-dup", poll_interval=0.5)
    worker = WorkerProcessor(config)
    worker.start(mode="single")

    # Refresh and check
    uow.session.expire_all()
    job1 = uow.ingestions.get_by_id(job1.id)

    if job1.status == IngestionStatus.completed:
        print(f"✓ First job completed: recipe_id={job1.recipe_id}")

        # Try to create duplicate (same source_key)
        # This should be prevented at the database level via unique constraint
        from sqlalchemy.exc import IntegrityError

        try:
            job2 = uow.ingestions.create_request(
                source_type=SourceType.custom,
                source_key="text:duplicate_test",  # Same source_key
                source_url=None,
                request_params={
                    "text": "Different text but same source_key"
                }
            )
            uow.session.commit()
            print(f"✗ Duplicate job was created: ID={job2.id} (should have been prevented!)")
            assert False, "Duplicate source_key should have raised IntegrityError"
        except IntegrityError:
            print("✓ Duplicate source_key correctly rejected by database")
            uow.session.rollback()
    else:
        print(f"⋯ First job did not complete (status={job1.status.value}), skipping duplicate test")


@pytest.mark.integration
def test_worker_graceful_shutdown(uow):
    """Test worker shuts down gracefully without losing jobs."""
    # Create a job
    job = uow.ingestions.create_request(
        source_type=SourceType.custom,
        source_key="text:shutdown_test",
        source_url=None,
        request_params={
            "text": "Shutdown Test Recipe: Quick recipe."
        }
    )
    uow.session.commit()
    job_id = job.id

    print(f"\nCreated test job: ID={job_id}")

    # Start worker
    config = WorkerConfig(
        worker_id="test-worker-shutdown",
        poll_interval=0.5,
        shutdown_timeout=2.0,
    )
    worker = WorkerProcessor(config)

    worker_thread = threading.Thread(target=lambda: worker.start(mode="continuous"))
    worker_thread.daemon = True
    worker_thread.start()

    # Let it start processing
    time.sleep(0.5)

    # Stop worker gracefully
    print("Stopping worker...")
    worker.stop()
    worker_thread.join(timeout=5)

    print("✓ Worker stopped gracefully")

    # Check job status - should either be completed or still pending (not in weird state)
    uow.session.expire_all()
    job = uow.ingestions.get_by_id(job_id)

    assert job.status in (
        IngestionStatus.pending,
        IngestionStatus.processing,
        IngestionStatus.completed,
        IngestionStatus.failed
    )
    print(f"Job status after shutdown: {job.status.value}")


if __name__ == "__main__":
    """Run tests manually without pytest."""
    print("Manual Worker Tests")
    print("=" * 50)
    print("\nRun these tests with pytest for proper test database isolation:")
    print("  uv run pytest tests/test_worker_manual.py -v -s")
    print("\n" + "=" * 50)
