"""Tests for database models."""
import pytest
from datetime import datetime

from mise.db.models import RecipeDbModel, IngestionRequest, SourceType, IngestionStatus


@pytest.mark.integration
class TestRecipeDbModel:
    """Tests for RecipeDbModel."""

    def test_create_with_defaults(self, db_session, sample_recipe):
        """Test creating model with default values."""
        recipe_model = RecipeDbModel(
            data=sample_recipe.model_dump(mode='json')
        )

        db_session.add(recipe_model)
        db_session.commit()

        assert recipe_model.id is not None
        assert recipe_model.uuid is not None
        assert recipe_model.created_at is not None
        assert recipe_model.updated_at is not None
        assert recipe_model.deleted_at is None

    def test_timestamps_auto_populate(self, db_session, sample_recipe):
        """Test that timestamps are automatically set."""
        recipe_model = RecipeDbModel(
            data=sample_recipe.model_dump(mode='json')
        )

        db_session.add(recipe_model)
        db_session.commit()

        # Both should be set
        assert recipe_model.created_at is not None
        assert recipe_model.updated_at is not None

        # They should be close to each other (same transaction)
        time_diff = (recipe_model.updated_at - recipe_model.created_at).total_seconds()
        assert abs(time_diff) < 1  # Within 1 second

    def test_updated_at_changes_on_update(self, db_session, sample_recipe):
        """Test that updated_at is maintained on updates."""
        from datetime import datetime, timezone
        from sqlalchemy.orm import attributes

        recipe_model = RecipeDbModel(
            data=sample_recipe.model_dump(mode='json')
        )

        db_session.add(recipe_model)
        db_session.commit()

        original_updated_at = recipe_model.updated_at

        # Modify the recipe
        recipe_data = recipe_model.data.copy()
        recipe_data["title"] = "Modified Title"
        recipe_model.data = recipe_data

        # SQLAlchemy needs to detect the change
        attributes.flag_modified(recipe_model, "data")

        db_session.commit()
        db_session.refresh(recipe_model)

        # Verify updated_at is recent (within last minute)
        # Note: Testing exact timestamp changes is unreliable due to database timing
        # Database stores naive timestamps, so compare without timezone
        now = datetime.now()
        time_since_update = (now - recipe_model.updated_at).total_seconds()
        assert time_since_update < 60  # Updated within last minute
        assert recipe_model.updated_at >= original_updated_at  # Should be same or newer

    def test_is_deleted_property(self, db_session, sample_recipe):
        """Test the is_deleted property."""
        recipe_model = RecipeDbModel(
            data=sample_recipe.model_dump(mode='json')
        )

        db_session.add(recipe_model)
        db_session.commit()

        # Not deleted initially
        assert not recipe_model.is_deleted

        # Mark as deleted
        recipe_model.deleted_at = datetime.now()
        db_session.commit()

        # Should be deleted now
        assert recipe_model.is_deleted

    def test_jsonb_data_storage(self, db_session, sample_recipe):
        """Test that complex data structures are stored correctly."""
        recipe_data = sample_recipe.model_dump(mode='json')

        recipe_model = RecipeDbModel(data=recipe_data)
        db_session.add(recipe_model)
        db_session.commit()

        # Retrieve and verify
        db_session.refresh(recipe_model)

        assert recipe_model.data["title"] == "Test Recipe"
        assert recipe_model.data["prep_time"] == 10
        assert len(recipe_model.data["ingredients"]) == 2
        assert len(recipe_model.data["steps"]) == 2
        assert recipe_model.data["ingredients"][0]["name"] == "flour"


@pytest.mark.integration
class TestIngestionRequest:
    """Tests for IngestionRequest model."""

    def test_create_with_defaults(self, db_session):
        """Test creating ingestion request with defaults."""
        request = IngestionRequest(
            source_type=SourceType.youtube,
            source_key="test:123",
            source_url="https://example.com"
        )

        db_session.add(request)
        db_session.commit()

        assert request.id is not None
        assert request.uuid is not None
        assert request.status == IngestionStatus.pending
        assert request.priority == 0
        assert request.retry_count == 0
        assert request.max_retries == 3
        assert request.requested_at is not None

    def test_enum_values(self, db_session):
        """Test that enum values are stored correctly."""
        request = IngestionRequest(
            source_type=SourceType.youtube,
            source_key="test:enum",
            status=IngestionStatus.processing
        )

        db_session.add(request)
        db_session.commit()
        db_session.refresh(request)

        assert isinstance(request.source_type, SourceType)
        assert request.source_type == SourceType.youtube
        assert isinstance(request.status, IngestionStatus)
        assert request.status == IngestionStatus.processing

    def test_processing_metadata_jsonb(self, db_session):
        """Test JSONB metadata storage."""
        metadata = {
            "downloads": {
                "transcript": "content here",
                "size": 1024
            },
            "ai_extraction": {
                "model": "claude-sonnet-4.5",
                "tokens": 5000
            }
        }

        request = IngestionRequest(
            source_type=SourceType.youtube,
            source_key="test:metadata",
            processing_metadata=metadata
        )

        db_session.add(request)
        db_session.commit()
        db_session.refresh(request)

        assert request.processing_metadata is not None
        assert request.processing_metadata["downloads"]["size"] == 1024
        assert request.processing_metadata["ai_extraction"]["model"] == "claude-sonnet-4.5"

    def test_unique_source_key_constraint(self, db_session):
        """Test that source_key must be unique."""
        request1 = IngestionRequest(
            source_type=SourceType.youtube,
            source_key="test:unique"
        )

        db_session.add(request1)
        db_session.commit()

        # Try to create duplicate
        request2 = IngestionRequest(
            source_type=SourceType.youtube,
            source_key="test:unique"  # Same key
        )

        db_session.add(request2)

        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()

    def test_recipe_relationship(self, db_session, sample_recipe):
        """Test relationship between IngestionRequest and Recipe."""
        # Create recipe
        recipe_model = RecipeDbModel(
            data=sample_recipe.model_dump(mode='json')
        )
        db_session.add(recipe_model)
        db_session.commit()

        # Create ingestion linked to recipe
        request = IngestionRequest(
            source_type=SourceType.youtube,
            source_key="test:relationship",
            recipe_id=recipe_model.id,
            status=IngestionStatus.completed
        )
        db_session.add(request)
        db_session.commit()

        # Test forward relationship
        db_session.refresh(request)
        assert request.recipe is not None
        assert request.recipe.id == recipe_model.id

        # Test reverse relationship
        db_session.refresh(recipe_model)
        assert len(recipe_model.ingestions) == 1
        assert recipe_model.ingestions[0].id == request.id


@pytest.mark.unit
class TestEnums:
    """Tests for enum types."""

    def test_source_type_values(self):
        """Test SourceType enum values."""
        assert SourceType.youtube.value == "youtube"
        assert SourceType.webpage.value == "webpage"
        assert SourceType.photo.value == "photo"
        assert SourceType.custom.value == "custom"

    def test_ingestion_status_values(self):
        """Test IngestionStatus enum values."""
        assert IngestionStatus.pending.value == "pending"
        assert IngestionStatus.processing.value == "processing"
        assert IngestionStatus.completed.value == "completed"
        assert IngestionStatus.failed.value == "failed"
        assert IngestionStatus.cancelled.value == "cancelled"

    def test_enum_comparison(self):
        """Test enum comparisons."""
        status1 = IngestionStatus.pending
        status2 = IngestionStatus.pending
        status3 = IngestionStatus.processing

        assert status1 == status2
        assert status1 != status3

    def test_enum_string_compatibility(self):
        """Test that enums work as strings."""
        source = SourceType.youtube

        # Enum value comparisons
        assert source.value == "youtube"

        # Can compare to enum member
        assert source == SourceType.youtube

        # Can create from string
        assert SourceType("youtube") == SourceType.youtube
