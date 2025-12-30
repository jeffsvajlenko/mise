#!/usr/bin/env python3
"""Manual test script for recipe ingestion service."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mise.db.unit_of_work import UnitOfWork
from mise.ingestion.executor import execute_ingestion_request
from mise.ingestion.models import IngestionInput


def test_text_ingestion():
    """Test ingesting a recipe from text."""
    print("=== Testing Text Ingestion ===")

    recipe_text = """
    Chocolate Chip Cookies

    Ingredients:
    - 2 cups all-purpose flour
    - 1 tsp baking soda
    - 1 tsp salt
    - 1 cup butter, softened
    - 3/4 cup sugar
    - 3/4 cup brown sugar
    - 2 eggs
    - 2 tsp vanilla extract
    - 2 cups chocolate chips

    Instructions:
    1. Preheat oven to 375°F
    2. Mix flour, baking soda, and salt in a bowl
    3. In another bowl, cream butter and sugars
    4. Beat in eggs and vanilla
    5. Gradually stir in flour mixture
    6. Stir in chocolate chips
    7. Drop spoonfuls onto ungreased cookie sheets
    8. Bake 9-11 minutes until golden brown

    Makes about 5 dozen cookies.
    """

    input_data = IngestionInput(
        source_type="text",
        text=recipe_text
    )

    try:
        with UnitOfWork() as uow:
            result = execute_ingestion_request(uow, input_data)

        if result.success:
            print(f"✓ Success! Recipe ID: {result.recipe_id}")
            print(f"  Recipe UUID: {result.recipe_uuid}")
            print(f"  Ingestion ID: {result.ingestion_id}")
            if result.processing_metadata:
                print(f"  Model: {result.processing_metadata.get('model')}")
                print(f"  Tokens: {result.processing_metadata.get('total_tokens')}")
        else:
            print(f"✗ Failed: {result.error_message}")
            print(f"  Retryable: {result.retryable}")

    except Exception as e:
        print(f"✗ Exception: {e}")
        import traceback
        traceback.print_exc()


def test_duplicate_detection():
    """Test that duplicate recipes are detected."""
    print("\n=== Testing Duplicate Detection ===")

    recipe_text = "Simple recipe: Mix 1 cup flour with 1 egg. Bake at 350°F."

    input_data = IngestionInput(
        source_type="text",
        text=recipe_text
    )

    try:
        # First ingestion
        with UnitOfWork() as uow:
            result1 = execute_ingestion_request(uow, input_data)
        print(f"First ingestion: {'Success' if result1.success else 'Failed'} (ID: {result1.recipe_id})")

        # Second ingestion (should be detected as duplicate)
        try:
            with UnitOfWork() as uow:
                result2 = execute_ingestion_request(uow, input_data)
            print(f"✗ Second ingestion should have been rejected as duplicate!")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"✓ Duplicate correctly detected: {e}")
            else:
                print(f"✗ Unexpected error: {e}")

    except Exception as e:
        print(f"✗ Exception: {e}")
        import traceback
        traceback.print_exc()


def test_webpage_ingestion():
    """Test ingesting from a real webpage (if you want to test this)."""
    print("\n=== Testing Webpage Ingestion ===")
    print("Skipping - requires real API key and network access")
    print("To test manually, uncomment the code below and add a recipe URL")

    # service = IngestionService()
    # input_data = IngestionInput(
    #     source_type="webpage",
    #     url="https://example.com/some-recipe"  # Replace with real recipe URL
    # )
    #
    # try:
    #     with UnitOfWork() as uow:
    #         result = service.ingest_recipe(uow, input_data)
    #
    #     if result.success:
    #         print(f"✓ Success! Recipe ID: {result.recipe_id}")
    #     else:
    #         print(f"✗ Failed: {result.error_message}")
    # except Exception as e:
    #     print(f"✗ Exception: {e}")


if __name__ == "__main__":
    print("Recipe Ingestion Service Test")
    print("=" * 50)

    # Check for API key
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n⚠️  WARNING: ANTHROPIC_API_KEY not set in environment")
        print("Set it to test real AI extraction:")
        print("  export ANTHROPIC_API_KEY=your_key_here\n")

    # Run tests
    test_text_ingestion()
    test_duplicate_detection()
    test_webpage_ingestion()

    print("\n" + "=" * 50)
    print("Tests completed!")
