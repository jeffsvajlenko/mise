"""Tests for Recipe schema validation and serialization."""
import pytest
from pydantic import ValidationError

from mise.schema.recipe import (
    Recipe, Ingredient, RecipeStep, Tag
)


@pytest.mark.unit
class TestIngredient:
    """Tests for Ingredient model."""

    def test_valid_ingredient(self):
        """Test creating a valid ingredient."""
        ingredient = Ingredient(
            text="200g flour, sifted",
            name="flour",
            quantity=200.0,
            unit="g",
            preparation="sifted"
        )

        assert ingredient.name == "flour"
        assert ingredient.quantity == 200.0
        assert ingredient.unit == "g"
        assert ingredient.preparation == "sifted"
        assert ingredient.optional is False

    def test_ingredient_minimum_fields(self):
        """Test ingredient with only required fields."""
        ingredient = Ingredient(
            text="1 cup water",
            name="water",
            quantity=1.0,
            unit="cup"
        )

        assert ingredient.name == "water"
        assert ingredient.preparation is None
        assert ingredient.notes is None

    def test_ingredient_negative_quantity_fails(self):
        """Test that negative quantity raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Ingredient(
                text="invalid",
                name="flour",
                quantity=-1.0,
                unit="g"
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("quantity",) for e in errors)

    def test_ingredient_optional_flag(self):
        """Test optional ingredient flag."""
        ingredient = Ingredient(
            text="pinch of salt (optional)",
            name="salt",
            quantity=1.0,
            unit="pinch",
            optional=True
        )

        assert ingredient.optional is True


@pytest.mark.unit
class TestRecipeStep:
    """Tests for RecipeStep model."""

    def test_simple_step(self):
        """Test creating a simple recipe step."""
        step = RecipeStep(instruction="Mix flour and water")

        assert step.instruction == "Mix flour and water"
        assert step.substeps is None

    def test_nested_substeps(self):
        """Test recipe step with nested substeps."""
        step = RecipeStep(
            instruction="Prepare the dough",
            substeps=[
                RecipeStep(instruction="Mix dry ingredients"),
                RecipeStep(instruction="Add wet ingredients"),
                RecipeStep(instruction="Knead for 5 minutes")
            ]
        )

        assert len(step.substeps) == 3
        assert step.substeps[0].instruction == "Mix dry ingredients"
        assert step.substeps[2].instruction == "Knead for 5 minutes"

    def test_deeply_nested_substeps(self):
        """Test deeply nested substeps (3 levels)."""
        step = RecipeStep(
            instruction="Make the sauce",
            substeps=[
                RecipeStep(
                    instruction="Prepare base",
                    substeps=[
                        RecipeStep(instruction="Heat pan"),
                        RecipeStep(instruction="Add oil")
                    ]
                ),
                RecipeStep(instruction="Simmer")
            ]
        )

        assert len(step.substeps) == 2
        assert len(step.substeps[0].substeps) == 2


@pytest.mark.unit
class TestRecipe:
    """Tests for Recipe model."""

    def test_minimal_recipe(self):
        """Test creating recipe with minimum required fields."""
        recipe = Recipe(
            title="Simple Toast",
            ingredients=[
                Ingredient(
                    text="2 slices bread",
                    name="bread",
                    quantity=2.0,
                    unit="slices"
                )
            ],
            steps=[
                RecipeStep(instruction="Toast the bread")
            ]
        )

        assert recipe.title == "Simple Toast"
        assert len(recipe.ingredients) == 1
        assert len(recipe.steps) == 1
        assert recipe.description is None
        assert recipe.prep_time is None
        assert recipe.cook_time is None

    def test_full_recipe(self):
        """Test creating recipe with all fields."""
        recipe = Recipe(
            title="Chocolate Cake",
            description="A delicious chocolate cake",
            prep_time=30,
            cook_time=45,
            servings=8,
            ingredients=[
                Ingredient(
                    text="200g flour",
                    name="flour",
                    quantity=200.0,
                    unit="g"
                ),
                Ingredient(
                    text="100g sugar",
                    name="sugar",
                    quantity=100.0,
                    unit="g"
                )
            ],
            steps=[
                RecipeStep(instruction="Mix dry ingredients"),
                RecipeStep(instruction="Bake at 180°C for 45 minutes")
            ],
            tags=[
                Tag(key="meal_type", value="dessert"),
                Tag(key="difficulty", value="medium")
            ],
            source_url="https://example.com/recipe",
            author="Chef John"
        )

        assert recipe.title == "Chocolate Cake"
        assert recipe.prep_time == 30
        assert recipe.cook_time == 45
        assert recipe.servings == 8
        assert len(recipe.ingredients) == 2
        assert len(recipe.steps) == 2
        assert len(recipe.tags) == 2
        assert recipe.author == "Chef John"

    def test_recipe_serialization(self):
        """Test recipe serializes to dict correctly."""
        recipe = Recipe(
            title="Test Recipe",
            ingredients=[
                Ingredient(
                    text="1 cup water",
                    name="water",
                    quantity=1.0,
                    unit="cup"
                )
            ],
            steps=[
                RecipeStep(instruction="Boil water")
            ]
        )

        data = recipe.model_dump(mode='json')

        assert data["title"] == "Test Recipe"
        assert len(data["ingredients"]) == 1
        assert data["ingredients"][0]["name"] == "water"
        assert data["steps"][0]["instruction"] == "Boil water"

    def test_recipe_with_nested_steps_serialization(self):
        """Test recipe with nested steps serializes correctly."""
        recipe = Recipe(
            title="Complex Recipe",
            ingredients=[
                Ingredient(
                    text="flour",
                    name="flour",
                    quantity=100.0,
                    unit="g"
                )
            ],
            steps=[
                RecipeStep(
                    instruction="Prepare dough",
                    substeps=[
                        RecipeStep(instruction="Mix ingredients"),
                        RecipeStep(instruction="Knead")
                    ]
                )
            ]
        )

        data = recipe.model_dump(mode='json')

        assert len(data["steps"]) == 1
        assert len(data["steps"][0]["substeps"]) == 2
        assert data["steps"][0]["substeps"][0]["instruction"] == "Mix ingredients"

    def test_recipe_with_times(self):
        """Test recipe with time fields."""
        recipe = Recipe(
            title="Timed Recipe",
            prep_time=15,
            cook_time=30,
            total_time=45,
            ingredients=[
                Ingredient(text="x", name="x", quantity=1, unit="x")
            ],
            steps=[RecipeStep(instruction="x")]
        )

        assert recipe.prep_time == 15
        assert recipe.cook_time == 30
        assert recipe.total_time == 45

    def test_recipe_empty_ingredients_fails(self):
        """Test that recipe requires at least one ingredient."""
        with pytest.raises(ValidationError) as exc_info:
            Recipe(
                title="Empty Recipe",
                ingredients=[],
                steps=[RecipeStep(instruction="Do something")]
            )

        errors = exc_info.value.errors()
        assert any("ingredients" in str(e) for e in errors)

    def test_recipe_empty_steps_fails(self):
        """Test that recipe requires at least one step."""
        with pytest.raises(ValidationError) as exc_info:
            Recipe(
                title="No Steps",
                ingredients=[
                    Ingredient(text="x", name="x", quantity=1, unit="x")
                ],
                steps=[]
            )

        errors = exc_info.value.errors()
        assert any("steps" in str(e) for e in errors)


@pytest.mark.unit
class TestTag:
    """Tests for Tag model."""

    def test_tag_creation(self):
        """Test creating a tag."""
        tag = Tag(key="cuisine", value="italian")

        assert tag.key == "cuisine"
        assert tag.value == "italian"
