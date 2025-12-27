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
        min_length=1,
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
        min_length=1,
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
        ge=0,
        description="Approximate time in minutes to complete step."
    )
    notes: str | None = Field(
        default=None,
        min_length=1,
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

class Recipe(BaseModel):
    """Schema for recipe responses. Includes database fields."""

    id: UUID4 = Field(
        default_factory=lambda: uuid4(),
        description='A unique UUID generated at creation time by default.'
    )

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
        ge=0, 
        description="Prep time in minutes"
    )
    cook_time: int | None = Field(
        default=None, 
        ge=0, 
        description="Cook time in minutes"
    )
    total_time: int | None = Field(
        default=None,
        ge=0,
        description="Total time in minutes (auto-calculated if not provided)"
    )
    servings: int | None = Field(
        default=None,
        ge=1,
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