#!/usr/bin/env python3
"""
Example demonstrating the Unit of Work pattern.

This shows how to:
1. Use UnitOfWork for single-repository operations
2. Use UnitOfWork for multi-repository transactions
3. Handle exceptions with automatic rollback
"""

from mise.db.unit_of_work import UnitOfWork
from mise.db.models import RecipeDbModel, SourceType, IngestionStatus
from mise.schema.recipe import Recipe, Ingredient, RecipeStep, Tag


def main():
    print("=" * 60)
    print("Unit of Work Pattern Example")
    print("=" * 60)

    # Example 1: Single repository operation
    print("\n1. Single repository operation")
    print("   Creating a recipe...")

    with UnitOfWork() as uow:
        recipe = Recipe(
            title="Simple Pasta",
            description="Easy weeknight pasta",
            prep_time=5,
            cook_time=15,
            servings=2,
            ingredients=[
                Ingredient(
                    text="200g pasta",
                    name="pasta",
                    quantity=200.0,
                    unit="g"
                ),
                Ingredient(
                    text="2 tbsp olive oil",
                    name="olive oil",
                    quantity=2.0,
                    unit="tbsp"
                )
            ],
            steps=[
                RecipeStep(instruction="Boil pasta according to package directions"),
                RecipeStep(instruction="Drain and toss with olive oil")
            ],
            tags=[
                Tag(key="difficulty", value="easy"),
                Tag(key="meal_type", value="dinner")
            ]
        )

        recipe_model = RecipeDbModel(data=recipe.model_dump(mode='json'))
        created = uow.recipes.create(recipe_model)
        recipe_id = created.id
        # Automatically commits when exiting the 'with' block

    print(f"   ✓ Recipe created with ID: {recipe_id}")

    # Example 2: Multi-repository transaction
    print("\n2. Multi-repository transaction")
    print("   Creating recipe and linking to ingestion...")

    with UnitOfWork() as uow:
        # Create ingestion request
        ingestion = uow.ingestions.create_request(
            source_type=SourceType.webpage,
            source_key="https://example.com/recipe-123",
            source_url="https://example.com/recipe-123",
            requested_by="user_456"
        )
        uow.session.flush()  # Get the ID without committing

        # Create recipe
        recipe = Recipe(
            title="Web Recipe",
            description="From example.com",
            ingredients=[
                Ingredient(text="1 cup flour", name="flour", quantity=1.0, unit="cup")
            ],
            steps=[
                RecipeStep(instruction="Mix ingredients")
            ]
        )
        recipe_model = RecipeDbModel(data=recipe.model_dump(mode='json'))
        created_recipe = uow.recipes.create(recipe_model)

        # Link them together
        uow.ingestions.mark_completed(
            ingestion.id,
            created_recipe.id,
            processing_metadata={"source": "example.com"}
        )

        # All operations committed together as one transaction
        ingestion_id = ingestion.id
        recipe_id = created_recipe.id

    print(f"   ✓ Ingestion #{ingestion_id} linked to Recipe #{recipe_id}")

    # Example 3: Exception handling (auto-rollback)
    print("\n3. Exception handling (auto-rollback)")
    print("   Attempting to create recipe, then raising exception...")

    try:
        with UnitOfWork() as uow:
            recipe = Recipe(
                title="This Won't Be Saved",
                description="Because an exception will occur",
                ingredients=[],
                steps=[]
            )
            recipe_model = RecipeDbModel(data=recipe.model_dump(mode='json'))
            uow.recipes.create(recipe_model)

            # Simulate an error
            raise ValueError("Something went wrong!")
            # Auto-rollback will happen

    except ValueError as e:
        print(f"   ✓ Exception caught: {e}")
        print("   ✓ Changes were automatically rolled back")

    # Example 4: Verify rollback worked
    print("\n4. Verifying rollback worked")
    with UnitOfWork() as uow:
        all_recipes = uow.recipes.get_all_recipes()
        print(f"   ✓ Total recipes in database: {len(all_recipes)}")
        print("   ✓ The failed recipe was not saved")

    # Example 5: Checking for duplicates before creating
    print("\n5. Checking for duplicates (preventing duplicates)")

    source_key = "youtube:duplicate_test"

    with UnitOfWork() as uow:
        # Check if already exists
        existing = uow.ingestions.find_by_source_key(source_key)

        if existing:
            print(f"   → Ingestion already exists: #{existing.id}")
            if existing.recipe_id:
                print(f"   → Already linked to recipe #{existing.recipe_id}")
        else:
            # Create new ingestion
            ingestion = uow.ingestions.create_request(
                source_type=SourceType.youtube,
                source_key=source_key,
                source_url="https://youtube.com/watch?v=test",
                requested_by="user_789"
            )
            print(f"   ✓ Created new ingestion request #{ingestion.id}")

    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)
    print("\nKey takeaways:")
    print("  - Use UnitOfWork() context manager for all database operations")
    print("  - Automatic commit on success, rollback on exception")
    print("  - Access repositories via uow.recipes, uow.ingestions, etc.")
    print("  - All operations in a 'with' block are part of one transaction")


if __name__ == "__main__":
    main()
