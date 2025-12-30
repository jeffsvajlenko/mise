"""CLI for worker process."""

import logging
import sys

from mise.worker.config import WorkerConfig
from mise.worker.processor import WorkerProcessor


def setup_logging(level: str = "INFO") -> None:
    """
    Setup logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    """Main entry point for worker CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="Mise recipe ingestion worker")
    parser.add_argument(
        "--mode",
        choices=["continuous", "single"],
        default="continuous",
        help="Worker mode: continuous (long-running) or single (one job and exit)",
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        help="Worker identifier (overrides WORKER_ID env var)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        help="Polling interval in seconds when idle (overrides WORKER_POLL_INTERVAL)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    # Create config from environment
    config = WorkerConfig.from_env()

    # Override with CLI arguments
    if args.worker_id:
        config.worker_id = args.worker_id
    if args.poll_interval:
        config.poll_interval = args.poll_interval

    # Create and start worker
    worker = WorkerProcessor(config)

    try:
        worker.start(mode=args.mode)
    except Exception as e:
        logging.error(f"Worker failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
