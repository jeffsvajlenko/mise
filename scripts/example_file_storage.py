#!/usr/bin/env python3
"""
Example demonstrating the file storage system.

This shows how to:
1. Save files to recipe directories
2. Extract and store metadata
3. Save temporary ingestion files
4. Retrieve files for serving
"""

import io
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from mise.db.database import engine
from mise.db.models import RecipeDbModel
from mise.repository.recipe import RecipeRepository
from mise.storage.files import get_default_storage
from mise.schema.recipe import Recipe, Ingredient, RecipeStep


def create_sample_image() -> bytes:
    """Create a simple test image."""
    try:
        from PIL import Image
        img = Image.new('RGB', (800, 600), color='red')
        buf = io.BytesIO()
        img.save(buf, 'JPEG')
        return buf.getvalue()
    except ImportError:
        # If PIL not installed, create a tiny valid JPEG
        # This is a 1x1 red JPEG
        return bytes.fromhex(
            'ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707'
            '0709090a140d0a0b0c0b0b0c191213140f1b1a1d1c1b1d1f1e1f1e1f1f1f1f1f1f'
            '1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f'
            '1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f'
            '1fffc00011080001000103012200021101031101ffc4001500010100000000000000'
            '0000000000000000ffda000c03010002110311003f00bfff00ffd9'
        )


def main():
    print("=" * 60)
    print("File Storage Example")
    print("=" * 60)

    # Initialize storage
    storage = get_default_storage()
    print(f"\n📁 Storage path: {storage.base_path}")

    with Session(engine) as session:
        recipe_repo = RecipeRepository(session)

        # Step 1: Create a recipe
        print("\n1. Creating recipe...")

        recipe = Recipe(
            title="Chocolate Chip Cookies",
            description="Classic homemade chocolate chip cookies",
            cuisine="American",
            prep_time=15,
            cook_time=12,
            servings=24,
            ingredients=[
                Ingredient(
                    text="2 cups all-purpose flour",
                    name="flour",
                    quantity=2.0,
                    unit="cups"
                )
            ],
            steps=[
                RecipeStep(instruction="Mix dry ingredients"),
                RecipeStep(instruction="Bake at 350°F for 12 minutes")
            ]
        )

        recipe_model = RecipeDbModel(
            data=recipe.model_dump(mode='json')
        )

        session.add(recipe_model)
        session.flush()  # Get UUID

        print(f"   ✓ Created recipe #{recipe_model.id}")
        print(f"     UUID: {recipe_model.uuid}")

        # Step 2: Save multiple photos
        print("\n2. Saving recipe photos...")

        # Simulate 3 uploaded photos
        photo_data = [
            ("cookie-dough.jpg", create_sample_image()),
            ("cookies-baking.jpg", create_sample_image()),
            ("finished-cookies.jpg", create_sample_image()),
        ]

        metadata_list = []
        for filename, image_bytes in photo_data:
            file_obj = io.BytesIO(image_bytes)
            metadata = storage.save_recipe_file(
                recipe_uuid=recipe_model.uuid,
                file=file_obj,
                original_filename=filename
            )
            metadata_list.append(metadata)
            print(f"   ✓ Saved {filename}")
            print(f"     Path: {metadata['path']}")
            print(f"     Size: {metadata['size_bytes']:,} bytes")
            print(f"     Type: {metadata['content_type']}")
            if metadata['width']:
                print(f"     Dimensions: {metadata['width']}x{metadata['height']}")

        # Step 3: Store metadata in database (in recipe JSONB)
        print("\n3. Storing metadata in database...")

        # Update recipe data with file metadata
        recipe_model.data['files'] = metadata_list
        flag_modified(recipe_model, 'data')  # Tell SQLAlchemy the JSONB changed
        session.commit()

        print(f"   ✓ Stored metadata for {len(metadata_list)} files in recipe JSONB")

        # Step 4: Retrieve and display
        print("\n4. Retrieving recipe with file metadata...")

        retrieved = session.get(RecipeDbModel, recipe_model.id)
        print(f"   ✓ Recipe: {retrieved.data['title']}")
        print(f"   ✓ Files attached: {len(retrieved.data.get('files', []))}")

        for file_meta in retrieved.data.get('files', []):
            print(f"\n     File: {file_meta['filename']}")
            print(f"       ID: {file_meta['id']}")
            print(f"       Path: {file_meta['path']}")
            print(f"       Size: {file_meta['size_bytes']:,} bytes")

            # Verify file exists
            file_path = storage.get_file_path(file_meta['path'])
            if file_path.exists():
                print(f"       ✓ File exists on disk")
            else:
                print(f"       ✗ File missing!")

        # Step 5: Demonstrate temporary file storage
        print("\n5. Saving temporary ingestion file...")

        temp_content = b"This is a temporary transcript file for processing"
        temp_file = io.BytesIO(temp_content)

        temp_path = storage.save_temp_file(
            ingestion_id=999,
            file=temp_file,
            filename="transcript.txt"
        )

        print(f"   ✓ Saved temporary file")
        print(f"     Path: {temp_path}")
        print(f"     Size: {len(temp_content):,} bytes")

        # Cleanup temp files
        print("\n6. Cleaning up temporary files...")
        storage.delete_temp_files(999)

        if not temp_path.exists():
            print(f"   ✓ Temporary files deleted")
        else:
            print(f"   ✗ Cleanup failed")

        # Step 7: Show storage directory structure
        print("\n7. Directory structure (with UUID sharding):")
        recipe_dir = storage._get_recipe_dir(recipe_model.uuid)
        uuid_str = str(recipe_model.uuid)

        if recipe_dir.exists():
            print(f"\n   recipes/")
            print(f"     {uuid_str[0:2]}/          # Shard level 1")
            print(f"       {uuid_str[2:4]}/        # Shard level 2")
            print(f"         {uuid_str}/")
            for file in sorted(recipe_dir.iterdir()):
                size = file.stat().st_size
                print(f"           ├── {file.name} ({size:,} bytes)")

    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)
    print("\nTo inspect the files:")
    print(f"  ls -lh {storage.base_path}/recipes/")
    print(f"\nTo clean up (optional):")
    print(f"  rm -rf {storage.base_path}")
    print()


if __name__ == "__main__":
    main()
