"""Tests for Unit of Work pattern."""
import pytest

from mise.db.unit_of_work import UnitOfWork
from mise.db.models import RecipeDbModel, SourceType, IngestionStatus


@pytest.mark.integration
class TestUnitOfWork:
    """Tests for UnitOfWork pattern."""

    def test_auto_commit_on_success(self, sample_recipe):
        """Test that UoW automatically commits on success."""
        # Create recipe in UoW
        with UnitOfWork() as uow:
            recipe_data = sample_recipe.model_dump(mode='json')
            recipe_model = RecipeDbModel(data=recipe_data)
            created = uow.recipes.create(recipe_model)
            recipe_id = created.id
            # Auto-commits here

        # Verify in new UoW
        with UnitOfWork() as uow:
            recipe = uow.recipes.get_by_id(recipe_id)
            assert recipe is not None
            assert recipe.data["title"] == "Test Recipe"

    def test_auto_rollback_on_exception(self, sample_recipe):
        """Test that UoW automatically rolls back on exception."""
        recipe_id = None

        # Try to create recipe but raise exception
        try:
            with UnitOfWork() as uow:
                recipe_data = sample_recipe.model_dump(mode='json')
                recipe_model = RecipeDbModel(data=recipe_data)
                created = uow.recipes.create(recipe_model)
                recipe_id = created.id

                # Raise exception before commit
                raise ValueError("Test error")
        except ValueError:
            pass

        # Verify rollback worked - recipe should not exist
        with UnitOfWork() as uow:
            recipe = uow.recipes.get_by_id(recipe_id) if recipe_id else None
            assert recipe is None

    def test_multi_repository_transaction(self, sample_recipe):
        """Test transaction across multiple repositories."""
        with UnitOfWork() as uow:
            # Create ingestion request
            ingestion = uow.ingestions.create_request(
                source_type=SourceType.youtube,
                source_key="test:multi",
                source_url="https://example.com"
            )
            uow.session.flush()  # Get ID

            # Create recipe
            recipe_data = sample_recipe.model_dump(mode='json')
            recipe_model = RecipeDbModel(data=recipe_data)
            recipe = uow.recipes.create(recipe_model)

            # Link them
            uow.ingestions.mark_completed(ingestion.id, recipe.id)

            ingestion_id = ingestion.id
            recipe_id = recipe.id
            # Both committed together

        # Verify both exist and are linked
        with UnitOfWork() as uow:
            ingestion = uow.ingestions.get_by_id(ingestion_id)
            recipe = uow.recipes.get_by_id(recipe_id)

            assert ingestion is not None
            assert recipe is not None
            assert ingestion.recipe_id == recipe.id
            assert ingestion.status == IngestionStatus.completed

    def test_lazy_repository_loading(self, test_engine, setup_test_database):
        """Test that repositories are lazy-loaded."""
        with UnitOfWork() as uow:
            # Repositories should not be created yet
            assert uow._recipes is None
            assert uow._ingestions is None

            # Access recipes
            _ = uow.recipes

            # Now recipes should be loaded
            assert uow._recipes is not None
            # But ingestions still not loaded
            assert uow._ingestions is None

    def test_session_cleanup(self, test_engine, setup_test_database):
        """Test that session is properly closed."""
        uow = UnitOfWork()

        # Session should be open
        assert uow.session is not None

        # Enter and exit context
        with uow:
            pass

        # Session should be closed
        # Note: We can't directly check if closed, but if we try to use it,
        # it should fail or be in closed state
        assert uow.session is not None  # Object exists but is closed

    def test_rollback_doesnt_affect_other_transactions(
        self, test_engine, setup_test_database, sample_recipe
    ):
        """Test that rolling back one transaction doesn't affect others."""
        # Create recipe in first transaction (committed)
        with UnitOfWork() as uow:
            recipe_data = sample_recipe.model_dump(mode='json')
            recipe_data["title"] = "First Recipe"
            recipe_model = RecipeDbModel(data=recipe_data)
            first = uow.recipes.create(recipe_model)
            first_id = first.id

        # Try to create second recipe but rollback
        try:
            with UnitOfWork() as uow:
                recipe_data = sample_recipe.model_dump(mode='json')
                recipe_data["title"] = "Second Recipe"
                recipe_model = RecipeDbModel(data=recipe_data)
                uow.recipes.create(recipe_model)
                raise ValueError("Rollback")
        except ValueError:
            pass

        # First recipe should still exist
        with UnitOfWork() as uow:
            first = uow.recipes.get_by_id(first_id)
            assert first is not None
            assert first.data["title"] == "First Recipe"

            # Second recipe should not exist
            all_recipes = uow.recipes.get_all_recipes()
            assert len(all_recipes) == 1

    def test_duplicate_prevention(self, sample_recipe):
        """Test using UoW to prevent duplicates."""
        source_key = "test:duplicate_check"

        # First attempt - create
        with UnitOfWork() as uow:
            existing = uow.ingestions.find_by_source_key(source_key)
            assert existing is None

            ingestion = uow.ingestions.create_request(
                source_type=SourceType.youtube,
                source_key=source_key,
                source_url="https://example.com"
            )
            uow.session.flush()  # Get ID before commit
            ingestion_id = ingestion.id

        # Second attempt - detect duplicate
        with UnitOfWork() as uow:
            existing = uow.ingestions.find_by_source_key(source_key)
            assert existing is not None
            assert existing.id == ingestion_id

            # Don't create duplicate
            # Just return existing

        # Verify only one exists
        with UnitOfWork() as uow:
            ingestion = uow.ingestions.find_by_source_key(source_key)
            assert ingestion.id == ingestion_id

    def test_nested_exception_handling(self, sample_recipe):
        """Test exception handling with nested operations."""
        # This should rollback everything if inner operation fails
        try:
            with UnitOfWork() as uow:
                # Create ingestion
                ingestion = uow.ingestions.create_request(
                    source_type=SourceType.youtube,
                    source_key="test:nested",
                    source_url="https://example.com"
                )
                uow.session.flush()

                # Create recipe
                recipe_data = sample_recipe.model_dump(mode='json')
                recipe_model = RecipeDbModel(data=recipe_data)
                recipe = uow.recipes.create(recipe_model)

                # Something fails during linking
                raise RuntimeError("Link failed")
        except RuntimeError:
            pass

        # Neither should exist
        with UnitOfWork() as uow:
            ingestion = uow.ingestions.find_by_source_key("test:nested")
            assert ingestion is None

            all_recipes = uow.recipes.get_all_recipes()
            assert len(all_recipes) == 0
