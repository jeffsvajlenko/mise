"""Ingestion request endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, HttpUrl
from typing import Literal
from uuid import UUID

from mise.db.unit_of_work import UnitOfWork
from mise.db.models import SourceType, IngestionStatus
from mise.api.dependencies import get_uow

router = APIRouter()


class CreateIngestionRequest(BaseModel):
    """Request body for creating an ingestion."""

    source_type: Literal["text", "webpage", "youtube", "image"]
    text: str | None = None
    url: HttpUrl | None = None
    metadata: dict | None = None


class IngestionResponse(BaseModel):
    """Response for ingestion request."""

    id: int
    uuid: UUID
    status: str
    source_type: str
    source_key: str
    source_url: str | None
    recipe_id: int | None
    recipe_uuid: UUID | None
    created_at: str
    updated_at: str
    processing_started_at: str | None
    processing_completed_at: str | None
    worker_id: str | None
    retry_count: int
    max_retries: int


class IngestionListResponse(BaseModel):
    """Response for list of ingestions."""

    ingestions: list[IngestionResponse]
    total: int
    skip: int
    limit: int


@router.post("", response_model=IngestionResponse, status_code=201)
def create_ingestion(
    request: CreateIngestionRequest, uow: UnitOfWork = Depends(get_uow)
) -> IngestionResponse:
    """
    Create a new ingestion request.

    The ingestion will be queued for processing by a worker.
    """
    # Validate request based on source type
    if request.source_type in ("webpage", "youtube"):
        if not request.url:
            raise HTTPException(
                status_code=400,
                detail=f"{request.source_type} source requires 'url' field",
            )
    elif request.source_type == "text":
        if not request.text:
            raise HTTPException(status_code=400, detail="text source requires 'text' field")
    elif request.source_type == "image":
        raise HTTPException(
            status_code=400,
            detail="Image ingestion via API not yet implemented. Use file upload endpoint.",
        )

    # Map source_type to SourceType enum
    source_type_map = {
        "text": SourceType.custom,
        "webpage": SourceType.webpage,
        "youtube": SourceType.youtube,
        "image": SourceType.photo,
    }
    source_type = source_type_map[request.source_type]

    # Determine source_key and source_url
    if request.source_type == "text":
        # For text, we'll use a hash or unique identifier
        # For now, just use a simple approach - let the repository handle it
        import hashlib
        text_hash = hashlib.sha256((request.text or "").encode()).hexdigest()[:16]
        source_key = f"text:{text_hash}"
        source_url = None
    else:
        # For URL-based sources, use normalized URL
        from mise.ingestion.source_utils import normalize_url
        source_url = str(request.url) if request.url else None
        normalized = normalize_url(source_url) if source_url else None
        source_key = f"{request.source_type}:{normalized}"

    # Create ingestion request
    ingestion = uow.ingestions.create_request(
        source_type=source_type,
        source_key=source_key,
        source_url=source_url,
        request_params=request.metadata or {},
    )

    # Add text to request_params if provided
    if request.text:
        ingestion.request_params["text"] = request.text

    uow.session.commit()

    # Get recipe UUID if completed
    recipe_uuid = None
    if ingestion.recipe_id and ingestion.recipe:
        recipe_uuid = ingestion.recipe.uuid

    return IngestionResponse(
        id=ingestion.id,
        uuid=ingestion.uuid,
        status=ingestion.status.value,
        source_type=ingestion.source_type.value,
        source_key=ingestion.source_key,
        source_url=ingestion.source_url,
        recipe_id=ingestion.recipe_id,
        recipe_uuid=recipe_uuid,
        created_at=ingestion.created_at.isoformat(),
        updated_at=ingestion.updated_at.isoformat(),
        processing_started_at=ingestion.processing_started_at.isoformat()
        if ingestion.processing_started_at
        else None,
        processing_completed_at=ingestion.processing_completed_at.isoformat()
        if ingestion.processing_completed_at
        else None,
        worker_id=ingestion.worker_id,
        retry_count=ingestion.retry_count,
        max_retries=ingestion.max_retries,
    )


@router.get("/{ingestion_id}", response_model=IngestionResponse)
def get_ingestion(ingestion_id: int, uow: UnitOfWork = Depends(get_uow)) -> IngestionResponse:
    """Get an ingestion request by ID."""
    ingestion = uow.ingestions.get_by_id(ingestion_id)

    if not ingestion:
        raise HTTPException(status_code=404, detail="Ingestion not found")

    # Get recipe UUID if completed
    recipe_uuid = None
    if ingestion.recipe_id and ingestion.recipe:
        recipe_uuid = ingestion.recipe.uuid

    return IngestionResponse(
        id=ingestion.id,
        uuid=ingestion.uuid,
        status=ingestion.status.value,
        source_type=ingestion.source_type.value,
        source_key=ingestion.source_key,
        source_url=ingestion.source_url,
        recipe_id=ingestion.recipe_id,
        recipe_uuid=recipe_uuid,
        created_at=ingestion.created_at.isoformat(),
        updated_at=ingestion.updated_at.isoformat(),
        processing_started_at=ingestion.processing_started_at.isoformat()
        if ingestion.processing_started_at
        else None,
        processing_completed_at=ingestion.processing_completed_at.isoformat()
        if ingestion.processing_completed_at
        else None,
        worker_id=ingestion.worker_id,
        retry_count=ingestion.retry_count,
        max_retries=ingestion.max_retries,
    )


@router.get("", response_model=IngestionListResponse)
def list_ingestions(
    status: IngestionStatus | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    uow: UnitOfWork = Depends(get_uow),
) -> IngestionListResponse:
    """
    List ingestion requests with optional filtering.

    Args:
        status: Filter by status (pending, processing, completed, failed, cancelled)
        skip: Number of records to skip (pagination)
        limit: Maximum number of records to return (max 100)
    """
    # Get filtered ingestions
    if status:
        from sqlalchemy import select
        from mise.db.models import IngestionRequest

        query = select(IngestionRequest).where(IngestionRequest.status == status)
        query = query.order_by(IngestionRequest.created_at.desc())
        query = query.offset(skip).limit(limit)

        ingestions = list(uow.session.execute(query).scalars())

        # Count total
        count_query = select(IngestionRequest).where(IngestionRequest.status == status)
        total = len(list(uow.session.execute(count_query).scalars()))
    else:
        from sqlalchemy import select, func
        from mise.db.models import IngestionRequest

        query = select(IngestionRequest).order_by(IngestionRequest.created_at.desc())
        query = query.offset(skip).limit(limit)

        ingestions = list(uow.session.execute(query).scalars())

        # Count total
        total = uow.session.execute(select(func.count()).select_from(IngestionRequest)).scalar()

    # Convert to response models
    responses = []
    for ingestion in ingestions:
        recipe_uuid = None
        if ingestion.recipe_id and ingestion.recipe:
            recipe_uuid = ingestion.recipe.uuid

        responses.append(
            IngestionResponse(
                id=ingestion.id,
                uuid=ingestion.uuid,
                status=ingestion.status.value,
                source_type=ingestion.source_type.value,
                source_key=ingestion.source_key,
                source_url=ingestion.source_url,
                recipe_id=ingestion.recipe_id,
                recipe_uuid=recipe_uuid,
                created_at=ingestion.created_at.isoformat(),
                updated_at=ingestion.updated_at.isoformat(),
                processing_started_at=ingestion.processing_started_at.isoformat()
                if ingestion.processing_started_at
                else None,
                processing_completed_at=ingestion.processing_completed_at.isoformat()
                if ingestion.processing_completed_at
                else None,
                worker_id=ingestion.worker_id,
                retry_count=ingestion.retry_count,
                max_retries=ingestion.max_retries,
            )
        )

    return IngestionListResponse(ingestions=responses, total=total or 0, skip=skip, limit=limit)
