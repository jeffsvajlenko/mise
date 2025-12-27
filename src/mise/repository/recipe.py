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
            source_type=model.source_type,
            source_key=model.source_key,
            source_metadata=model.source_metadata,
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

    def find_by_source(
        self,
        source_type: str,
        source_key: str
    ) -> RecipeRecord | None:
        """
        Find recipe by source for deduplication.

        Args:
            source_type: Type of source (e.g., 'youtube', 'webpage')
            source_key: Unique key within that source type

        Returns:
            RecipeRecord if found, None otherwise
        """
        stmt = (
            select(RecipeModel)
            .where(RecipeModel.source_type == source_type)
            .where(RecipeModel.source_key == source_key)
            .where(RecipeModel.deleted_at.is_(None))
        )

        model = self.session.scalar(stmt)
        return self._to_record(model) if model else None

    def create_from_source(
        self,
        recipe: Recipe,
        source_type: str,
        source_key: str,
        source_metadata: dict | None = None
    ) -> RecipeRecord:
        """
        Create a new recipe with source tracking.

        Args:
            recipe: Recipe business domain object
            source_type: Type of source
            source_key: Unique identifier for this source
            source_metadata: Optional additional metadata

        Returns:
            RecipeRecord with generated metadata

        Raises:
            IntegrityError: If source already exists (duplicate)
        """
        data = recipe.model_dump(mode='json')

        model = RecipeModel(
            data=data,
            source_type=source_type,
            source_key=source_key,
            source_metadata=source_metadata
        )

        created_model = super().create(model)
        return self._to_record(created_model)

    def upsert_from_source(
        self,
        recipe: Recipe,
        source_type: str,
        source_key: str,
        source_metadata: dict | None = None,
        update_if_exists: bool = True
    ) -> tuple[RecipeRecord, bool]:
        """
        Create or update recipe from external source.

        Args:
            recipe: Recipe business domain object
            source_type: Type of source
            source_key: Unique identifier for this source
            source_metadata: Optional additional metadata
            update_if_exists: If True, update existing recipe; if False, return existing

        Returns:
            Tuple of (RecipeRecord, was_created)
            - was_created is True if new recipe was created, False if existing was used/updated
        """
        # Check if exists
        existing = self.find_by_source(source_type, source_key)

        if existing:
            if update_if_exists:
                # Update existing recipe
                updated = self.update_recipe(existing.id, recipe)
                # Also update source_metadata if provided
                if source_metadata is not None:
                    model = super().get_by_id(existing.id)
                    if model:
                        model.source_metadata = source_metadata
                        super().update(model)
                return (updated if updated else existing, False)
            else:
                # Return existing without updating
                return (existing, False)
        else:
            # Create new with source tracking
            created = self.create_from_source(
                recipe,
                source_type,
                source_key,
                source_metadata
            )
            return (created, True)

    def get_by_source_type(
        self,
        source_type: str,
        skip: int = 0,
        limit: int = 100
    ) -> list[RecipeRecord]:
        """
        Get all recipes from a specific source type.

        Args:
            source_type: Type of source to filter by
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of RecipeRecords from that source
        """
        stmt = (
            select(RecipeModel)
            .where(RecipeModel.source_type == source_type)
            .where(RecipeModel.deleted_at.is_(None))
            .offset(skip)
            .limit(limit)
        )

        models = self.session.scalars(stmt).all()
        return [self._to_record(model) for model in models]
