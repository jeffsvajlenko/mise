"""Convert Pydantic Recipe schema to Claude-compatible JSON schema."""

from mise.schema.recipe import Recipe


def get_recipe_schema() -> dict:
    """
    Get Claude-compatible Recipe JSON schema.

    Uses union_format='primitive_type_array' to minimize anyOf usage.
    After removing constraints from optional fields, this should produce
    a schema with only 4 anyOf occurrences (all acceptable):
    - RecipeStep.substeps (recursive reference)
    - image_url, video_url, source_url (HttpUrl with format validation)

    Returns:
        dict: JSON schema compatible with Claude's tool use API
    """
    return Recipe.model_json_schema(
        mode='serialization',
        union_format='primitive_type_array'
    )


def get_recipe_tool_definition() -> dict:
    """
    Get Claude tool definition for recipe extraction.

    This formats the Recipe schema as a Claude tool definition that can be
    passed to the Anthropic API messages endpoint.

    Returns:
        dict: Tool definition in Anthropic format
    """
    schema = get_recipe_schema()

    return {
        "name": "extract_recipe",
        "description": (
            "Extract structured recipe data from unstructured content. "
            "Parse ingredients with quantities and units, break down cooking "
            "instructions into clear steps, and extract metadata like cooking times, "
            "servings, and tags."
        ),
        "input_schema": schema
    }
