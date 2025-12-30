#!/usr/bin/env python3
"""Quick test for image ingestion."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mise.db.unit_of_work import UnitOfWork
from mise.ingestion.service import IngestionService
from mise.ingestion.models import IngestionInput

from dotenv import load_dotenv

# Load variables from .env into the environment
load_dotenv()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_image_quick.py <path_to_image>")
        print("Example: python scripts/test_image_quick.py ~/Downloads/recipe_card.jpg")
        sys.exit(1)

    image_path = sys.argv[1]

    if not Path(image_path).exists():
        print(f"Error: Image file not found: {image_path}")
        sys.exit(1)

    print(f"Ingesting recipe from image: {image_path}")

    service = IngestionService()
    input_data = IngestionInput(
        source_type="image",
        image_path=image_path
    )

    try:
        with UnitOfWork() as uow:
            result = service.ingest_recipe(uow, input_data)

        if result.success:
            print(f"\n✓ Success!")
            print(f"  Recipe ID: {result.recipe_id}")
            print(f"  Recipe UUID: {result.recipe_uuid}")
            print(f"  Ingestion ID: {result.ingestion_id}")

            if result.processing_metadata:
                print(f"\nProcessing details:")
                print(f"  Model: {result.processing_metadata.get('model')}")
                print(f"  Tokens: {result.processing_metadata.get('total_tokens')}")

            print(f"\nTo view in database:")
            print(f"  SELECT * FROM recipes WHERE id = {result.recipe_id};")
            print(f"  SELECT * FROM ingestion_requests WHERE id = {result.ingestion_id};")
        else:
            print(f"\n✗ Failed: {result.error_message}")
            print(f"  Retryable: {result.retryable}")
            print(f"  Ingestion ID: {result.ingestion_id}")

    except Exception as e:
        print(f"\n✗ Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
