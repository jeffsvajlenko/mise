"""Tests for schema converter."""
import pytest
import json

from mise.ai.schema_converter import get_recipe_schema, get_recipe_tool_definition


@pytest.mark.unit
class TestSchemaConverter:
    """Tests for Recipe schema conversion to Claude-compatible format."""

    def test_get_recipe_schema_returns_dict(self):
        """Test that get_recipe_schema returns a dictionary."""
        schema = get_recipe_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "title" in schema

    def test_schema_has_minimal_anyof(self):
        """Test that schema has minimal anyOf usage after constraint removal."""
        schema = get_recipe_schema()
        schema_str = json.dumps(schema)
        anyof_count = schema_str.count('"anyOf"')

        # Should have exactly 4 anyOf occurrences:
        # - RecipeStep.substeps (recursive)
        # - image_url, video_url, source_url (HttpUrl types)
        assert anyof_count == 4, f"Expected 4 anyOf occurrences, got {anyof_count}"

    def test_schema_has_required_fields(self):
        """Test that schema specifies required fields correctly."""
        schema = get_recipe_schema()

        # Recipe required fields
        assert "required" in schema
        assert "title" in schema["required"]
        assert "ingredients" in schema["required"]
        assert "steps" in schema["required"]

        # Optional fields should not be in required
        assert "description" not in schema["required"]
        assert "prep_time" not in schema["required"]

    def test_schema_uses_primitive_type_arrays(self):
        """Test that simple optional fields use type arrays instead of anyOf."""
        schema = get_recipe_schema()

        # Check that simple optional string fields use array type
        description_prop = schema["properties"]["description"]
        assert "type" in description_prop
        assert description_prop["type"] == ["string", "null"]

        # Check that yield_amount also uses array type
        yield_prop = schema["properties"]["yield_amount"]
        assert yield_prop["type"] == ["string", "null"]

    def test_schema_has_nested_definitions(self):
        """Test that schema includes $defs for nested models."""
        schema = get_recipe_schema()

        assert "$defs" in schema
        assert "Ingredient" in schema["$defs"]
        assert "RecipeStep" in schema["$defs"]
        assert "Tag" in schema["$defs"]
        assert "RecipeFile" in schema["$defs"]

    def test_ingredient_schema_no_minlength_constraints(self):
        """Test that Ingredient optional fields have no minLength constraints."""
        schema = get_recipe_schema()
        ingredient_schema = schema["$defs"]["Ingredient"]

        # preparation should not have minLength constraint
        prep_prop = ingredient_schema["properties"]["preparation"]
        assert "minLength" not in prep_prop

        # notes should not have minLength constraint
        notes_prop = ingredient_schema["properties"]["notes"]
        assert "minLength" not in notes_prop

    def test_recipe_step_schema_no_minimum_constraints(self):
        """Test that RecipeStep time_minutes has no minimum constraint."""
        schema = get_recipe_schema()
        step_schema = schema["$defs"]["RecipeStep"]

        time_prop = step_schema["properties"]["time_minutes"]
        assert "minimum" not in time_prop

    def test_recipe_schema_no_time_constraints(self):
        """Test that Recipe time fields have no minimum constraints."""
        schema = get_recipe_schema()

        for field in ["prep_time", "cook_time", "total_time"]:
            field_prop = schema["properties"][field]
            assert "minimum" not in field_prop, f"{field} should not have minimum constraint"

    def test_recipe_schema_no_servings_constraint(self):
        """Test that servings field has no minimum constraint."""
        schema = get_recipe_schema()
        servings_prop = schema["properties"]["servings"]
        assert "minimum" not in servings_prop

    def test_get_recipe_tool_definition(self):
        """Test that tool definition is correctly formatted for Claude API."""
        tool_def = get_recipe_tool_definition()

        assert isinstance(tool_def, dict)
        assert "name" in tool_def
        assert "description" in tool_def
        assert "input_schema" in tool_def

        assert tool_def["name"] == "extract_recipe"
        assert isinstance(tool_def["description"], str)
        assert len(tool_def["description"]) > 0

        # input_schema should be the full Recipe schema
        assert isinstance(tool_def["input_schema"], dict)
        assert "properties" in tool_def["input_schema"]
        assert "title" in tool_def["input_schema"]["properties"]

    def test_recursive_substeps_has_anyof(self):
        """Test that RecipeStep.substeps correctly uses anyOf for recursive reference."""
        schema = get_recipe_schema()
        step_schema = schema["$defs"]["RecipeStep"]

        substeps_prop = step_schema["properties"]["substeps"]
        assert "anyOf" in substeps_prop

        # Should be anyOf with array type and null
        anyof_options = substeps_prop["anyOf"]
        assert len(anyof_options) == 2

        # One option should be array of RecipeStep, other should be null
        types = [opt.get("type") for opt in anyof_options]
        assert "array" in types
        assert "null" in types

    def test_httpurl_fields_have_anyof(self):
        """Test that HttpUrl fields (image_url, etc) have anyOf for format validation."""
        schema = get_recipe_schema()

        for field in ["image_url", "video_url", "source_url"]:
            field_prop = schema["properties"][field]
            assert "anyOf" in field_prop, f"{field} should have anyOf"

            # Should be 2-option anyOf (uri format + null)
            anyof_options = field_prop["anyOf"]
            assert len(anyof_options) == 2

            # One should have format: uri
            formats = [opt.get("format") for opt in anyof_options]
            assert "uri" in formats

            types = [opt.get("type") for opt in anyof_options]
            assert "string" in types
            assert "null" in types
