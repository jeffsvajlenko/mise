"""Base repository with common CRUD operations."""
from typing import Generic, TypeVar, Type
from sqlalchemy.orm import Session
from sqlalchemy import select
from mise.db.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic base repository providing common CRUD operations.

    This handles basic database operations and can be extended
    by specific repositories for domain-specific queries.
    """

    def __init__(self, session: Session, model: Type[ModelType]):
        """
        Initialize repository with database session and model.

        Args:
            session: SQLAlchemy session for database operations
            model: SQLAlchemy ORM model class
        """
        self.session = session
        self.model = model

    def get_by_id(self, id: int) -> ModelType | None:
        """
        Get a single record by primary key.

        Args:
            id: Primary key value

        Returns:
            Model instance or None if not found
        """
        return self.session.get(self.model, id)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """
        Get all records with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of model instances
        """
        stmt = select(self.model).offset(skip).limit(limit)
        return list(self.session.scalars(stmt).all())

    def create(self, instance: ModelType) -> ModelType:
        """
        Create a new record.

        Args:
            instance: Model instance to create

        Returns:
            Created model instance with generated fields populated
        """
        self.session.add(instance)
        self.session.flush()  # Flush to get generated ID without committing
        self.session.refresh(instance)  # Refresh to get server defaults
        return instance

    def update(self, instance: ModelType) -> ModelType:
        """
        Update an existing record.

        Args:
            instance: Model instance to update (must be attached to session)

        Returns:
            Updated model instance
        """
        self.session.flush()
        self.session.refresh(instance)
        return instance

    def delete(self, instance: ModelType) -> None:
        """
        Hard delete a record from the database.

        Args:
            instance: Model instance to delete
        """
        self.session.delete(instance)
        self.session.flush()

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.session.rollback()
