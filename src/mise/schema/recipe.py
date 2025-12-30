from uuid import uuid4
from pydantic import BaseModel, Field, model_validator, HttpUrl, UUID4

class Ingredient(BaseModel):
    """Recipe ingredient"""

    text: str = Field(
        default=...,
        min_length=1,
        description="Natural language specification of the ingredient from the original recipe."
    )
    name: str = Field(
        default=...,
        min_length=1,
        description="Ingredient name without preparation or measurement (e.g., carrot, banana, etc.)",
    )
    preparation: str | None = Field(
        default=None,
        description="Ingredient preparation for measurement (e.g., chopped for chopped carrots).",
    )
    quantity: float = Field(
        default=...,
        ge=0,
        description="Quantity of ingredient required.",
    )
    unit: str = Field(
        default=...,
        min_length=1,
        description="Unit of quantity measurement.",
    )
    notes: str | None = Field(
        default=None,
        description="Additional free-form notes.",
    )
    optional: bool = Field(
        default=False, 
        description="Whether this ingredient is optional"
    )

class RecipeStep(BaseModel):
    """Recipe instruction step with optional substeps."""
    instruction: str = Field(
        default=...,
        min_length=1,
        description="The main instruction for this step.",
    )
    substeps: list["RecipeStep"] | None = Field(
        None, 
        description="Optional substeps for detailed instructions"
    )
    time_minutes: int | None = Field(
        default=None,
        description="Approximate time in minutes to complete step."
    )
    notes: str | None = Field(
        default=None,
        description="Additional notes or tips"
    )

class Tag(BaseModel):
    """Recipe tag with optional value for structured categorization and labeling."""

    key: str = Field(
        default=...,
        min_length=1,
        description="Tag key (e.g., 'cuisine', 'diet', 'meal-type')",
    )

    value: str | None = Field(
        default=None,
        description="Optional tag value (e.g., 'italian', 'vegan', 'dinner')"
    )

    @model_validator(mode="after")
    def normalize_case(self) -> "Tag":
        """Normalize key and value to lowercase for consistent querying."""
        self.key = self.key.lower().strip()
        if self.value:
            self.value = self.value.lower().strip()
        return self


class ResourceUrl(BaseModel):
    """External URL resource associated with a recipe."""

    url: HttpUrl = Field(
        description="The URL of the resource"
    )
    description: str | None = Field(
        default=None,
        description="Optional description or context for this URL (e.g., 'alternative image', 'nutrition calculator', 'related article')"
    )
    resource_type: str | None = Field(
        default=None,
        description="Optional type hint (e.g., 'image', 'video', 'article', 'tool')"
    )


class RecipeFile(BaseModel):
    """File attached to a recipe (photos, etc.)."""

    id: str = Field(
        description="File identifier (e.g., 'original_1', 'thumbnail')"
    )
    path: str = Field(
        description="Relative path from storage root"
    )
    filename: str = Field(
        description="Original filename"
    )
    content_type: str = Field(
        description="MIME type (e.g., 'image/jpeg')"
    )
    size_bytes: int = Field(
        ge=0,
        description="File size in bytes"
    )
    width: int | None = Field(
        default=None,
        description="Image width in pixels (if applicable)"
    )
    height: int | None = Field(
        default=None,
        description="Image height in pixels (if applicable)"
    )
    uploaded_at: str = Field(
        description="ISO 8601 timestamp of upload"
    )

class Recipe(BaseModel):
    """Schema for recipe responses. Includes database fields."""

    id: UUID4 = Field(
        default_factory=lambda: uuid4(),
        description='A unique UUID generated at creation time by default.'
    )

    @model_validator(mode="after")
    def validate_and_clean(self) -> "Recipe":
        """Post-validation: convert empty strings to None and validate minimums."""
        # Convert empty strings to None for optional string fields
        if self.yield_amount is not None and self.yield_amount.strip() == "":
            self.yield_amount = None
        if self.author is not None and self.author.strip() == "":
            self.author = None
        if self.notes is not None and self.notes.strip() == "":
            self.notes = None
        if self.cuisine is not None and self.cuisine.strip() == "":
            self.cuisine = None
        if self.description is not None and self.description.strip() == "":
            self.description = None

        # Validate minimum values for numeric fields (preserving original constraints)
        if self.prep_time is not None and self.prep_time < 0:
            raise ValueError("prep_time must be >= 0")
        if self.cook_time is not None and self.cook_time < 0:
            raise ValueError("cook_time must be >= 0")
        if self.total_time is not None and self.total_time < 0:
            raise ValueError("total_time must be >= 0")
        if self.servings is not None and self.servings < 1:
            raise ValueError("servings must be >= 1")

        # Clean ingredients and steps
        for ingredient in self.ingredients:
            if ingredient.preparation is not None and ingredient.preparation.strip() == "":
                ingredient.preparation = None
            if ingredient.notes is not None and ingredient.notes.strip() == "":
                ingredient.notes = None

        for step in self.steps:
            if step.notes is not None and step.notes.strip() == "":
                step.notes = None
            if step.time_minutes is not None and step.time_minutes < 0:
                raise ValueError(f"Step time_minutes must be >= 0, got {step.time_minutes}")

        # Clean files
        for file in self.files:
            if file.width is not None and file.width < 1:
                raise ValueError(f"File width must be >= 1, got {file.width}")
            if file.height is not None and file.height < 1:
                raise ValueError(f"File height must be >= 1, got {file.height}")

        return self

    title: str = Field(
        default=..., 
        min_length=1, 
        description="Recipe title"
    )
    description: str | None = Field(
        default=None, 
        description="Brief recipe description"
    )
    ingredients: list[Ingredient] = Field(
        min_length=1, 
        description="List of ingredients"
    )
    steps: list[RecipeStep] = Field(
        min_length=1, 
        description="List of recipe steps"
    )
    tags: list[Tag] = Field(
        default=[], 
        description="Structured tags for categorization and filtering"
    )
    prep_time: int | None = Field(
        default=None,
        description="Prep time in minutes"
    )
    cook_time: int | None = Field(
        default=None,
        description="Cook time in minutes"
    )
    total_time: int | None = Field(
        default=None,
        description="Total time in minutes (auto-calculated if not provided)"
    )
    servings: int | None = Field(
        default=None,
        description="Number of servings"
    )
    yield_amount: str | None = Field(
        default=None, 
        description="Yield description (e.g., '2 loaves', '24 cookies')"
    )
    image_url: HttpUrl | None = Field(
        default=None, 
        description="URL to recipe image"
    )
    video_url: HttpUrl | None = Field(
        default=None, 
        description="URL to recipe video"
    )
    source_url: HttpUrl | None = Field(
        default=None, 
        description="Original source URL"
    )
    author: str | None = Field(
        default=None, 
        description="Recipe author or creator"
    )
    notes: str | None = Field(
        default=None,
        description="Additional notes or user comments"
    )
    cuisine: str | None = Field(
        default=None,
        description="Cuisine type (e.g., 'Italian', 'Mexican')"
    )
    files: list[RecipeFile] = Field(
        default=[],
        description="Files attached to this recipe (photos, videos, etc.)"
    )
    resource_urls: list[ResourceUrl] = Field(
        default=[],
        description="Additional URLs found in the recipe source (alternative images, related articles, tools, etc.)"
    )