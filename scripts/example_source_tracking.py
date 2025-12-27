#!/usr/bin/env python3
"""
Example usage of source tracking for recipe deduplication.

Demonstrates:
- Creating recipes from different sources
- Preventing duplicates
- Upserting (create or update)
- Querying by source
"""

from mise.db.database import engine
from mise.schema.recipe import Recipe, Ingredient, RecipeStep, Tag
from mise.repository import RecipeRepository
from sqlalchemy.orm import Session


def main():
    """Run source tracking examples."""

    with Session(engine) as session:
        repo = RecipeRepository(session)

        print("=== Source Tracking Example ===\n")

        # Example 1: Create from YouTube
        print("1. Creating recipe from YouTube...")
        youtube_recipe = Recipe(
            title="Gordon Ramsay's Perfect Scrambled Eggs",
            description="Creamy scrambled eggs from YouTube tutorial",
            ingredients=[
                Ingredient(
                    text="3 large eggs",
                    name="eggs",
                    quantity=3,
                    unit="whole"
                ),
                Ingredient(
                    text="15g butter",
                    name="butter",
                    quantity=15,
                    unit="g"
                )
            ],
            steps=[
                RecipeStep(instruction="Crack eggs into cold pan with butter"),
                RecipeStep(instruction="Cook on medium heat, stirring constantly")
            ],
            tags=[Tag(key="source", value="youtube")]
        )

        # YouTube source - using video ID as key
        video_id = "PUP7U5vTMM0"
        record, created = repo.upsert_from_source(
            youtube_recipe,
            source_type="youtube",
            source_key=video_id,
            source_metadata={
                "url": f"https://youtube.com/watch?v={video_id}",
                "channel": "Gordon Ramsay",
                "uploaded_date": "2019-06-15"
            }
        )
        repo.commit()

        print(f"✓ {'Created' if created else 'Found existing'} recipe: {record.recipe.title}")
        print(f"  Source: {record.source_type} ({record.source_key})")
        print()

        # Example 2: Try to create duplicate - should return existing
        print("2. Attempting to create duplicate from same YouTube video...")
        duplicate_recipe = Recipe(
            title="Updated Title: Scrambled Eggs",
            description="Updated description",
            ingredients=youtube_recipe.ingredients,
            steps=youtube_recipe.steps,
            tags=[Tag(key="source", value="youtube")]
        )

        record2, created2 = repo.upsert_from_source(
            duplicate_recipe,
            source_type="youtube",
            source_key=video_id,
            update_if_exists=True  # Will update existing
        )
        repo.commit()

        print(f"✓ {'Created new' if created2 else 'Updated existing'} recipe")
        print(f"  Same ID: {record.id == record2.id}")
        print(f"  Updated title: {record2.recipe.title}")
        print()

        # Example 3: Create from webpage
        print("3. Creating recipe from webpage...")
        webpage_recipe = Recipe(
            title="Classic Chocolate Chip Cookies",
            description="From Serious Eats",
            ingredients=[
                Ingredient(
                    text="200g flour",
                    name="flour",
                    quantity=200,
                    unit="g"
                ),
                Ingredient(
                    text="100g chocolate chips",
                    name="chocolate chips",
                    quantity=100,
                    unit="g"
                )
            ],
            steps=[
                RecipeStep(instruction="Mix dry ingredients"),
                RecipeStep(instruction="Add wet ingredients"),
                RecipeStep(instruction="Bake at 180°C for 12 minutes")
            ],
            tags=[Tag(key="cuisine", value="american")]
        )

        # Normalize URL for consistency
        url = "https://www.seriouseats.com/recipes/chocolate-chip-cookies"
        record3, created3 = repo.upsert_from_source(
            webpage_recipe,
            source_type="webpage",
            source_key=url,
            source_metadata={
                "scraped_at": "2024-01-15T10:30:00Z",
                "site_name": "Serious Eats",
                "author": "Kenji López-Alt"
            }
        )
        repo.commit()

        print(f"✓ Created recipe: {record3.recipe.title}")
        print(f"  Source: {record3.source_type}")
        print(f"  URL: {url}")
        print()

        # Example 4: Create custom (user-created) recipe
        print("4. Creating custom user recipe...")
        custom_recipe = Recipe(
            title="My Family's Secret Pasta Sauce",
            description="Passed down for generations",
            ingredients=[
                Ingredient(
                    text="500g tomatoes",
                    name="tomatoes",
                    quantity=500,
                    unit="g"
                )
            ],
            steps=[
                RecipeStep(instruction="Secret family method")
            ],
            tags=[Tag(key="cuisine", value="italian")]
        )

        # For custom recipes, use the Recipe's UUID as the key
        record4, created4 = repo.upsert_from_source(
            custom_recipe,
            source_type="custom",
            source_key=str(custom_recipe.id),  # Use Recipe's UUID
            source_metadata=None  # No extra metadata needed
        )
        repo.commit()

        print(f"✓ Created recipe: {record4.recipe.title}")
        print(f"  Source: {record4.source_type}")
        print(f"  Key: {record4.source_key}")
        print()

        # Example 5: Find by source
        print("5. Finding recipe by source...")
        found = repo.find_by_source("youtube", video_id)
        if found:
            print(f"✓ Found: {found.recipe.title}")
            print(f"  Metadata: {found.source_metadata}")
        print()

        # Example 6: Get all recipes from a source type
        print("6. Getting all YouTube recipes...")
        youtube_recipes = repo.get_by_source_type("youtube")
        print(f"✓ Found {len(youtube_recipes)} YouTube recipe(s):")
        for r in youtube_recipes:
            print(f"  - {r.recipe.title} (ID: {r.id})")
        print()

        # Example 7: Statistics
        print("7. Source statistics...")
        all_recipes = repo.get_all_recipes()
        print(f"Total recipes: {len(all_recipes)}")

        source_counts = {}
        for r in all_recipes:
            source = r.source_type or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1

        for source, count in sorted(source_counts.items()):
            print(f"  - {source}: {count}")
        print()

        print("=== Example Complete ===")


if __name__ == "__main__":
    main()
