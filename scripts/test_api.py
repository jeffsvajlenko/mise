#!/usr/bin/env python3
"""Manually test the API by creating ingestions and retrieving recipes."""

import time
import requests
import sys

BASE_URL = "http://localhost:8000"


def test_health():
    """Test health check endpoint."""
    print("Testing health check...")
    response = requests.get(f"{BASE_URL}/api/health")
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.json()}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    print("  ✓ Health check passed\n")


def test_create_ingestion():
    """Test creating an ingestion request."""
    print("Testing ingestion creation...")

    recipe_text = """
    Chocolate Chip Cookies

    Ingredients:
    - 2 cups all-purpose flour
    - 1 cup butter, softened
    - 1 cup brown sugar
    - 2 eggs
    - 2 cups chocolate chips

    Instructions:
    1. Preheat oven to 350°F
    2. Mix butter and sugar until fluffy
    3. Beat in eggs
    4. Stir in flour gradually
    5. Fold in chocolate chips
    6. Drop spoonfuls onto baking sheet
    7. Bake for 10-12 minutes

    Makes 24 cookies
    """

    payload = {"source_type": "text", "text": recipe_text, "metadata": {"test": True}}

    response = requests.post(f"{BASE_URL}/api/ingestions", json=payload)
    print(f"  Status: {response.status_code}")

    if response.status_code != 201:
        print(f"  Error: {response.text}")
        sys.exit(1)

    data = response.json()
    print(f"  Ingestion ID: {data['id']}")
    print(f"  Status: {data['status']}")
    print(f"  UUID: {data['uuid']}")
    print("  ✓ Ingestion created\n")

    return data["id"], data["uuid"]


def test_get_ingestion(ingestion_id):
    """Test getting an ingestion by ID."""
    print(f"Testing get ingestion {ingestion_id}...")
    response = requests.get(f"{BASE_URL}/api/ingestions/{ingestion_id}")
    print(f"  Status: {response.status_code}")

    if response.status_code != 200:
        print(f"  Error: {response.text}")
        return None

    data = response.json()
    print(f"  Status: {data['status']}")
    print(f"  Recipe ID: {data['recipe_id']}")
    print(f"  Recipe UUID: {data['recipe_uuid']}")
    print("  ✓ Ingestion retrieved\n")

    return data


def test_list_ingestions():
    """Test listing ingestions."""
    print("Testing list ingestions...")
    response = requests.get(f"{BASE_URL}/api/ingestions?limit=5")
    print(f"  Status: {response.status_code}")

    if response.status_code != 200:
        print(f"  Error: {response.text}")
        return

    data = response.json()
    print(f"  Total: {data['total']}")
    print(f"  Returned: {len(data['ingestions'])}")
    print("  ✓ Ingestions listed\n")


def test_get_recipe(recipe_uuid):
    """Test getting a recipe by UUID."""
    if not recipe_uuid:
        print("  ⊘ Skipping recipe retrieval (no recipe UUID)\n")
        return

    print(f"Testing get recipe {recipe_uuid}...")
    response = requests.get(f"{BASE_URL}/api/recipes/{recipe_uuid}")
    print(f"  Status: {response.status_code}")

    if response.status_code != 200:
        print(f"  Error: {response.text}")
        return

    data = response.json()
    print(f"  Title: {data['title']}")
    print(f"  Ingredients: {len(data['ingredients'])}")
    print(f"  Steps: {len(data['steps'])}")
    print("  ✓ Recipe retrieved\n")


def test_list_recipes():
    """Test listing recipes."""
    print("Testing list recipes...")
    response = requests.get(f"{BASE_URL}/api/recipes?limit=5")
    print(f"  Status: {response.status_code}")

    if response.status_code != 200:
        print(f"  Error: {response.text}")
        return

    data = response.json()
    print(f"  Total: {data['total']}")
    print(f"  Returned: {len(data['recipes'])}")
    if data["recipes"]:
        print(f"  First recipe: {data['recipes'][0]['title']}")
    print("  ✓ Recipes listed\n")


def main():
    """Run all API tests."""
    print("=" * 60)
    print("Mise API Manual Test")
    print("=" * 60)
    print()
    print("Make sure the API server is running:")
    print("  uv run mise-api")
    print()
    print("And the worker is running:")
    print("  uv run python -m mise.worker.processor")
    print()
    input("Press Enter to continue...")
    print()

    try:
        # Test health
        test_health()

        # Test ingestion creation
        ingestion_id, ingestion_uuid = test_create_ingestion()

        # Test listing ingestions
        test_list_ingestions()

        # Wait for worker to process
        print("Waiting for worker to process ingestion...")
        recipe_uuid = None
        for i in range(30):
            time.sleep(1)
            ingestion = test_get_ingestion(ingestion_id)
            if ingestion and ingestion["status"] in ("completed", "failed"):
                recipe_uuid = ingestion.get("recipe_uuid")
                break
            print(f"  Status: {ingestion['status'] if ingestion else 'unknown'} (waiting...)")

        if not recipe_uuid:
            print("\n⚠ Warning: Ingestion not completed within 30 seconds")
            print("  Check worker logs for errors\n")
        else:
            print(f"\n✓ Ingestion completed! Recipe UUID: {recipe_uuid}\n")

        # Test recipe retrieval
        test_get_recipe(recipe_uuid)

        # Test listing recipes
        test_list_recipes()

        print("=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("\n✗ Error: Could not connect to API server")
        print("  Make sure the API is running: uv run mise-api")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
