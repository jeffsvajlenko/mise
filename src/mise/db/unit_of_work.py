"""Unit of Work pattern for managing database transactions."""
from sqlalchemy.orm import Session

from mise.db.database import engine
from mise.repository.recipe import RecipeRepository
from mise.repository.ingestion import IngestionRepository


class UnitOfWork:
    """
    Unit of Work pattern for managing database transactions.

    Provides access to all repositories within a single transaction context.
    Automatically commits on success and rolls back on exceptions.

    Example - Single repository:
        with UnitOfWork() as uow:
            recipe = uow.recipes.create(recipe_instance)
            # Automatically commits when exiting the 'with' block

    Example - Multiple repositories (single transaction):
        with UnitOfWork() as uow:
            recipe = uow.recipes.create(recipe_instance)
            uow.ingestions.mark_completed(ingestion_id, recipe.id)
            # Both operations committed together

    Example - Exception handling (auto-rollback):
        try:
            with UnitOfWork() as uow:
                recipe = uow.recipes.create(recipe_instance)
                raise ValueError("Something went wrong")
                # Auto-rollback happens
        except ValueError:
            print("Changes were rolled back")
    """

    def __init__(self):
        """Initialize a new unit of work with a fresh database session."""
        self.session = Session(engine)

        # Lazy-loaded repositories
        self._recipes: RecipeRepository | None = None
        self._ingestions: IngestionRepository | None = None

    @property
    def recipes(self) -> RecipeRepository:
        """Access to recipe repository."""
        if self._recipes is None:
            self._recipes = RecipeRepository(self.session)
        return self._recipes

    @property
    def ingestions(self) -> IngestionRepository:
        """Access to ingestion repository."""
        if self._ingestions is None:
            self._ingestions = IngestionRepository(self.session)
        return self._ingestions

    def __enter__(self):
        """Enter transaction context."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit transaction context.

        Commits if no exception occurred, otherwise rolls back.
        Always closes the session.
        """
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()

        # Don't suppress exceptions
        return False
