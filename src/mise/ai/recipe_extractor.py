"""Recipe extraction using Claude API with tool use."""

import re
import time
from pathlib import Path
from typing import TypeAlias

from youtube_transcript_api import YouTubeTranscriptApi

from mise.schema.recipe import Recipe
from mise.ai.client import get_anthropic_client, get_default_model, get_default_max_tokens
from mise.ai.schema_converter import get_recipe_tool_definition
from mise.ai.image_handler import load_image_as_base64, validate_image_for_api
from mise.ai.webpage_scraper import scrape_webpage
from mise.ingestion.source_utils import create_source_key, normalize_url, SourceType


# Type alias for extraction results
ExtractionResult: TypeAlias = tuple[Recipe, dict, dict]


def _build_system_prompt() -> str:
    """Build the system prompt for recipe extraction."""
    return """You are an expert recipe parser and culinary assistant. Your task is to extract structured recipe data from unstructured content with high accuracy.

## Ingredient Extraction

CRITICAL - Compound Ingredients:
- If a recipe lists compound ingredients like "salt and pepper", create TWO separate ingredient entries
- Example: "2 tsp salt and pepper" → two ingredients: "1 tsp salt" and "1 tsp pepper"
- Common patterns: "salt and pepper", "flour and sugar", "oil or butter"

Ingredient Format:
- text: Full original text as written (e.g., "2 cups all-purpose flour, sifted")
- name: Core ingredient without quantity/prep (e.g., "all-purpose flour")
- quantity: Numeric value (e.g., 2)
- unit: Standardized unit (e.g., "cup", "tsp", "g")
- preparation: How to prep (e.g., "sifted", "chopped", "melted")
- notes: Additional context (e.g., "or substitute with whole wheat")
- optional: Boolean if marked as optional

Guidelines:
- Parse ALL ingredients with precise quantities, units, and preparation methods
- For ranges like "1-2 cups", use the middle value (1.5) or lower bound
- Extract preparation methods separately from ingredient name
- Mark ingredients as optional only if explicitly stated
- Use empty string ("") for missing optional string fields, 0 for missing numeric fields

## Recipe Steps

- Break down cooking instructions into clear, sequential steps
- Each step should be actionable and focused on a single task
- Extract timer information when mentioned (e.g., "bake for 30 minutes" → timer_minutes: 30)
- Preserve the author's voice and specific techniques
- Use substeps for complex multi-part steps if needed
- Include helpful notes for tips, substitutions, or warnings

## Metadata Extraction

Times:
- Extract prep_time, cook_time in minutes (convert hours: 1.5 hours → 90 minutes)
- If only total_time given, try to estimate prep vs cook based on steps
- Be conservative with estimates - better to leave blank than guess wildly

Servings:
- Extract numeric servings (e.g., "serves 4-6" → 5, "makes 12 cookies" → 12)
- Use yield_amount for non-serving yields (e.g., "2 cups sauce", "1 9-inch cake")

Other Fields:
- title: Recipe name, cleaned and formatted
- description: Brief overview if provided
- cuisine: Type of cuisine (e.g., "italian", "mexican", "japanese")
- category: Meal category (e.g., "dessert", "main course", "appetizer")
- author: Recipe author or source attribution
- notes: General recipe notes, tips, or variations

## Tagging Guidelines

Provide 5-10 tags per recipe covering:
- Difficulty: "easy", "medium", "hard", "beginner-friendly"
- Dietary: "vegetarian", "vegan", "gluten-free", "dairy-free", "low-carb", "keto", "paleo"
- Cooking method: "baked", "fried", "grilled", "slow-cooker", "instant-pot", "no-bake", "one-pot"
- Meal type: "breakfast", "lunch", "dinner", "snack", "dessert", "appetizer"
- Occasion: "weeknight", "holiday", "party", "meal-prep", "kid-friendly", "date-night"
- Season: "summer", "fall", "winter", "spring"
- Flavor profile: "sweet", "savory", "spicy", "tangy", "umami"
- Cuisine style: "comfort-food", "healthy", "indulgent", "traditional", "fusion"
- Main ingredient: "chicken", "chocolate", "pasta", "seafood"

All tags should be lowercase and standardized.

## URL Extraction

- image_url: Main recipe image URL (highest quality if multiple available)
- video_url: Recipe video URL if available
- resource_urls: Additional URLs found in content with description and type:
  - Alternative images
  - Related recipes
  - Nutrition calculators
  - Product links
  - Source articles
  - Each entry should have: url, description (what it is), resource_type (hint like "image", "video", "article", "tool")

## Handling Missing Data

- Use empty string ("") for missing optional string fields
- Use 0 for missing numeric fields
- Use empty list ([]) for missing list fields
- Only make educated guesses for metadata when highly confident
- Better to leave blank than to invent information

## Special Cases

- If content contains multiple recipes, extract only the primary/first one
- For ambiguous measurements, prefer metric units when source doesn't specify
- Preserve original language and tone in step instructions
- Handle informal/conversational content (especially from videos) by extracting key information"""


def _extract_with_claude(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int | None = None
) -> tuple[Recipe, dict]:
    """
    Call Claude API with tool use to extract recipe.

    Args:
        messages: List of message dicts for Claude API
        model: Model to use (defaults to configured model)
        max_tokens: Max tokens (defaults to configured value)

    Returns:
        tuple[Recipe, dict]: (parsed Recipe object, processing metadata)

    Raises:
        ValueError: If extraction fails or returns invalid data
    """
    client = get_anthropic_client()
    tool_def = get_recipe_tool_definition()

    model = model or get_default_model()
    max_tokens = max_tokens or get_default_max_tokens()

    start_time = time.time()

    # Call API with tool use
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[tool_def],
        messages=messages
    )

    extraction_time_ms = int((time.time() - start_time) * 1000)

    # Extract tool use from response
    tool_use = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_recipe":
            tool_use = block
            break

    if not tool_use:
        raise ValueError(
            "Claude did not use the extract_recipe tool. "
            f"Response: {response.content}"
        )

    # Parse recipe from tool input
    try:
        recipe = Recipe.model_validate(tool_use.input)
    except Exception as e:
        raise ValueError(f"Failed to validate extracted recipe: {e}") from e

    # Build processing metadata
    processing_metadata = {
        "model": model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        "extraction_time_ms": extraction_time_ms,
        "api_request_id": response.id,
        "stop_reason": response.stop_reason,
        "raw_request": {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": [tool_def]
        },
        "raw_response": {
            "id": response.id,
            "type": response.type,
            "role": response.role,
            "content": [
                {
                    "type": block.type,
                    **({"text": block.text} if hasattr(block, "text") else {}),
                    **({"name": block.name, "input": block.input} if hasattr(block, "name") else {})
                }
                for block in response.content
            ],
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }
        }
    }

    return recipe, processing_metadata


def extract_from_webpage(url: str) -> ExtractionResult:
    """
    Extract recipe from a webpage URL.

    This function:
    1. Scrapes the webpage content using Beautiful Soup
    2. Extracts the main content and cleans it
    3. Sends the content to Claude for recipe extraction
    4. Returns the Recipe with source and processing metadata

    Args:
        url: URL of the webpage containing the recipe

    Returns:
        ExtractionResult: (Recipe, source_metadata, processing_metadata)

    Raises:
        requests.RequestException: If webpage cannot be fetched
        ValueError: If content cannot be extracted or parsed

    Example:
        >>> recipe, source_meta, proc_meta = extract_from_webpage(
        ...     "https://www.example.com/recipes/chocolate-cake"
        ... )
        >>> print(f"Extracted: {recipe.title}")
    """
    # Scrape webpage content
    scraped_data = scrape_webpage(url)

    # Build content for extraction
    content_parts = []

    if scraped_data['title']:
        content_parts.append(f"Page Title: {scraped_data['title']}\n")

    content_parts.append(scraped_data['content'])

    content = '\n'.join(content_parts)

    messages = [
        {
            "role": "user",
            "content": f"""Extract the recipe from the following webpage content:

{content}

IMPORTANT NOTES FOR WEBPAGES:
- Content has been converted to markdown and cleaned, but may still contain some non-recipe text
- Look for structured recipe sections (ingredients list, instructions/directions, etc.)
- Extract image URLs, video URLs, and other resource URLs found in the content
- Page may include blog post text, ads, or tangents - focus on the recipe itself
- Common recipe metadata may be in structured format or prose
- Extract author attribution if present
- Ignore comment sections, related recipes, or advertisement content"""
        }
    ]

    recipe, processing_metadata = _extract_with_claude(messages)

    # Build source metadata
    source_metadata = {
        "source_type": "webpage",
        "source_key": create_source_key(SourceType.WEBPAGE, url),
        "source_url": normalize_url(url),
        "page_title": scraped_data['title'],
    }

    return recipe, source_metadata, processing_metadata


def extract_from_text(
    text: str,
    source_url: str | None = None
) -> ExtractionResult:
    """
    Extract recipe from plain text content.

    Args:
        text: Recipe text to parse (from webpage, document, etc.)
        source_url: Optional URL where content was sourced from

    Returns:
        ExtractionResult: (Recipe, source_metadata, processing_metadata)

    Example:
        >>> text = "Chocolate Chip Cookies\\n\\nIngredients:\\n- 2 cups flour\\n..."
        >>> recipe, source_meta, proc_meta = extract_from_text(text)
    """
    messages = [
        {
            "role": "user",
            "content": f"""Extract the recipe from the following text:

{text}

IMPORTANT NOTES:
- Text may be formatted, unformatted, or partially structured
- Extract all ingredients and steps in the order they appear
- If text contains multiple recipes, extract only the first/primary one
- Preserve original measurements and terminology"""
        }
    ]

    recipe, processing_metadata = _extract_with_claude(messages)

    # Build source metadata
    source_metadata = {
        "source_type": "webpage" if source_url else "text",
        "source_key": create_source_key(SourceType.WEBPAGE, source_url) if source_url else None,
        "source_url": normalize_url(source_url) if source_url else None,
    }

    return recipe, source_metadata, processing_metadata


def _extract_youtube_video_id(url: str) -> str:
    """
    Extract YouTube video ID from various URL formats.

    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/v/VIDEO_ID

    Args:
        url: YouTube URL

    Returns:
        str: Video ID

    Raises:
        ValueError: If URL format is not recognized

    Example:
        >>> _extract_youtube_video_id("https://www.youtube.com/watch?v=Y8Tko2YC5hA")
        'Y8Tko2YC5hA'
    """
    # Pattern matches various YouTube URL formats
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",  # Direct video ID
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError(f"Could not extract video ID from URL: {url}")


def _get_youtube_transcript(video_id: str, languages: list[str] | None = None) -> str:
    """
    Get transcript for a YouTube video.

    Args:
        video_id: YouTube video ID
        languages: List of language codes to try (default: ['en'])

    Returns:
        str: Full transcript as plain text

    Raises:
        Exception: If transcript cannot be retrieved

    Example:
        >>> transcript = _get_youtube_transcript("Y8Tko2YC5hA")
        >>> print(transcript[:100])
    """
    if languages is None:
        languages = ["en"]

    # Get transcript using API
    api = YouTubeTranscriptApi()
    fetched_transcript = api.fetch(video_id, languages=languages)

    # Join text segments with newlines
    transcript = "\n".join(snippet.text for snippet in fetched_transcript)

    return transcript


def extract_from_youtube(url: str, languages: list[str] | None = None) -> ExtractionResult:
    """
    Extract recipe from YouTube video URL.

    This function:
    1. Extracts the video ID from the URL
    2. Downloads the video transcript
    3. Sends the transcript to Claude for recipe extraction
    4. Returns the Recipe with source and processing metadata

    Args:
        url: YouTube video URL or video ID
        languages: List of language codes to try for transcript (default: ['en'])

    Returns:
        ExtractionResult: (Recipe, source_metadata, processing_metadata)

    Raises:
        ValueError: If URL format is not recognized
        Exception: If transcript cannot be retrieved

    Example:
        >>> recipe, source_meta, proc_meta = extract_from_youtube(
        ...     "https://www.youtube.com/watch?v=Y8Tko2YC5hA"
        ... )
        >>> print(f"Extracted: {recipe.title}")
    """
    # Extract video ID from URL
    video_id = _extract_youtube_video_id(url)

    # Construct canonical URL
    canonical_url = f"https://www.youtube.com/watch?v={video_id}"

    # Get transcript
    transcript = _get_youtube_transcript(video_id, languages)

    # Build messages for extraction
    messages = [
        {
            "role": "user",
            "content": f"""Extract the recipe from this YouTube video transcript:

{transcript}

IMPORTANT NOTES FOR VIDEO TRANSCRIPTS:
- Transcripts are auto-generated and may contain errors or lack punctuation
- Content may be informal, conversational, or include tangents
- Quantities may be spoken differently (e.g., "one and a half cups" → 1.5 cups)
- Ingredients may be mentioned multiple times or out of order
- Instructions may include personal anecdotes - extract only cooking steps
- Time references may be approximate (e.g., "about 30 minutes" → 30 minutes)
- Extract the core recipe and ignore off-topic content"""
        }
    ]

    recipe, processing_metadata = _extract_with_claude(messages)

    # Build source metadata
    source_metadata = {
        "source_type": "youtube",
        "source_key": create_source_key(SourceType.YOUTUBE, video_id),
        "source_url": canonical_url,
        "video_id": video_id,
    }

    return recipe, source_metadata, processing_metadata


def extract_from_image(image_path: Path | str) -> ExtractionResult:
    """
    Extract recipe from an image using Claude's vision API.

    Args:
        image_path: Path to recipe image (photo of recipe card, screenshot, etc.)

    Returns:
        ExtractionResult: (Recipe, source_metadata, processing_metadata)

    Raises:
        FileNotFoundError: If image file doesn't exist
        ValueError: If image is invalid or extraction fails

    Example:
        >>> recipe, source_meta, proc_meta = extract_from_image("recipe_card.jpg")
    """
    image_path = Path(image_path)

    # Validate image
    validate_image_for_api(image_path)

    # Load image as base64
    image_data = load_image_as_base64(image_path)

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": image_data
                },
                {
                    "type": "text",
                    "text": """Extract the recipe from this image.

IMPORTANT NOTES FOR IMAGES:
- This may be a recipe card, screenshot, handwritten note, printed page, or magazine clipping
- Text may be handwritten (cursive or print) or typed
- Some text may be partially obscured, blurry, or at an angle
- Extract all visible text even if formatting is unclear
- For handwritten recipes, ingredient amounts may use abbreviations (tsp, T, c)
- If servings/yields are not visible, leave blank
- Maintain the recipe structure as closely as possible to the visual layout
- If multiple recipes are visible, extract only the primary/most prominent one
- Extract exactly what is visible - do not infer missing information unless obvious from context"""
                }
            ]
        }
    ]

    recipe, processing_metadata = _extract_with_claude(messages)

    # Build source metadata
    source_metadata = {
        "source_type": "image",
        "source_key": f"image:{image_path.name}",
        "source_url": None,
        "image_path": str(image_path),
        "image_filename": image_path.name,
    }

    return recipe, source_metadata, processing_metadata


def extract_recipe(source_type: str, **kwargs) -> ExtractionResult:
    """
    Master method to extract recipe based on source type.

    Args:
        source_type: One of "text", "webpage", "youtube", "image"
        **kwargs: Arguments specific to the source type

    Returns:
        ExtractionResult: (Recipe, source_metadata, processing_metadata)

    Examples:
        >>> # From text
        >>> extract_recipe("text", text="...", source_url="https://...")

        >>> # From webpage (scrapes and extracts automatically)
        >>> extract_recipe("webpage", url="https://www.example.com/recipe")

        >>> # From YouTube (downloads transcript automatically)
        >>> extract_recipe("youtube", url="https://www.youtube.com/watch?v=...")

        >>> # From image
        >>> extract_recipe("image", image_path="recipe.jpg")
    """
    if source_type == "text":
        return extract_from_text(**kwargs)
    elif source_type == "webpage":
        return extract_from_webpage(**kwargs)
    elif source_type == "youtube":
        return extract_from_youtube(**kwargs)
    elif source_type == "image":
        return extract_from_image(**kwargs)
    else:
        raise ValueError(
            f"Unknown source_type: {source_type}. "
            "Must be one of: text, webpage, youtube, image"
        )
