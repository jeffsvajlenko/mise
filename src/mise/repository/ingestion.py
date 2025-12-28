"""Repository for ingestion request operations."""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from mise.db.models import IngestionRequest, SourceType, IngestionStatus
from mise.repository.base import BaseRepository


class IngestionRepository(BaseRepository[IngestionRequest]):
    """
    Repository for IngestionRequest data access.

    Handles background job queue operations:
    - Creating ingestion requests
    - Claiming pending jobs (with atomic locking)
    - Updating status and progress
    - Finding duplicates by source_key
    - Linking completed ingestions to recipes
    """

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, IngestionRequest)

    def create_request(
        self,
        source_type: SourceType,
        source_key: str,
        source_url: str | None = None,
        priority: int = 0,
        requested_by: str | None = None,
        request_params: dict | None = None,
    ) -> IngestionRequest:
        """
        Create a new ingestion request.

        Args:
            source_type: Type of source (SourceType enum)
            source_key: Unique identifier for deduplication
            source_url: Original URL (if applicable)
            priority: Processing priority (higher = first, default 0)
            requested_by: User who requested this ingestion
            request_params: Additional request parameters

        Returns:
            Created IngestionRequest

        Raises:
            IntegrityError: If source_key already exists
        """
        request = IngestionRequest(
            source_type=source_type,
            source_key=source_key,
            source_url=source_url,
            status=IngestionStatus.pending,
            priority=priority,
            requested_by=requested_by,
            request_params=request_params,
            requested_at=datetime.now(timezone.utc),
        )
        self.session.add(request)
        return request

    def find_by_source_key(self, source_key: str) -> IngestionRequest | None:
        """
        Find an ingestion request by source_key.

        Useful for checking if a source has already been ingested.

        Args:
            source_key: Unique source identifier

        Returns:
            IngestionRequest or None if not found
        """
        stmt = select(IngestionRequest).where(IngestionRequest.source_key == source_key)
        return self.session.scalar(stmt)

    def get_next_pending(
        self,
        worker_id: str,
        skip_locked: bool = True
    ) -> IngestionRequest | None:
        """
        Claim the next pending job from the queue (atomically).

        This method uses SELECT FOR UPDATE to ensure only one worker
        claims a job, preventing race conditions.

        Args:
            worker_id: Identifier for the worker claiming this job
            skip_locked: If True, skip locked rows (non-blocking)

        Returns:
            IngestionRequest or None if queue is empty

        Example:
            >>> repo = IngestionRepository(session)
            >>> job = repo.get_next_pending("worker-1")
            >>> if job:
            ...     # Process job
            ...     repo.mark_completed(job.id, recipe_id=123)
            ...     repo.commit()
        """
        # Build query: pending jobs, ordered by priority (high to low) then FIFO
        stmt = (
            select(IngestionRequest)
            .where(IngestionRequest.status == IngestionStatus.pending)
            .order_by(IngestionRequest.priority.desc(), IngestionRequest.requested_at)
            .limit(1)
        )

        # Add row locking
        if skip_locked:
            stmt = stmt.with_for_update(skip_locked=True)
        else:
            stmt = stmt.with_for_update()

        # Execute and claim
        request = self.session.scalar(stmt)

        if request:
            # Atomically update to processing
            request.status = IngestionStatus.processing
            request.worker_id = worker_id
            request.processing_started_at = datetime.now(timezone.utc)

        return request

    def update_status(
        self,
        request_id: int,
        status: IngestionStatus,
        processing_metadata: dict | None = None,
        error_details: dict | None = None,
    ) -> IngestionRequest | None:
        """
        Update the status of an ingestion request.

        Args:
            request_id: ID of the request
            status: New status (IngestionStatus enum)
            processing_metadata: Processing metadata to merge/update
            error_details: Error details (if status is failed)

        Returns:
            Updated IngestionRequest or None if not found
        """
        request = self.get_by_id(request_id)
        if not request:
            return None

        request.status = status

        # Merge processing metadata
        if processing_metadata:
            if request.processing_metadata is None:
                request.processing_metadata = processing_metadata
            else:
                request.processing_metadata.update(processing_metadata)

        # Add error details if failed
        if status == IngestionStatus.failed and error_details:
            if request.processing_metadata is None:
                request.processing_metadata = {}

            # Type narrowing: at this point processing_metadata is definitely not None
            assert request.processing_metadata is not None

            if "errors" not in request.processing_metadata:
                request.processing_metadata["errors"] = []
            request.processing_metadata["errors"].append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "retry_count": request.retry_count,
                **error_details
            })

        return request

    def mark_completed(
        self,
        request_id: int,
        recipe_id: int,
        processing_metadata: dict | None = None,
    ) -> IngestionRequest | None:
        """
        Mark an ingestion request as completed and link to recipe.

        Args:
            request_id: ID of the request
            recipe_id: ID of the created recipe
            processing_metadata: Final processing metadata

        Returns:
            Updated IngestionRequest or None if not found
        """
        request = self.get_by_id(request_id)
        if not request:
            return None

        request.status = IngestionStatus.completed
        request.recipe_id = recipe_id
        request.completed_at = datetime.now(timezone.utc)

        if processing_metadata:
            if request.processing_metadata is None:
                request.processing_metadata = processing_metadata
            else:
                request.processing_metadata.update(processing_metadata)

        return request

    def mark_failed(
        self,
        request_id: int,
        error_message: str,
        error_type: str | None = None,
        retry: bool = False,
    ) -> IngestionRequest | None:
        """
        Mark an ingestion request as failed.

        Args:
            request_id: ID of the request
            error_message: Error description
            error_type: Type of error (optional)
            retry: If True and retries available, reset to pending

        Returns:
            Updated IngestionRequest or None if not found
        """
        request = self.get_by_id(request_id)
        if not request:
            return None

        request.retry_count += 1

        error_details = {
            "message": error_message,
            "type": error_type,
        }

        # Check if we should retry
        if retry and request.retry_count <= request.max_retries:
            request.status = IngestionStatus.pending
            request.worker_id = None
            request.processing_started_at = None
            error_details["will_retry"] = True
        else:
            request.status = IngestionStatus.failed
            request.completed_at = datetime.now(timezone.utc)
            error_details["will_retry"] = False

        # Add error to processing metadata
        if request.processing_metadata is None:
            request.processing_metadata = {}

        # Type narrowing: at this point processing_metadata is definitely not None
        assert request.processing_metadata is not None

        if "errors" not in request.processing_metadata:
            request.processing_metadata["errors"] = []

        request.processing_metadata["errors"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "retry_count": request.retry_count,
            **error_details
        })

        return request

    def get_pending_count(self) -> int:
        """
        Get the number of pending ingestion requests.

        Returns:
            Count of pending requests
        """
        stmt = select(func.count()).select_from(IngestionRequest).where(
            IngestionRequest.status == IngestionStatus.pending
        )
        return self.session.scalar(stmt) or 0

    def get_processing_count(self) -> int:
        """
        Get the number of currently processing requests.

        Returns:
            Count of processing requests
        """
        stmt = select(func.count()).select_from(IngestionRequest).where(
            IngestionRequest.status == IngestionStatus.processing
        )
        return self.session.scalar(stmt) or 0

    def get_by_recipe_id(self, recipe_id: int) -> list[IngestionRequest]:
        """
        Get all ingestion requests that created a specific recipe.

        Args:
            recipe_id: Recipe ID

        Returns:
            List of IngestionRequest objects
        """
        stmt = (
            select(IngestionRequest)
            .where(IngestionRequest.recipe_id == recipe_id)
            .order_by(IngestionRequest.requested_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get_failed_requests(
        self,
        since: datetime | None = None,
        limit: int = 100
    ) -> list[IngestionRequest]:
        """
        Get failed ingestion requests.

        Args:
            since: Only return failures since this time
            limit: Maximum number of results

        Returns:
            List of failed IngestionRequest objects
        """
        stmt = (
            select(IngestionRequest)
            .where(IngestionRequest.status == IngestionStatus.failed)
            .order_by(IngestionRequest.completed_at.desc())
            .limit(limit)
        )

        if since:
            stmt = stmt.where(IngestionRequest.completed_at >= since)

        return list(self.session.scalars(stmt).all())
