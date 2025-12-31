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

        logger.info(f"=== Starting worker {self.config.worker_id} in {mode} mode ===")
        logger.info(f"Configuration: poll_interval={self.config.poll_interval}s, poll_interval_busy={self.config.poll_interval_busy}s")
        self.running = True

        # Reset orphaned jobs from crashed previous worker instance
        self._reset_orphaned_jobs()

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
            logger.info(f"=== Worker {self.config.worker_id} stopped ===")

    def _reset_orphaned_jobs(self) -> None:
        """Reset orphaned jobs from crashed previous worker instance."""
        try:
            with UnitOfWork() as uow:
                reset_count = uow.ingestions.reset_orphaned_jobs()
                uow.session.commit()

                if reset_count > 0:
                    logger.warning(
                        f"Reset {reset_count} orphaned job(s) from crashed worker instance "
                        f"(status: processing → pending)"
                    )
                else:
                    logger.info("No orphaned jobs found")
        except Exception as e:
            logger.error(f"Failed to reset orphaned jobs: {e}", exc_info=True)
            # Continue anyway - this is not fatal

    def _run_continuous(self) -> None:
        """Run worker in continuous mode (poll indefinitely)."""
        consecutive_empty_polls = 0
        jobs_processed = 0

        logger.info("Starting continuous polling loop")

        while self.running:
            processed = self._process_next_job()

            if processed:
                # Reset counter and use busy interval
                consecutive_empty_polls = 0
                jobs_processed += 1
                time.sleep(self.config.poll_interval_busy)
            else:
                # Increment counter and use idle interval
                consecutive_empty_polls += 1
                if consecutive_empty_polls == 1:
                    logger.info(f"Queue empty (processed {jobs_processed} jobs), entering idle mode")
                time.sleep(self.config.poll_interval)

        logger.info(f"Polling loop ended (processed {jobs_processed} total jobs)")

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
                    f"[Job {job.id}] Processing {job.source_type.value} from source_key={job.source_key}"
                )

                # Convert IngestionRequest to IngestionInput
                start_time = time.time()
                try:
                    input_data = self._job_to_input(job)
                except ValueError as e:
                    logger.error(f"[Job {job.id}] Invalid job data: {e}")
                    # Job has invalid data, can't process
                    return True

                # Execute the ingestion (passing job ID to update existing request)
                try:
                    result = execute_ingestion_request(uow, input_data, ingestion_id=job.id)
                    elapsed = time.time() - start_time

                    if result.success:
                        logger.info(
                            f"[Job {job.id}] ✓ SUCCESS - Created recipe_id={result.recipe_id} "
                            f"in {elapsed:.1f}s"
                        )
                        if result.processing_metadata:
                            tokens = result.processing_metadata.get('total_tokens', 0)
                            model = result.processing_metadata.get('model', 'unknown')
                            logger.info(f"[Job {job.id}]   AI: {model}, {tokens} tokens")
                    else:
                        logger.warning(
                            f"[Job {job.id}] ✗ FAILED - {result.error_message} "
                            f"(retryable={result.retryable}) after {elapsed:.1f}s"
                        )

                    # Commit the transaction to persist status updates
                    uow.session.commit()
                    return True

                except DuplicateRecipeError as e:
                    elapsed = time.time() - start_time
                    logger.warning(
                        f"[Job {job.id}] ⊘ DUPLICATE - {e} (detected in {elapsed:.1f}s)"
                    )
                    uow.session.commit()
                    return True

                except ValidationError as e:
                    elapsed = time.time() - start_time
                    logger.error(
                        f"[Job {job.id}] ✗ VALIDATION ERROR - {e} (failed in {elapsed:.1f}s)"
                    )
                    uow.session.commit()
                    return True

                except Exception as e:
                    elapsed = time.time() - start_time
                    logger.error(
                        f"[Job {job.id}] ✗ UNEXPECTED ERROR - {e} (failed in {elapsed:.1f}s)",
                        exc_info=True
                    )
                    uow.session.commit()
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
