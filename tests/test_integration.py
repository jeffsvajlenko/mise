"""End-to-end integration tests."""
import pytest
from pathlib import Path

from mise.db.unit_of_work import UnitOfWork
from mise.db.models import RecipeDbModel, SourceType, IngestionStatus
from mise.schema.recipe import Recipe, Ingredient, RecipeStep, Tag
from mise.storage.files import FileStorage


@pytest.mark.integration
class TestRecipeIngestionWorkflow:
    """Test complete recipe ingestion workflow."""

    def test_create_recipe_from_url(self, sample_recipe):
        """Test full workflow: ingestion request -> recipe creation -> verification."""
        source_url = "https://example.com/chocolate-cake"
        source_key = "webpage:example.com/chocolate-cake"

        # Step 1: Create ingestion request
        with UnitOfWork() as uow:
            # Check for duplicates first
            existing = uow.ingestions.find_by_source_key(source_key)
            assert existing is None

            # Create ingestion request
            ingestion = uow.ingestions.create_request(
                source_type=SourceType.webpage,
                source_key=source_key,
                source_url=source_url,
                requested_by="user@example.com"
            )
            uow.session.flush()
            ingestion_id = ingestion.id

        # Step 2: Simulate processing - create recipe
        with UnitOfWork() as uow:
            # Get pending ingestion
            ingestion = uow.ingestions.get_by_id(ingestion_id)
            assert ingestion.status == IngestionStatus.pending

            # Mark as processing
            ingestion.status = IngestionStatus.processing
            uow.session.flush()

            # Create recipe
            recipe_data = sample_recipe.model_dump(mode='json')
            recipe_model = RecipeDbModel(data=recipe_data)
            recipe = uow.recipes.create(recipe_model)
            uow.session.flush()

            # Mark ingestion as completed
            uow.ingestions.mark_completed(ingestion.id, recipe.id)
            recipe_id = recipe.id

        # Step 3: Verify everything is linked correctly
        with UnitOfWork() as uow:
            recipe = uow.recipes.get_by_id(recipe_id)
            ingestion = uow.ingestions.get_by_id(ingestion_id)

            assert recipe is not None
            assert recipe.data["title"] == "Test Recipe"

            assert ingestion.status == IngestionStatus.completed
            assert ingestion.recipe_id == recipe.id
            assert ingestion.source_url == source_url

    def test_duplicate_url_prevention(self):
        """Test that duplicate URLs are detected and prevented."""
        source_key = "webpage:example.com/duplicate-test"

        # First request
        with UnitOfWork() as uow:
            ingestion1 = uow.ingestions.create_request(
                source_type=SourceType.webpage,
                source_key=source_key,
                source_url="https://example.com/duplicate-test"
            )
            uow.session.flush()
            first_id = ingestion1.id

        # Second request - should detect duplicate
        with UnitOfWork() as uow:
            existing = uow.ingestions.find_by_source_key(source_key)
            assert existing is not None
            assert existing.id == first_id

    def test_recipe_with_full_metadata(self):
        """Test creating and retrieving recipe with all metadata."""
        # Create a comprehensive recipe
        recipe = Recipe(
            title="Grandma's Apple Pie",
            description="A classic apple pie recipe passed down for generations",
            prep_time=30,
            cook_time=60,
            servings=8,
            ingredients=[
                Ingredient(
                    text="6 cups apples, peeled and sliced",
                    name="apples",
                    quantity=6.0,
                    unit="cups",
                    preparation="peeled and sliced"
                ),
                Ingredient(
                    text="3/4 cup sugar",
                    name="sugar",
                    quantity=0.75,
                    unit="cup"
                ),
                Ingredient(
                    text="2 tablespoons flour",
                    name="flour",
                    quantity=2.0,
                    unit="tablespoons"
                ),
                Ingredient(
                    text="1 teaspoon cinnamon",
                    name="cinnamon",
                    quantity=1.0,
                    unit="teaspoon"
                )
            ],
            steps=[
                RecipeStep(
                    instruction="Prepare the crust",
                    substeps=[
                        RecipeStep(instruction="Mix flour and salt"),
                        RecipeStep(instruction="Cut in butter"),
                        RecipeStep(instruction="Add ice water gradually")
                    ]
                ),
                RecipeStep(instruction="Mix apples with sugar, flour, and cinnamon"),
                RecipeStep(instruction="Fill pie crust with apple mixture"),
                RecipeStep(instruction="Bake at 375°F for 50-60 minutes")
            ],
            tags=[
                Tag(key="cuisine", value="american"),
                Tag(key="meal_type", value="dessert"),
                Tag(key="difficulty", value="medium")
            ],
            author="Grandma Smith"
        )

        # Save to database
        with UnitOfWork() as uow:
            recipe_model = RecipeDbModel(data=recipe.model_dump(mode='json'))
            created = uow.recipes.create(recipe_model)
            uow.session.flush()
            recipe_id = created.id

        # Retrieve and verify
        with UnitOfWork() as uow:
            retrieved = uow.recipes.get_by_id(recipe_id)

            assert retrieved.data["title"] == "Grandma's Apple Pie"
            assert retrieved.data["prep_time"] == 30
            assert retrieved.data["cook_time"] == 60
            assert len(retrieved.data["ingredients"]) == 4
            assert len(retrieved.data["steps"]) == 4
            assert len(retrieved.data["steps"][0]["substeps"]) == 3
            assert len(retrieved.data["tags"]) == 3
            assert retrieved.data["author"] == "Grandma Smith"

    def test_failed_ingestion_with_retry(self):
        """Test ingestion failure and retry workflow."""
        source_key = "webpage:example.com/flaky-source"

        # Create ingestion request
        with UnitOfWork() as uow:
            ingestion = uow.ingestions.create_request(
                source_type=SourceType.webpage,
                source_key=source_key,
                source_url="https://example.com/flaky-source"
            )
            uow.session.flush()
            ingestion_id = ingestion.id

        # First attempt fails
        with UnitOfWork() as uow:
            ingestion = uow.ingestions.get_by_id(ingestion_id)
            uow.ingestions.mark_failed(
                ingestion_id,
                error_message="Connection timeout",
                retry=True
            )

        # Verify retry count incremented and status is pending
        with UnitOfWork() as uow:
            ingestion = uow.ingestions.get_by_id(ingestion_id)
            assert ingestion.retry_count == 1
            assert ingestion.status == IngestionStatus.pending

        # Second attempt fails
        with UnitOfWork() as uow:
            uow.ingestions.mark_failed(
                ingestion_id,
                error_message="Connection timeout again",
                retry=True
            )

        # Verify retry count incremented again
        with UnitOfWork() as uow:
            ingestion = uow.ingestions.get_by_id(ingestion_id)
            assert ingestion.retry_count == 2
            assert ingestion.status == IngestionStatus.pending

    def test_ingestion_queue_ordering(self):
        """Test that ingestion queue respects priority and FIFO."""
        # Create low priority request
        with UnitOfWork() as uow:
            uow.ingestions.create_request(
                source_type=SourceType.webpage,
                source_key="webpage:example.com/low",
                source_url="https://example.com/low",
                priority=0
            )

        # Create high priority request
        with UnitOfWork() as uow:
            uow.ingestions.create_request(
                source_type=SourceType.webpage,
                source_key="webpage:example.com/high",
                source_url="https://example.com/high",
                priority=10
            )

        # Create medium priority request
        with UnitOfWork() as uow:
            uow.ingestions.create_request(
                source_type=SourceType.webpage,
                source_key="webpage:example.com/medium",
                source_url="https://example.com/medium",
                priority=5
            )

        # Get next pending - should be high priority
        with UnitOfWork() as uow:
            next_request = uow.ingestions.get_next_pending(worker_id="test-worker")
            assert next_request is not None
            assert next_request.priority == 10
            assert "high" in next_request.source_url


@pytest.mark.integration
class TestRecipeOperations:
    """Test recipe CRUD operations."""

    def test_create_and_retrieve_recipe(self, sample_recipe):
        """Test creating and retrieving a recipe."""
        with UnitOfWork() as uow:
            recipe_model = RecipeDbModel(data=sample_recipe.model_dump(mode='json'))
            created = uow.recipes.create(recipe_model)
            recipe_id = created.id

        with UnitOfWork() as uow:
            retrieved = uow.recipes.get_by_id(recipe_id)
            assert retrieved is not None
            assert retrieved.data["title"] == sample_recipe.title

    def test_soft_delete_recipe(self, sample_recipe):
        """Test soft deleting a recipe."""
        # Create recipe
        with UnitOfWork() as uow:
            recipe_model = RecipeDbModel(data=sample_recipe.model_dump(mode='json'))
            created = uow.recipes.create(recipe_model)
            recipe_id = created.id

        # Soft delete
        with UnitOfWork() as uow:
            uow.recipes.soft_delete(recipe_id)

        # Verify it's marked as deleted
        with UnitOfWork() as uow:
            recipe = uow.recipes.get_by_id(recipe_id)
            assert recipe is not None
            assert recipe.is_deleted

            # Should not appear in regular queries
            all_recipes = uow.recipes.get_all_recipes()
            assert recipe_id not in [r.id for r in all_recipes]

    def test_pagination(self, sample_recipe):
        """Test recipe pagination."""
        # Create 10 recipes
        with UnitOfWork() as uow:
            for i in range(10):
                recipe_data = sample_recipe.model_dump(mode='json')
                recipe_data["title"] = f"Recipe {i}"
                recipe_model = RecipeDbModel(data=recipe_data)
                uow.recipes.create(recipe_model)

        # Get first page
        with UnitOfWork() as uow:
            page1 = uow.recipes.get_all_recipes(limit=5, skip=0)
            assert len(page1) == 5

        # Get second page
        with UnitOfWork() as uow:
            page2 = uow.recipes.get_all_recipes(limit=5, skip=5)
            assert len(page2) == 5

        # Verify no overlap
        page1_ids = [r.id for r in page1]
        page2_ids = [r.id for r in page2]
        assert len(set(page1_ids) & set(page2_ids)) == 0


@pytest.mark.integration
class TestFileStorage:
    """Test file storage operations."""

    def test_file_storage_creation(self, temp_file_storage):
        """Test that file storage creates directory structure."""
        storage = temp_file_storage
        assert storage.base_path.exists()
        assert storage.base_path.is_dir()

    def test_save_recipe_file(self, temp_file_storage, sample_recipe):
        """Test saving a file for a recipe."""
        from io import BytesIO

        storage = temp_file_storage

        # Create a recipe first
        with UnitOfWork() as uow:
            recipe_model = RecipeDbModel(data=sample_recipe.model_dump(mode='json'))
            created = uow.recipes.create(recipe_model)
            recipe_uuid = created.uuid

        # Create fake image data
        image_data = BytesIO(b"fake image data")

        # Save file
        metadata = storage.save_recipe_file(
            recipe_uuid=recipe_uuid,
            file=image_data,
            original_filename="chocolate-cake.jpg",
            file_id="original"
        )

        assert metadata["id"] == "original"
        assert metadata["filename"] == "chocolate-cake.jpg"
        assert metadata["content_type"] == "image/jpeg"
        assert metadata["size_bytes"] > 0
        assert "uploaded_at" in metadata

        # Verify file exists on disk
        file_path = storage.base_path / metadata["path"]
        assert file_path.exists()
        assert file_path.read_bytes() == b"fake image data"
