"""Worker configuration."""

import os
from dataclasses import dataclass


@dataclass
class WorkerConfig:
    """Configuration for worker process."""

    # Worker identification
    worker_id: str = "worker-1"

    # Polling configuration
    poll_interval: float = 5.0  # seconds between polls when queue is empty
    poll_interval_busy: float = 0.5  # seconds between polls when processing jobs

    # Processing configuration
    max_retries: int = 3  # Maximum retry attempts for failed jobs
    retry_delay: float = 60.0  # seconds to wait before retrying failed jobs

    # Graceful shutdown
    shutdown_timeout: float = 30.0  # seconds to wait for current job to finish

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        """
        Create configuration from environment variables.

        Returns:
            WorkerConfig instance with values from environment
        """
        return cls(
            worker_id=os.getenv("WORKER_ID", "worker-1"),
            poll_interval=float(os.getenv("WORKER_POLL_INTERVAL", "5.0")),
            poll_interval_busy=float(os.getenv("WORKER_POLL_INTERVAL_BUSY", "0.5")),
            max_retries=int(os.getenv("WORKER_MAX_RETRIES", "3")),
            retry_delay=float(os.getenv("WORKER_RETRY_DELAY", "60.0")),
            shutdown_timeout=float(os.getenv("WORKER_SHUTDOWN_TIMEOUT", "30.0")),
        )
