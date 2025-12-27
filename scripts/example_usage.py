#!/usr/bin/env python3
"""
Example usage of the RecipeRepository.

Demonstrates CRUD operations and queries using the repository pattern.
"""

from mise.db.database import engine
from mise.schema.recipe import Recipe, Ingredient, RecipeStep, Tag
from mise.repository import RecipeRepository
from sqlalchemy.orm import Session


def main():
    """Run example repository operations."""

    # Create a session
    with Session(engine) as session:
        # Initialize repository
        repo = RecipeRepository(session)

        print("=== Recipe Repository Example ===\n")

        # 1. Create a recipe
        print("1. Creating a new recipe...")
        recipe = Recipe(
            title="Classic Spaghetti Carbonara",
            description="Traditional Italian pasta dish",
            ingredients=[
                Ingredient(
                    text="400g spaghetti",
                    name="spaghetti",
                    preparation=None,
                    quantity=400,
                    unit="g",
                    notes=None,
                    optional=False
                ),
                Ingredient(
                    text="200g guanciale, diced",
                    name="guanciale",
                    preparation="diced",
                    quantity=200,
                    unit="g",
                    notes="Can substitute with pancetta",
                    optional=False
                ),
                Ingredient(
                    text="4 large egg yolks",
                    name="egg yolks",
                    preparation=None,
                    quantity=4,
                    unit="whole",
                    notes=None,
                    optional=False
                ),
                Ingredient(
                    text="100g Pecorino Romano, grated",
                    name="Pecorino Romano",
                    preparation="grated",
                    quantity=100,
                    unit="g",
                    notes=None,
                    optional=False
                ),
            ],
            steps=[
                RecipeStep(
                    instruction="Bring a large pot of salted water to boil and cook spaghetti until al dente",
                    substeps=None,
                    time_minutes=10,
                    notes="Reserve 1 cup of pasta water before draining"
                ),
                RecipeStep(
                    instruction="Cook guanciale in a large pan until crispy",
                    substeps=None,
                    time_minutes=5,
                    notes="Do not add oil - the fat will render from the meat"
                ),
                RecipeStep(
                    instruction="Whisk egg yolks with grated Pecorino in a bowl",
                    substeps=None,
                    time_minutes=2,
                    notes=None
                ),
                RecipeStep(
                    instruction="Add hot pasta to the pan with guanciale, remove from heat",
                    substeps=None,
                    time_minutes=1,
                    notes="Off heat is important to prevent scrambling eggs"
                ),
                RecipeStep(
                    instruction="Quickly stir in egg mixture, adding pasta water as needed for creamy sauce",
                    substeps=None,
                    time_minutes=2,
                    notes="Work quickly while pasta is still hot"
                ),
            ],
            tags=[
                Tag(key="cuisine", value="italian"),
                Tag(key="meal-type", value="dinner"),
                Tag(key="difficulty", value="medium"),
                Tag(key="dish-type", value="pasta"),
            ],
            prep_time=10,
            cook_time=15,
            total_time=25,
            servings=4,
            yield_amount=None,
            image_url=None,
            video_url=None,
            source_url=None,
            author="Traditional Recipe",
            notes="The key is to work quickly and keep the pasta hot when mixing with eggs."
        )

        record = repo.create_recipe(recipe)
        repo.commit()

        print(f"✓ Created recipe with ID: {record.id}")
        print(f"  Title: {record.recipe.title}")
        print(f"  Created at: {record.created_at}")
        print(f"  Tags: {[(t.key, t.value) for t in record.recipe.tags]}")
        print()

        # 2. Get by ID
        print(f"2. Retrieving recipe by ID {record.id}...")
        retrieved = repo.get_recipe_by_id(record.id)
        if retrieved:
            print(f"✓ Found: {retrieved.recipe.title}")
            print(f"  Servings: {retrieved.recipe.servings}")
            print(f"  Total time: {retrieved.recipe.total_time} minutes")
        print()

        # 3. Update recipe
        print("3. Updating recipe...")
        recipe.servings = 6
        recipe.notes = "Recipe scaled for 6 servings instead of 4."
        updated = repo.update_recipe(record.id, recipe)
        repo.commit()
        if updated:
            print(f"✓ Updated servings to: {updated.recipe.servings}")
            print(f"  Updated at: {updated.updated_at}")
        print()

        # 4. Search by title
        print("4. Searching for 'carbonara'...")
        results = repo.search_by_title("carbonara")
        print(f"✓ Found {len(results)} recipe(s)")
        for r in results:
            print(f"  - {r.recipe.title} (ID: {r.id})")
        print()

        # 5. Find by tag
        print("5. Finding Italian recipes...")
        italian_recipes = repo.find_by_tag("cuisine", "italian")
        print(f"✓ Found {len(italian_recipes)} Italian recipe(s)")
        for r in italian_recipes:
            print(f"  - {r.recipe.title}")
        print()

        # 6. Get all recipes
        print("6. Getting all recipes...")
        all_recipes = repo.get_all_recipes(limit=10)
        print(f"✓ Total recipes: {repo.count()}")
        for r in all_recipes:
            print(f"  - {r.recipe.title} (ID: {r.id})")
        print()

        # 7. Soft delete
        print(f"7. Soft deleting recipe {record.id}...")
        deleted = repo.soft_delete(record.id)
        repo.commit()
        if deleted:
            print("✓ Recipe soft deleted")

            # Try to get it (should return None)
            not_found = repo.get_recipe_by_id(record.id)
            print(f"  Get without include_deleted: {not_found}")

            # Get with include_deleted
            still_there = repo.get_recipe_by_id(record.id, include_deleted=True)
            if still_there:
                print(f"  Get with include_deleted: Found (deleted_at: {still_there.deleted_at})")
        print()

        # 8. Restore
        print(f"8. Restoring recipe {record.id}...")
        restored = repo.restore(record.id)
        repo.commit()
        if restored:
            print("✓ Recipe restored")
            restored_record = repo.get_recipe_by_id(record.id)
            if restored_record:
                print(f"  Deleted at: {restored_record.deleted_at}")
        print()

        # 9. Count
        print("9. Counting recipes...")
        total = repo.count()
        total_with_deleted = repo.count(include_deleted=True)
        print(f"✓ Active recipes: {total}")
        print(f"✓ Total (including deleted): {total_with_deleted}")
        print()

        print("=== Example Complete ===")


if __name__ == "__main__":
    main()
