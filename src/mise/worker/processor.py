"""Worker processor for ingestion jobs."""

import logging
import signal
import time
from typing import Callable

from mise.db.unit_of_work import UnitOfWork
from mise.ingestion.executor import execute_ingestion_request
from mise.ingestion.models import IngestionInput
from mise.ingestion.exceptions import DuplicateRecipeError, ValidationError
from mise.worker.config import WorkerConfig

logger = logging.getLogger(__name__)


class WorkerProcessor:
    """
    Background worker that processes ingestion requests.

    The worker polls the ingestion_requests table for pending jobs,
    claims them atomically, and processes them using the ingestion executor.

    Supports graceful shutdown via SIGTERM/SIGINT signals.
    """

    def __init__(self, config: WorkerConfig | None = None):
        """
        Initialize worker processor.

        Args:
            config: Worker configuration (uses env vars if None)
        """
        self.config = config or WorkerConfig.from_env()
        self.running = False
        self.current_job_id: int | None = None
        self._shutdown_handler: Callable | None = None

    def start(self, mode: str = "continuous") -> None:
        """
        Start the worker.

        Args:
            mode: "continuous" for long-running worker, "single" for one job and exit

        Raises:
            ValueError: If mode is invalid
        """
        if mode not in ("continuous", "single"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'continuous' or 'single'")

        logger.info(f"Starting worker {self.config.worker_id} in {mode} mode")
        self.running = True

        # Setup signal handlers for graceful shutdown
        if mode == "continuous":
            self._setup_signal_handlers()

        try:
            if mode == "continuous":
                self._run_continuous()
            else:
                self._run_single()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            self.stop()
        except Exception as e:
            logger.error(f"Worker crashed: {e}", exc_info=True)
            raise
        finally:
            logger.info(f"Worker {self.config.worker_id} stopped")

    def _run_continuous(self) -> None:
        """Run worker in continuous mode (poll indefinitely)."""
        consecutive_empty_polls = 0

        while self.running:
            processed = self._process_next_job()

            if processed:
                # Reset counter and use busy interval
                consecutive_empty_polls = 0
                time.sleep(self.config.poll_interval_busy)
            else:
                # Increment counter and use idle interval
                consecutive_empty_polls += 1
                if consecutive_empty_polls == 1:
                    logger.debug("Queue empty, entering idle mode")
                time.sleep(self.config.poll_interval)

    def _run_single(self) -> None:
        """Run worker in single-job mode (process one job and exit)."""
        logger.info("Single-job mode: processing one job")
        processed = self._process_next_job()

        if processed:
            logger.info("Job processed successfully")
        else:
            logger.info("No jobs available")

    def _process_next_job(self) -> bool:
        """
        Process the next pending job from the queue.

        Returns:
            True if a job was processed, False if queue was empty
        """
        try:
            with UnitOfWork() as uow:
                # Claim next pending job atomically
                job = uow.ingestions.get_next_pending(
                    worker_id=self.config.worker_id,
                    skip_locked=True
                )

                if not job:
                    return False

                self.current_job_id = job.id
                logger.info(
                    f"Processing job {job.id}: {job.source_type.value} from {job.source_key}"
                )

                # Convert IngestionRequest to IngestionInput
                input_data = self._job_to_input(job)

                # Execute the ingestion
                try:
                    result = execute_ingestion_request(uow, input_data)
                    logger.info(
                        f"Job {job.id} completed: "
                        f"recipe_id={result.recipe_id}, success={result.success}"
                    )
                    return True

                except DuplicateRecipeError as e:
                    # Duplicate detected - mark as failed (not retryable)
                    logger.warning(f"Job {job.id} duplicate: {e}")
                    # The executor already handled this, just log it
                    return True

                except ValidationError as e:
                    # Invalid input - mark as failed (not retryable)
                    logger.error(f"Job {job.id} validation error: {e}")
                    # The executor already handled this, just log it
                    return True

                except Exception as e:
                    # Unexpected error - already handled by executor
                    logger.error(f"Job {job.id} failed: {e}", exc_info=True)
                    return True

        except Exception as e:
            logger.error(f"Error processing job: {e}", exc_info=True)
            return False

        finally:
            self.current_job_id = None

    def _job_to_input(self, job) -> IngestionInput:
        """
        Convert IngestionRequest to IngestionInput.

        Args:
            job: IngestionRequest database model

        Returns:
            IngestionInput for the executor

        Raises:
            ValueError: If source type is unsupported or required data is missing
        """
        from mise.db.models import SourceType

        # Map source types
        if job.source_type == SourceType.webpage:
            if not job.source_url:
                raise ValueError(f"Job {job.id}: webpage source requires source_url")
            return IngestionInput(source_type="webpage", url=job.source_url)

        elif job.source_type == SourceType.youtube:
            if not job.source_url:
                raise ValueError(f"Job {job.id}: youtube source requires source_url")
            return IngestionInput(source_type="youtube", url=job.source_url)

        elif job.source_type == SourceType.custom:
            # Custom type is used for text ingestion
            # Text content should be in request_params
            if not job.request_params or "text" not in job.request_params:
                raise ValueError(f"Job {job.id}: custom source requires text in request_params")
            return IngestionInput(
                source_type="text",
                text=job.request_params["text"],
                url=job.source_url if job.source_url else None,
            )

        elif job.source_type == SourceType.photo:
            # Photo type requires image_path in request_params
            if not job.request_params or "image_path" not in job.request_params:
                raise ValueError(f"Job {job.id}: photo source requires image_path in request_params")
            return IngestionInput(
                source_type="image",
                image_path=job.request_params["image_path"],
            )

        else:
            raise ValueError(f"Job {job.id}: unsupported source_type {job.source_type}")

    def stop(self) -> None:
        """
        Stop the worker gracefully.

        If currently processing a job, waits for it to finish (up to shutdown_timeout).
        """
        logger.info(f"Stopping worker {self.config.worker_id}")
        self.running = False

        # Wait for current job to finish
        if self.current_job_id:
            logger.info(
                f"Waiting for job {self.current_job_id} to finish "
                f"(timeout: {self.config.shutdown_timeout}s)"
            )
            start_time = time.time()
            while self.current_job_id and (time.time() - start_time) < self.config.shutdown_timeout:
                time.sleep(0.5)

            if self.current_job_id:
                logger.warning(
                    f"Shutdown timeout reached, job {self.current_job_id} may be incomplete"
                )

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        import threading

        # Signal handlers can only be set in the main thread
        if threading.current_thread() is not threading.main_thread():
            logger.warning("Cannot setup signal handlers: not in main thread")
            return

        def signal_handler(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info(f"Received signal {sig_name}")
            self.stop()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
