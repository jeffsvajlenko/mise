"""Recipe endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from uuid import UUID

from mise.db.unit_of_work import UnitOfWork
from mise.schema.recipe import Recipe
from mise.api.dependencies import get_uow

router = APIRouter()


class RecipeListResponse(BaseModel):
    """Response for list of recipes."""

    recipes: list[Recipe]
    total: int
    skip: int
    limit: int


@router.get("/{recipe_uuid}", response_model=Recipe)
def get_recipe(recipe_uuid: UUID, uow: UnitOfWork = Depends(get_uow)) -> Recipe:
    """
    Get a recipe by UUID.

    Args:
        recipe_uuid: UUID of the recipe

    Returns:
        Recipe: Full recipe data

    Raises:
        HTTPException: 404 if recipe not found
    """
    record = uow.recipes.get_by_uuid(recipe_uuid)

    if not record:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return record.recipe


@router.get("", response_model=RecipeListResponse)
def list_recipes(
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    uow: UnitOfWork = Depends(get_uow),
) -> RecipeListResponse:
    """
    List recipes with optional search.

    Args:
        search: Optional search term (searches title)
        skip: Number of records to skip (pagination)
        limit: Maximum number of records to return (max 100)

    Returns:
        RecipeListResponse: List of recipes with pagination info
    """
    if search:
        # Search by title
        records = uow.recipes.search_by_title(search, skip=skip, limit=limit)
        # TODO: Implement proper count for search results
        total = len(records)
    else:
        # Get all recipes
        from sqlalchemy import select, func
        from mise.db.models import RecipeDbModel

        query = select(RecipeDbModel).where(RecipeDbModel.deleted_at.is_(None))
        query = query.order_by(RecipeDbModel.created_at.desc())
        query = query.offset(skip).limit(limit)

        db_recipes = list(uow.session.execute(query).scalars())
        records = [uow.recipes._to_record(r) for r in db_recipes]

        # Count total
        total = uow.session.execute(
            select(func.count())
            .select_from(RecipeDbModel)
            .where(RecipeDbModel.deleted_at.is_(None))
        ).scalar()

    recipes = [record.recipe for record in records]

    return RecipeListResponse(recipes=recipes, total=total or 0, skip=skip, limit=limit)
