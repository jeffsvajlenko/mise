#!/usr/bin/env python3
"""
Example demonstrating the ingestion workflow.

This shows how to:
1. Create an ingestion request
2. Simulate a worker processing it
3. Create a recipe from the ingestion
4. Link them together
"""

from sqlalchemy.orm import Session
from mise.db.database import engine
from mise.db.models import RecipeDbModel, IngestionRequest, SourceType, IngestionStatus
from mise.repository.ingestion import IngestionRepository
from mise.repository.recipe import RecipeRepository
from mise.schema.recipe import Recipe, Ingredient, RecipeStep, Tag


def main():
    print("=" * 60)
    print("Ingestion Workflow Example")
    print("=" * 60)

    with Session(engine) as session:
        ingestion_repo = IngestionRepository(session)
        recipe_repo = RecipeRepository(session)

        # Step 1: User submits a YouTube URL for ingestion
        print("\n1. Creating ingestion request for YouTube video...")

        try:
            request = ingestion_repo.create_request(
                source_type=SourceType.youtube,
                source_key="youtube:dQw4w9WgXcQ",  # Example video ID
                source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                priority=0,
                requested_by="user_123",
                request_params={"extract_images": True, "language": "en"}
            )
            session.commit()
            print(f"   ✓ Created ingestion request #{request.id}")
            print(f"     Status: {request.status}")
            print(f"     Source: {request.source_url}")

        except Exception as e:
            print(f"   ✗ Error: {e}")
            print("     (This might mean the source_key already exists)")
            session.rollback()
            # Try to find existing
            request = ingestion_repo.find_by_source_key("youtube:dQw4w9WgXcQ")
            if request:
                print(f"   → Found existing request #{request.id} with status: {request.status}")

        # Step 2: Worker picks up the job
        print("\n2. Worker claiming next pending job...")

        pending_job = ingestion_repo.get_next_pending("worker-1")

        if pending_job:
            print(f"   ✓ Worker-1 claimed job #{pending_job.id}")
            print(f"     Status: {pending_job.status}")
            print(f"     Worker: {pending_job.worker_id}")
            session.commit()

            # Step 3: Worker processes (download, AI extraction, etc.)
            print("\n3. Worker processing job...")
            print("   → Downloading YouTube transcript...")
            print("   → Running AI extraction...")

            # Simulate processing metadata
            processing_metadata = {
                "downloads": {
                    "transcript": {
                        "content": "Welcome to my cooking channel...",
                        "downloaded_at": "2025-12-27T17:30:00Z",
                        "size_bytes": 5432
                    },
                    "video_metadata": {
                        "title": "Perfect Scrambled Eggs",
                        "channel": "Gordon Ramsay",
                        "duration": 420
                    }
                },
                "ai_extraction": {
                    "model": "claude-sonnet-4.5",
                    "tokens_used": 8500,
                    "confidence": 0.95
                }
            }

            ingestion_repo.update_status(
                pending_job.id,
                status=IngestionStatus.processing,
                processing_metadata=processing_metadata
            )
            session.commit()
            print("   ✓ Processing metadata saved")

            # Step 4: Create the recipe
            print("\n4. Creating recipe from extracted data...")

            recipe = Recipe(
                title="Perfect Scrambled Eggs",
                description="Gordon Ramsay's technique for perfect scrambled eggs",
                cuisine="British",
                prep_time=5,
                cook_time=5,
                servings=2,
                ingredients=[
                    Ingredient(
                        text="3 large eggs, room temperature",
                        name="eggs",
                        quantity=3.0,
                        unit="large",
                        notes="room temperature"
                    ),
                    Ingredient(
                        text="1 tbsp butter",
                        name="butter",
                        quantity=1.0,
                        unit="tbsp"
                    ),
                    Ingredient(
                        text="salt to taste",
                        name="salt",
                        quantity=0.0,
                        unit="pinch",
                        notes="to taste"
                    )
                ],
                steps=[
                    RecipeStep(
                        instruction="Crack eggs into a bowl and whisk"
                    ),
                    RecipeStep(
                        instruction="Melt butter in a pan over medium-low heat"
                    ),
                    RecipeStep(
                        instruction="Add eggs and stir continuously for creamy texture"
                    )
                ],
                tags=[
                    Tag(key="meal_type", value="breakfast"),
                    Tag(key="difficulty", value="easy")
                ]
            )

            # Create RecipeDbModel (source info is in IngestionRequest)
            recipe_model = RecipeDbModel(
                data=recipe.model_dump(mode='json')
            )

            session.add(recipe_model)
            session.flush()  # Get the ID

            print(f"   ✓ Created recipe #{recipe_model.id}")
            print(f"     Title: {recipe.title}")
            print(f"     UUID: {recipe_model.uuid}")

            # Step 5: Mark ingestion as completed and link to recipe
            print("\n5. Linking ingestion to recipe...")

            ingestion_repo.mark_completed(
                pending_job.id,
                recipe_id=recipe_model.id,
                processing_metadata={
                    "recipe_created": True,
                    "final_confidence": 0.95
                }
            )
            session.commit()

            print(f"   ✓ Ingestion #{pending_job.id} marked as completed")
            print(f"   ✓ Linked to recipe #{recipe_model.id}")

            # Step 6: Verify the relationship
            print("\n6. Verifying relationship...")

            # Load recipe with ingestions
            recipe_from_db = session.get(RecipeDbModel, recipe_model.id)
            if recipe_from_db and recipe_from_db.ingestions:
                print(f"   ✓ Recipe has {len(recipe_from_db.ingestions)} ingestion(s):")
                for ing in recipe_from_db.ingestions:
                    print(f"     - Ingestion #{ing.id}: {ing.status}")

            # Load ingestion with recipe
            ingestion_from_db = session.get(IngestionRequest, pending_job.id)
            if ingestion_from_db and ingestion_from_db.recipe:
                print(f"   ✓ Ingestion links to recipe: {ingestion_from_db.recipe.data['title']}")

        else:
            print("   → No pending jobs in queue")

        # Step 7: Queue stats
        print("\n7. Queue Statistics")
        print(f"   Pending: {ingestion_repo.get_pending_count()}")
        print(f"   Processing: {ingestion_repo.get_processing_count()}")

    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
