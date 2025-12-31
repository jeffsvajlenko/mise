"""Tests for worker processor."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

from mise.worker.processor import WorkerProcessor
from mise.worker.config import WorkerConfig
from mise.db.models import SourceType, IngestionStatus
from mise.ingestion.models import IngestionResult
from mise.schema.recipe import Recipe, Ingredient, RecipeStep


@pytest.fixture
def worker_config():
    """Create test worker configuration."""
    return WorkerConfig(
        worker_id="test-worker",
        poll_interval=0.1,
        poll_interval_busy=0.05,
        shutdown_timeout=1.0,
    )


@pytest.fixture
def worker(worker_config):
    """Create worker instance for testing."""
    return WorkerProcessor(worker_config)


def test_worker_config_from_env(monkeypatch):
    """Test worker configuration from environment variables."""
    monkeypatch.setenv("WORKER_ID", "custom-worker")
    monkeypatch.setenv("WORKER_POLL_INTERVAL", "10.0")
    monkeypatch.setenv("WORKER_MAX_RETRIES", "5")

    config = WorkerConfig.from_env()

    assert config.worker_id == "custom-worker"
    assert config.poll_interval == 10.0
    assert config.max_retries == 5


def test_worker_initialization(worker_config):
    """Test worker initialization."""
    worker = WorkerProcessor(worker_config)

    assert worker.config == worker_config
    assert worker.running is False
    assert worker.current_job_id is None


def test_worker_single_mode_no_jobs(worker):
    """Test worker in single mode with empty queue."""
    mock_uow = Mock()
    mock_uow.ingestions.get_next_pending.return_value = None

    with patch("mise.worker.processor.UnitOfWork") as mock_uow_class:
        mock_uow_class.return_value.__enter__.return_value = mock_uow

        worker.start(mode="single")

        # Should poll once and exit
        mock_uow.ingestions.get_next_pending.assert_called_once_with(
            worker_id="test-worker",
            skip_locked=True,
        )


def test_worker_single_mode_processes_job(worker):
    """Test worker processes a job in single mode."""
    # Create a mock job
    mock_job = Mock()
    mock_job.id = 1
    mock_job.source_type = SourceType.custom
    mock_job.source_key = "text:abc123"
    mock_job.source_url = None
    mock_job.request_params = {"text": "Test recipe content"}

    # Mock the result
    test_uuid = uuid4()
    mock_result = IngestionResult.success_result(
        recipe_id=1,
        recipe_uuid=test_uuid,
        ingestion_id=1,
        processing_metadata={"model": "test"},
    )

    mock_uow = Mock()
    mock_uow.ingestions.get_next_pending.return_value = mock_job

    with patch("mise.worker.processor.UnitOfWork") as mock_uow_class:
        mock_uow_class.return_value.__enter__.return_value = mock_uow

        with patch("mise.worker.processor.execute_ingestion_request") as mock_execute:
            mock_execute.return_value = mock_result

            worker.start(mode="single")

            # Verify job was claimed
            mock_uow.ingestions.get_next_pending.assert_called_once()

            # Verify job was executed
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args
            assert call_args[0][0] == mock_uow  # UnitOfWork passed
            assert call_args[0][1].source_type == "text"
            assert call_args[0][1].text == "Test recipe content"


def test_job_to_input_webpage(worker):
    """Test converting webpage job to input."""
    mock_job = Mock()
    mock_job.id = 1
    mock_job.source_type = SourceType.webpage
    mock_job.source_url = "https://example.com/recipe"
    mock_job.request_params = {}

    input_data = worker._job_to_input(mock_job)

    assert input_data.source_type == "webpage"
    assert str(input_data.url) == "https://example.com/recipe"


def test_job_to_input_youtube(worker):
    """Test converting youtube job to input."""
    mock_job = Mock()
    mock_job.id = 1
    mock_job.source_type = SourceType.youtube
    mock_job.source_url = "https://youtube.com/watch?v=123"
    mock_job.request_params = {}

    input_data = worker._job_to_input(mock_job)

    assert input_data.source_type == "youtube"
    assert str(input_data.url) == "https://youtube.com/watch?v=123"


def test_job_to_input_text(worker):
    """Test converting text job to input."""
    mock_job = Mock()
    mock_job.id = 1
    mock_job.source_type = SourceType.custom
    mock_job.source_url = None
    mock_job.request_params = {"text": "Recipe content here"}

    input_data = worker._job_to_input(mock_job)

    assert input_data.source_type == "text"
    assert input_data.text == "Recipe content here"
    assert input_data.url is None


def test_job_to_input_image(worker):
    """Test converting image job to input."""
    mock_job = Mock()
    mock_job.id = 1
    mock_job.source_type = SourceType.photo
    mock_job.source_url = None
    mock_job.request_params = {"image_path": "/path/to/image.jpg"}

    input_data = worker._job_to_input(mock_job)

    assert input_data.source_type == "image"
    assert input_data.image_path == "/path/to/image.jpg"


def test_job_to_input_missing_data(worker):
    """Test that missing required data raises ValueError."""
    mock_job = Mock()
    mock_job.id = 1
    mock_job.source_type = SourceType.webpage
    mock_job.source_url = None  # Missing required URL
    mock_job.request_params = {}

    with pytest.raises(ValueError, match="webpage source requires source_url"):
        worker._job_to_input(mock_job)


def test_worker_stop(worker):
    """Test worker stop method."""
    worker.running = True
    worker.stop()

    assert worker.running is False


def test_worker_stop_with_current_job(worker):
    """Test worker stop waits for current job."""
    import threading
    import time

    worker.running = True
    worker.current_job_id = 123

    # Simulate job finishing after 0.2 seconds
    def finish_job():
        time.sleep(0.2)
        worker.current_job_id = None

    job_thread = threading.Thread(target=finish_job)
    job_thread.start()

    # Stop should wait for job to finish
    start = time.time()
    worker.stop()
    elapsed = time.time() - start

    assert worker.running is False
    assert worker.current_job_id is None
    assert 0.2 <= elapsed < 1.0  # Should wait ~0.2s (relaxed for CI/slow systems)
    job_thread.join()


def test_worker_continuous_mode_stops_on_signal(worker):
    """Test worker stops gracefully in continuous mode."""
    import threading
    import time

    mock_uow = Mock()
    mock_uow.ingestions.get_next_pending.return_value = None
    mock_uow.ingestions.reset_orphaned_jobs.return_value = 0

    with patch("mise.worker.processor.UnitOfWork") as mock_uow_class:
        mock_uow_class.return_value.__enter__.return_value = mock_uow

        # Start worker in background thread
        worker_thread = threading.Thread(target=lambda: worker.start(mode="continuous"))
        worker_thread.start()

        # Wait a bit for worker to start
        time.sleep(0.2)

        # Stop worker
        worker.stop()

        # Wait for thread to finish
        worker_thread.join(timeout=2.0)

        assert not worker_thread.is_alive()
        assert worker.running is False


@pytest.mark.integration
def test_worker_resets_orphaned_jobs_on_startup():
    """Test worker resets orphaned jobs from crashed instance on startup."""
    from mise.db.models import SourceType, IngestionStatus
    from datetime import datetime, timezone
    from mise.db.unit_of_work import UnitOfWork

    # Create orphaned job using a separate UnitOfWork and commit to database
    # (not using uow fixture because we need actual database commits for cross-session visibility)
    with UnitOfWork() as setup_uow:
        orphaned_job = setup_uow.ingestions.create_request(
            source_type=SourceType.custom,
            source_key="text:orphaned_test_startup",
            source_url=None,
            request_params={"text": "Orphaned recipe"}
        )
        # Manually set to processing (simulating a crash)
        orphaned_job.status = IngestionStatus.processing
        orphaned_job.worker_id = "crashed-worker"
        orphaned_job.processing_started_at = datetime.now(timezone.utc)
        setup_uow.session.commit()
        orphaned_job_id = orphaned_job.id

    try:
        # Start worker (should reset the orphaned job)
        config = WorkerConfig(worker_id="new-worker", poll_interval=0.5)
        worker = WorkerProcessor(config)

        # Mock the actual processing so we can test the reset happened
        # The worker will reset orphaned jobs, then claim and process the now-pending job
        mock_result = IngestionResult.success_result(
            recipe_id=1,
            recipe_uuid=uuid4(),
            ingestion_id=orphaned_job_id,
            processing_metadata={"model": "test"},
        )

        with patch("mise.worker.processor.execute_ingestion_request") as mock_execute:
            mock_execute.return_value = mock_result
            worker.start(mode="single")

        # Check the orphaned job was reset and then processed
        with UnitOfWork() as check_uow:
            job = check_uow.ingestions.get_by_id(orphaned_job_id)

            # Should be completed (was reset from processing → pending, then claimed and processed)
            # OR still processing if the mock didn't work properly
            assert job is not None
            assert job.status in (IngestionStatus.pending, IngestionStatus.processing, IngestionStatus.completed)

            # The key thing is that worker_id changed from "crashed-worker" to "new-worker"
            # This proves the reset happened (which clears worker_id), then the job was re-claimed
            if job.status == IngestionStatus.processing:
                # Job was claimed by new worker (proof of reset)
                assert job.worker_id == "new-worker", f"Expected new-worker, got {job.worker_id}"
            elif job.status == IngestionStatus.completed:
                # Job was fully processed
                assert job.recipe_id is not None

    finally:
        # Cleanup: delete the test job
        with UnitOfWork() as cleanup_uow:
            job = cleanup_uow.ingestions.get_by_id(orphaned_job_id)
            if job:
                cleanup_uow.session.delete(job)
                cleanup_uow.session.commit()
