"""Recipe repository for data access operations."""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from mise.db.models import RecipeDbModel as RecipeModel
from mise.schema.recipe import Recipe
from mise.repository.base import BaseRepository
from mise.repository.models import RecipeRecord


class RecipeRepository(BaseRepository[RecipeModel]):
    """
    Repository for Recipe data access.

    Handles conversion between:
    - Recipe (business domain schema)
    - RecipeModel (SQLAlchemy ORM model)
    - RecipeRecord (repository layer model with metadata)
    """

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, RecipeModel)

    def _to_record(self, model: RecipeModel) -> RecipeRecord:
        """
        Convert SQLAlchemy model to RecipeRecord.

        Args:
            model: SQLAlchemy Recipe model instance

        Returns:
            RecipeRecord with metadata and business data
        """
        # Parse the JSONB data field into Recipe schema
        recipe = Recipe(**model.data)

        return RecipeRecord(
            id=model.id,
            uuid=model.uuid,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
            recipe=recipe
        )

    def _to_model(self, recipe: Recipe, model: RecipeModel | None = None) -> RecipeModel:
        """
        Convert Recipe schema to SQLAlchemy model.

        Args:
            recipe: Business domain Recipe
            model: Existing model to update (optional, creates new if None)

        Returns:
            SQLAlchemy Recipe model instance
        """
        # Exclude 'id' from JSONB to avoid duplication (UUID stored in dedicated column)
        data = recipe.model_dump(mode='json', exclude={'id'})

        if model is None:
            return RecipeModel(
                uuid=recipe.id,  # Store Recipe's UUID in dedicated column
                data=data
            )
        else:
            model.uuid = recipe.id
            model.data = data
            return model

    def create_recipe(self, recipe: Recipe) -> RecipeRecord:
        """
        Create a new recipe.

        Args:
            recipe: Recipe business domain object

        Returns:
            RecipeRecord with generated metadata
        """
        model = self._to_model(recipe)
        created_model = super().create(model)
        return self._to_record(created_model)

    def get_recipe_by_id(self, id: int, include_deleted: bool = False) -> RecipeRecord | None:
        """
        Get recipe by database ID.

        Args:
            id: Database primary key
            include_deleted: Include soft-deleted recipes

        Returns:
            RecipeRecord or None if not found
        """
        model = super().get_by_id(id)

        if model is None:
            return None

        # Filter out soft-deleted unless explicitly requested
        if not include_deleted and model.deleted_at is not None:
            return None

        return self._to_record(model)

    def get_by_uuid(self, uuid: UUID, include_deleted: bool = False) -> RecipeRecord | None:
        """
        Get recipe by business UUID.

        Args:
            uuid: Recipe UUID
            include_deleted: Include soft-deleted recipes

        Returns:
            RecipeRecord or None if not found
        """
        stmt = (
            select(RecipeModel)
            .where(RecipeModel.uuid == uuid)
        )

        if not include_deleted:
            stmt = stmt.where(RecipeModel.deleted_at.is_(None))

        model = self.session.scalar(stmt)
        return self._to_record(model) if model else None

    def get_all_recipes(
        self,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False
    ) -> list[RecipeRecord]:
        """
        Get all recipes with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            include_deleted: Include soft-deleted recipes

        Returns:
            List of RecipeRecords
        """
        stmt = select(RecipeModel).offset(skip).limit(limit)

        if not include_deleted:
            stmt = stmt.where(RecipeModel.deleted_at.is_(None))

        models = self.session.scalars(stmt).all()
        return [self._to_record(model) for model in models]

    def update_recipe(self, id: int, recipe: Recipe) -> RecipeRecord | None:
        """
        Update an existing recipe.

        Args:
            id: Database primary key
            recipe: Updated recipe data

        Returns:
            Updated RecipeRecord or None if not found
        """
        model = super().get_by_id(id)

        if model is None or model.deleted_at is not None:
            return None

        self._to_model(recipe, model)
        updated_model = super().update(model)
        return self._to_record(updated_model)

    def soft_delete(self, id: int) -> bool:
        """
        Soft delete a recipe (sets deleted_at timestamp).

        Args:
            id: Database primary key

        Returns:
            True if deleted, False if not found
        """
        model = super().get_by_id(id)

        if model is None or model.deleted_at is not None:
            return False

        model.deleted_at = datetime.now(timezone.utc)
        super().update(model)
        return True

    def restore(self, id: int) -> bool:
        """
        Restore a soft-deleted recipe.

        Args:
            id: Database primary key

        Returns:
            True if restored, False if not found or not deleted
        """
        model = super().get_by_id(id)

        if model is None or model.deleted_at is None:
            return False

        model.deleted_at = None
        super().update(model)
        return True

    def hard_delete(self, id: int) -> bool:
        """
        Permanently delete a recipe from database.

        Args:
            id: Database primary key

        Returns:
            True if deleted, False if not found
        """
        model = super().get_by_id(id)

        if model is None:
            return False

        super().delete(model)
        return True

    # === Query Methods ===

    def search_by_title(
        self,
        query: str,
        skip: int = 0,
        limit: int = 100
    ) -> list[RecipeRecord]:
        """
        Search recipes by title (case-insensitive partial match).

        Args:
            query: Search query string
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of matching RecipeRecords
        """
        stmt = (
            select(RecipeModel)
            .where(RecipeModel.deleted_at.is_(None))
            .where(
                func.lower(RecipeModel.data['title'].astext).contains(query.lower())
            )
            .offset(skip)
            .limit(limit)
        )

        models = self.session.scalars(stmt).all()
        return [self._to_record(model) for model in models]

    def find_by_tag(
        self,
        tag_key: str,
        tag_value: str | None = None,
        skip: int = 0,
        limit: int = 100
    ) -> list[RecipeRecord]:
        """
        Find recipes by tag.

        Args:
            tag_key: Tag key to search for (e.g., 'cuisine')
            tag_value: Optional tag value (e.g., 'italian')
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of matching RecipeRecords
        """
        # JSONB query to search in tags array using @> containment operator
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy import cast

        if tag_value:
            # Search for exact tag key-value pair
            # Use @> operator to check if tags array contains this object
            tag_pattern = [{"key": tag_key.lower(), "value": tag_value.lower()}]
            tag_filter = RecipeModel.data['tags'].op('@>')(
                cast(tag_pattern, JSONB)
            )
        else:
            # For key-only search, we need a different approach
            # Check if any tag in the array has the matching key using jsonb_path_exists
            # This requires casting the pattern as jsonpath type
            from sqlalchemy import text
            # Use raw SQL for this more complex query
            tag_filter = text(
                f"jsonb_path_exists(data->'tags', '$[*] ? (@.key == \"{tag_key.lower()}\")')"
            )

        stmt = (
            select(RecipeModel)
            .where(RecipeModel.deleted_at.is_(None))
            .where(tag_filter)
            .offset(skip)
            .limit(limit)
        )

        models = self.session.scalars(stmt).all()
        return [self._to_record(model) for model in models]

    def count(self, include_deleted: bool = False) -> int:
        """
        Count total recipes.

        Args:
            include_deleted: Include soft-deleted recipes

        Returns:
            Total count
        """
        stmt = select(func.count()).select_from(RecipeModel)

        if not include_deleted:
            stmt = stmt.where(RecipeModel.deleted_at.is_(None))

        return self.session.scalar(stmt) or 0

    # === Source Tracking Methods ===
    # NOTE: Source tracking has been moved to the IngestionRequest table.
    # Use IngestionRepository to query recipes by source.
    # These methods are deprecated and will be removed in a future version.
