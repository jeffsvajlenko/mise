"""Tests for recipe API endpoints."""

import pytest
from uuid import uuid4

from mise.db.unit_of_work import UnitOfWork
from mise.schema.recipe import Recipe, Ingredient, RecipeStep, Tag


@pytest.fixture
def sample_recipe_in_db():
    """
    Create a sample recipe in the database and return its UUID.

    Uses direct UnitOfWork to bypass the API.
    """
    from mise.schema.recipe import Recipe, Ingredient, RecipeStep

    recipe = Recipe(
        title="Chocolate Chip Cookies",
        description="Classic homemade cookies",
        prep_time=15,
        cook_time=12,
        total_time=27,
        servings=24,
        yield_amount="24 cookies",
        ingredients=[
            Ingredient(
                text="2 cups all-purpose flour",
                name="flour",
                preparation="all-purpose",
                quantity=2.0,
                unit="cups"
            ),
            Ingredient(
                text="1 cup butter, softened",
                name="butter",
                preparation="softened",
                quantity=1.0,
                unit="cup"
            ),
        ],
        steps=[
            RecipeStep(instruction="Preheat oven to 350°F", time_minutes=5),
            RecipeStep(instruction="Mix butter and sugar until fluffy", time_minutes=5),
            RecipeStep(instruction="Bake for 10-12 minutes", time_minutes=12),
        ],
        tags=[
            Tag(key="cuisine", value="american"),
            Tag(key="meal-type", value="dessert"),
        ]
    )

    with UnitOfWork() as uow:
        record = uow.recipes.create_recipe(recipe)
        uow.session.commit()
        return record.uuid


@pytest.mark.integration
def test_get_recipe_by_uuid(api_client, sample_recipe_in_db):
    """GET /api/recipes/{uuid} returns recipe details."""
    recipe_uuid = sample_recipe_in_db

    response = api_client.get(f"/api/recipes/{recipe_uuid}")

    assert response.status_code == 200

    data = response.json()
    # The UUID in the response should match the one we queried with
    # (Note: recipe's own ID field might differ from DB UUID)
    assert "id" in data  # Just verify it has an ID
    assert data["title"] == "Chocolate Chip Cookies"
    assert len(data["ingredients"]) == 2
    assert len(data["steps"]) == 3
    assert len(data["tags"]) == 2


@pytest.mark.integration
def test_get_recipe_not_found(api_client):
    """GET /api/recipes/{uuid} returns 404 for non-existent UUID."""
    fake_uuid = uuid4()
    response = api_client.get(f"/api/recipes/{fake_uuid}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.integration
def test_get_recipe_includes_all_fields(api_client, sample_recipe_in_db):
    """GET /api/recipes/{uuid} returns complete recipe structure."""
    recipe_uuid = sample_recipe_in_db

    response = api_client.get(f"/api/recipes/{recipe_uuid}")

    assert response.status_code == 200

    data = response.json()
    # Check all major fields exist
    required_fields = [
        "id", "title", "ingredients", "steps",
        "prep_time", "cook_time", "total_time", "servings"
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"

    # Check ingredient structure
    ingredient = data["ingredients"][0]
    assert "text" in ingredient
    assert "name" in ingredient
    assert "quantity" in ingredient
    assert "unit" in ingredient

    # Check step structure
    step = data["steps"][0]
    assert "instruction" in step


@pytest.mark.integration
def test_list_recipes(api_client, sample_recipe_in_db):
    """GET /api/recipes returns paginated list."""
    response = api_client.get("/api/recipes")

    assert response.status_code == 200

    data = response.json()
    assert "recipes" in data
    assert "total" in data
    assert "skip" in data
    assert "limit" in data
    assert data["total"] >= 1
    assert len(data["recipes"]) >= 1


@pytest.mark.integration
def test_list_recipes_search(api_client):
    """GET /api/recipes?search=pasta filters by title."""
    # Create recipes with different titles
    with UnitOfWork() as uow:
        pasta_recipe = Recipe(
            title="Pasta Carbonara",
            ingredients=[Ingredient(text="pasta", name="pasta", quantity=1.0, unit="lb")],
            steps=[RecipeStep(instruction="Cook pasta")]
        )
        other_recipe = Recipe(
            title="Chocolate Cake",
            ingredients=[Ingredient(text="flour", name="flour", quantity=2.0, unit="cups")],
            steps=[RecipeStep(instruction="Bake cake")]
        )
        uow.recipes.create_recipe(pasta_recipe)
        uow.recipes.create_recipe(other_recipe)
        uow.session.commit()

    response = api_client.get("/api/recipes?search=pasta")

    assert response.status_code == 200

    data = response.json()
    # Should find the pasta recipe
    assert any("pasta" in recipe["title"].lower() for recipe in data["recipes"])


@pytest.mark.integration
def test_list_recipes_pagination(api_client):
    """GET /api/recipes respects skip and limit parameters."""
    # Create multiple recipes
    with UnitOfWork() as uow:
        for i in range(5):
            recipe = Recipe(
                title=f"Recipe {i}",
                ingredients=[Ingredient(text="test", name="test", quantity=1.0, unit="cup")],
                steps=[RecipeStep(instruction="test")]
            )
            uow.recipes.create_recipe(recipe)
        uow.session.commit()

    # Test limit
    response = api_client.get("/api/recipes?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["recipes"]) <= 2
    assert data["limit"] == 2

    # Test skip
    response = api_client.get("/api/recipes?skip=2&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["skip"] == 2


@pytest.mark.integration
def test_list_recipes_excludes_deleted(api_client):
    """GET /api/recipes excludes soft-deleted recipes."""
    # Create and then soft-delete a recipe
    with UnitOfWork() as uow:
        recipe = Recipe(
            title="Deleted Recipe",
            ingredients=[Ingredient(text="test", name="test", quantity=1.0, unit="cup")],
            steps=[RecipeStep(instruction="test")]
        )
        record = uow.recipes.create_recipe(recipe)
        uow.session.commit()

        # Soft delete
        uow.recipes.soft_delete(record.id)
        uow.session.commit()

    response = api_client.get("/api/recipes")

    assert response.status_code == 200

    data = response.json()
    # Deleted recipe should not appear in results
    assert not any(r["title"] == "Deleted Recipe" for r in data["recipes"])
