"""Tests for repository layer."""
import pytest
from datetime import datetime, timezone

from mise.db.models import RecipeDbModel, IngestionRequest, SourceType, IngestionStatus
from mise.repository.recipe import RecipeRepository
from mise.repository.ingestion import IngestionRepository


@pytest.mark.integration
class TestRecipeRepository:
    """Tests for RecipeRepository."""

    def test_create_recipe(self, db_session, sample_recipe_db_model):
        """Test creating a recipe."""
        repo = RecipeRepository(db_session)

        recipe = repo.create(sample_recipe_db_model)

        assert recipe.id is not None
        assert recipe.uuid is not None
        assert recipe.created_at is not None
        assert recipe.data["title"] == "Test Recipe"

    def test_get_by_id(self, db_session, sample_recipe_db_model):
        """Test retrieving a recipe by ID."""
        repo = RecipeRepository(db_session)

        # Create recipe
        created = repo.create(sample_recipe_db_model)
        db_session.commit()

        # Retrieve it
        retrieved = repo.get_by_id(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.uuid == created.uuid

    def test_get_by_id_nonexistent(self, db_session):
        """Test retrieving a nonexistent recipe."""
        repo = RecipeRepository(db_session)

        recipe = repo.get_by_id(99999)

        assert recipe is None

    def test_get_all_with_pagination(self, db_session, sample_recipe):
        """Test pagination."""
        repo = RecipeRepository(db_session)

        # Create multiple recipes
        for i in range(15):
            recipe_data = sample_recipe.model_dump(mode='json')
            recipe_data["title"] = f"Recipe {i}"
            recipe_model = RecipeDbModel(data=recipe_data)
            repo.create(recipe_model)

        db_session.commit()

        # Get first page
        page1 = repo.get_all(skip=0, limit=10)
        assert len(page1) == 10

        # Get second page
        page2 = repo.get_all(skip=10, limit=10)
        assert len(page2) == 5

        # Verify no overlap
        page1_ids = {r.id for r in page1}
        page2_ids = {r.id for r in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_delete_recipe(self, db_session, sample_recipe_db_model):
        """Test hard deleting a recipe."""
        repo = RecipeRepository(db_session)

        recipe = repo.create(sample_recipe_db_model)
        recipe_id = recipe.id
        db_session.commit()

        # Delete it
        repo.delete(recipe)
        db_session.commit()

        # Verify it's gone
        retrieved = repo.get_by_id(recipe_id)
        assert retrieved is None


@pytest.mark.integration
class TestIngestionRepository:
    """Tests for IngestionRepository."""

    def test_create_request(self, db_session):
        """Test creating an ingestion request."""
        repo = IngestionRepository(db_session)

        request = repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:123",
            source_url="https://example.com",
            priority=5,
            requested_by="user123"
        )

        # Flush to get the ID
        db_session.flush()

        assert request.id is not None
        assert request.source_type == SourceType.youtube
        assert request.source_key == "test:123"
        assert request.status == IngestionStatus.pending
        assert request.priority == 5

    def test_duplicate_source_key(self, db_session):
        """Test that duplicate source_key raises error."""
        repo = IngestionRepository(db_session)

        # Create first request
        repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:123",
            source_url="https://example.com"
        )
        db_session.commit()

        # Try to create duplicate
        repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:123",  # Same key
            source_url="https://example.com"
        )

        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()

    def test_find_by_source_key(self, db_session):
        """Test finding request by source key."""
        repo = IngestionRepository(db_session)

        # Create request
        created = repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:findme",
            source_url="https://example.com"
        )
        db_session.commit()

        # Find it
        found = repo.find_by_source_key("test:findme")

        assert found is not None
        assert found.id == created.id
        assert found.source_key == "test:findme"

    def test_get_next_pending_fifo_order(self, db_session):
        """Test that pending jobs are claimed in FIFO order."""
        repo = IngestionRepository(db_session)

        # Create three requests with same priority
        req1 = repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:1",
            source_url="https://example.com",
            priority=0
        )
        req2 = repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:2",
            source_url="https://example.com",
            priority=0
        )
        req3 = repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:3",
            source_url="https://example.com",
            priority=0
        )
        db_session.commit()

        # Claim them in order
        claimed1 = repo.get_next_pending("worker1")
        db_session.commit()
        assert claimed1.id == req1.id

        claimed2 = repo.get_next_pending("worker2")
        db_session.commit()
        assert claimed2.id == req2.id

        claimed3 = repo.get_next_pending("worker3")
        db_session.commit()
        assert claimed3.id == req3.id

    def test_get_next_pending_priority_order(self, db_session):
        """Test that priority is respected over FIFO."""
        repo = IngestionRepository(db_session)

        # Create requests with different priorities
        req_low = repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:low",
            source_url="https://example.com",
            priority=1
        )
        req_high = repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:high",
            source_url="https://example.com",
            priority=10
        )
        db_session.commit()

        # High priority should be claimed first
        claimed = repo.get_next_pending("worker1")
        db_session.commit()

        assert claimed.id == req_high.id
        assert claimed.priority == 10

    def test_mark_completed(self, db_session, sample_recipe_db_model):
        """Test marking request as completed."""
        repo = IngestionRepository(db_session)
        recipe_repo = RecipeRepository(db_session)

        # Create request
        request = repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:complete",
            source_url="https://example.com"
        )
        db_session.commit()

        # Create recipe
        recipe = recipe_repo.create(sample_recipe_db_model)
        db_session.commit()

        # Mark as completed
        updated = repo.mark_completed(
            request.id,
            recipe.id,
            processing_metadata={"final": "data"}
        )

        assert updated.status == IngestionStatus.completed
        assert updated.recipe_id == recipe.id
        assert updated.completed_at is not None
        assert updated.processing_metadata["final"] == "data"

    def test_mark_failed_with_retry(self, db_session):
        """Test marking request as failed with retry."""
        repo = IngestionRepository(db_session)

        # Create and claim request
        request = repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:fail",
            source_url="https://example.com"
        )
        db_session.commit()

        claimed = repo.get_next_pending("worker1")
        db_session.commit()

        # Mark as failed with retry
        updated = repo.mark_failed(
            claimed.id,
            error_message="Test error",
            error_type="TestError",
            retry=True
        )

        assert updated.status == IngestionStatus.pending  # Reset for retry
        assert updated.retry_count == 1
        assert updated.worker_id is None
        assert "errors" in updated.processing_metadata

    def test_mark_failed_max_retries(self, db_session):
        """Test that max retries prevents further retries."""
        repo = IngestionRepository(db_session)

        # Create request
        request = repo.create_request(
            source_type=SourceType.youtube,
            source_key="test:maxretry",
            source_url="https://example.com"
        )
        db_session.commit()

        # Fail it multiple times
        for i in range(request.max_retries + 1):
            claimed = repo.get_next_pending("worker1")
            if claimed:
                db_session.commit()
                repo.mark_failed(
                    claimed.id,
                    error_message=f"Attempt {i+1}",
                    error_type="TestError",
                    retry=True
                )
                db_session.commit()

        # Should now be permanently failed
        final = repo.get_by_id(request.id)
        assert final.status == IngestionStatus.failed
        assert final.retry_count > final.max_retries

    def test_get_pending_count(self, db_session):
        """Test counting pending requests."""
        repo = IngestionRepository(db_session)

        # Create mix of statuses
        repo.create_request(SourceType.youtube, "test:1", "http://ex.com")
        repo.create_request(SourceType.youtube, "test:2", "http://ex.com")

        req3 = repo.create_request(SourceType.youtube, "test:3", "http://ex.com")
        db_session.commit()

        # Claim one
        repo.get_next_pending("worker1")
        db_session.commit()

        # Should have 2 pending (one is now processing)
        count = repo.get_pending_count()
        assert count == 2

    def test_get_processing_count(self, db_session):
        """Test counting processing requests."""
        repo = IngestionRepository(db_session)

        # Create requests
        repo.create_request(SourceType.youtube, "test:1", "http://ex.com")
        repo.create_request(SourceType.youtube, "test:2", "http://ex.com")
        db_session.commit()

        # Claim both
        repo.get_next_pending("worker1")
        db_session.commit()
        repo.get_next_pending("worker2")
        db_session.commit()

        # Should have 2 processing
        count = repo.get_processing_count()
        assert count == 2
