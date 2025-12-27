# Architecture Review: Recipe Schema Design

## Current Setup

We have three layers:

### 1. Recipe (Business Domain Schema)
**Location:** `src/mise/schema/recipe.py`

```python
class Recipe(BaseModel):
    id: UUID4  # Business UUID
    title: str
    ingredients: list[Ingredient]
    steps: list[RecipeStep]
    tags: list[Tag]
    # ... all business fields
```

**Purpose:** Pure business logic, API contracts, validation

### 2. RecipeModel (SQLAlchemy ORM)
**Location:** `src/mise/db/models.py`

```python
class Recipe(Base):  # Confusing name!
    __tablename__ = "recipes"
    id: Mapped[int]  # Database primary key
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None]
    source_type: Mapped[str | None]
    source_key: Mapped[str | None]
    source_metadata: Mapped[dict | None]
    data: Mapped[dict]  # JSONB - stores Recipe schema
```

**Purpose:** Database persistence, infrastructure

### 3. RecipeRecord (Repository Layer)
**Location:** `src/mise/repository/models.py`

```python
class RecipeRecord(BaseModel):
    # Infrastructure
    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    source_type: str | None
    source_key: str | None
    source_metadata: dict | None

    # Business
    recipe: Recipe
```

**Purpose:** Bridge between ORM and business logic

---

## Issues with Current Setup

### 🔴 Problem 1: Naming Confusion
```python
# Both called "Recipe"!
from mise.schema.recipe import Recipe  # Pydantic
from mise.db.models import Recipe      # SQLAlchemy
```

This is confusing and error-prone. Need to import as:
```python
from mise.db.models import Recipe as RecipeModel
```

### 🟡 Problem 2: UUID vs Integer ID Duplication

**Recipe schema has:**
- `id: UUID4` - Business identifier

**RecipeModel/RecipeRecord has:**
- `id: int` - Database primary key

**Questions:**
1. Do we need both IDs?
2. Should Recipe UUID be stored in JSONB or as a separate column?
3. Can we use UUID as the primary key instead of integer?

### 🟡 Problem 3: Three-Layer Conversion

Data flows through three conversions:
```
API/User → Recipe → RecipeModel → Database
Database → RecipeModel → RecipeRecord → Recipe → API/User
```

This is complex but has benefits (separation of concerns).

---

## Options for Simplification

### Option 1: Keep Current Design ✅ (RECOMMENDED)

**Keep all three layers as-is, just fix naming**

**Changes:**
- Rename `Recipe` (ORM) → `RecipeModel` everywhere
- Keep Recipe (Pydantic) and RecipeRecord separate
- Current UUID stays in JSONB, DB uses integer PK

**Pros:**
- ✅ Clean separation of concerns
- ✅ Business logic never touches SQLAlchemy
- ✅ Easy to test (mock repositories)
- ✅ Can swap storage layer without changing business logic
- ✅ RecipeRecord makes source tracking explicit
- ✅ Recipe schema can evolve independently

**Cons:**
- Slightly more code
- Three schemas to maintain

**Verdict:** This is actually a GOOD architecture. The only issue is naming.

---

### Option 2: Merge RecipeRecord into Repository Response

**Remove RecipeRecord, repository returns tuple or dict**

```python
# Instead of RecipeRecord
def get_recipe_by_id(id: int) -> tuple[Recipe, dict] | None:
    """Returns (recipe, metadata)"""
    return (recipe, {
        "id": model.id,
        "created_at": model.created_at,
        "source_type": model.source_type,
        # ...
    })
```

**Pros:**
- One less class
- Simpler

**Cons:**
- ❌ Loses type safety
- ❌ Metadata as dict is unstructured
- ❌ Can't use `record.created_at`, must use `metadata["created_at"]`
- ❌ Harder to add methods like `is_deleted`

**Verdict:** Not recommended. RecipeRecord provides valuable structure.

---

### Option 3: Use UUID as Primary Key

**Make Recipe.id (UUID) the primary key, remove integer PK**

```python
class RecipeModel(Base):
    id: Mapped[UUID4] = mapped_column(primary_key=True)
    # No integer ID
```

**Pros:**
- One ID instead of two
- UUIDs are globally unique
- Can generate client-side

**Cons:**
- ❌ UUIDs are larger (16 bytes vs 4-8 bytes)
- ❌ Slower index performance
- ❌ Sequential integers are better for pagination/sorting
- ❌ Harder to reference in URLs/logs

**Verdict:** Integer PK is better for databases. UUID for business is fine.

---

### Option 4: Remove UUID from Recipe Schema

**Recipe schema has no ID field, only RecipeRecord has integer ID**

```python
class Recipe(BaseModel):
    # No id field!
    title: str
    ingredients: list[Ingredient]
    # ...
```

**Pros:**
- Simpler Recipe schema
- No dual ID confusion
- Recipe is truly "pure business data"

**Cons:**
- ❌ Can't reference a recipe before it's saved
- ❌ Can't use Recipe.id for source_key (custom recipes)
- ❌ Need ID for some business logic (e.g., "edit this recipe")

**Verdict:** The UUID is useful for business operations, keep it.

---

### Option 5: Flatten RecipeRecord

**Store all Recipe fields directly in RecipeRecord (no nested recipe)**

```python
class RecipeRecord(BaseModel):
    # Infrastructure
    id: int
    created_at: datetime
    source_type: str | None

    # Business (flattened)
    title: str
    ingredients: list[Ingredient]
    steps: list[RecipeStep]
    # ... all Recipe fields duplicated here
```

**Pros:**
- Simpler access: `record.title` instead of `record.recipe.title`
- No nested object

**Cons:**
- ❌ Massive duplication of field definitions
- ❌ Changes to Recipe require changes to RecipeRecord
- ❌ Harder to separate business vs infrastructure
- ❌ Can't reuse Recipe schema for API requests

**Verdict:** Not recommended. Nesting is cleaner.

---

## Recommendation: **Option 1 - Keep Design, Fix Naming**

Your architecture is actually **very good**. The only real issue is the naming collision.

### Proposed Changes:

#### 1. Rename ORM Model
```python
# src/mise/db/models.py
class RecipeModel(Base):  # Was: Recipe
    __tablename__ = "recipes"
    # ... same fields
```

#### 2. Update Imports Throughout
```python
# Before:
from mise.db.models import Recipe as RecipeModel

# After:
from mise.db.models import RecipeModel
```

#### 3. Keep Everything Else
- Recipe (Pydantic) - business domain ✅
- RecipeModel (SQLAlchemy) - database ✅
- RecipeRecord (Pydantic) - repository layer ✅

---

## Why This Architecture Is Good

### 1. **Clean Separation**
```
┌─────────────────────────────────────────┐
│  Recipe (Pydantic)                      │  ← Business Logic
│  - Pure business data                   │  ← API contracts
│  - No DB concerns                       │  ← Validation rules
└─────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│  RecipeRecord (Pydantic)                │  ← Repository Layer
│  - Business + Infrastructure            │  ← Bridge layer
│  - Type-safe metadata                   │  ← Clean API
└─────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│  RecipeModel (SQLAlchemy)               │  ← Database Layer
│  - ORM mapping                          │  ← Persistence
│  - JSONB storage                        │  ← Indexes, constraints
└─────────────────────────────────────────┘
```

### 2. **Testability**
```python
# Easy to mock repositories
def test_business_logic():
    mock_repo = Mock(RecipeRepository)
    mock_repo.get_recipe_by_id.return_value = RecipeRecord(...)
    # Test business logic without DB
```

### 3. **Flexibility**
- Want to add a field? Update Recipe schema
- Want to change storage? Only update RecipeModel
- Want to add metadata? Only update RecipeRecord
- Each layer can evolve independently

### 4. **Type Safety**
```python
# RecipeRecord gives structure
record = repo.get_recipe_by_id(1)
record.created_at  # Type-safe!
record.recipe.title  # Type-safe!
record.is_deleted  # Property works!

# vs dict approach:
record = repo.get_recipe_by_id(1)
record["created_at"]  # What if typo? createdAt?
record["recipe"]["title"]  # No autocomplete
```

---

## The Real Question: UUID Handling

The only legitimate debate is about the UUID:

### Current: UUID in JSONB + Integer PK
```python
# Recipe schema
id: UUID4  # Business identifier

# Database
id: int  # Primary key (1, 2, 3...)
data: JSONB  # Contains the UUID inside
```

**Pros:**
- Integer PK is efficient
- UUID available for business logic
- UUID persisted in JSONB with recipe data

**Cons:**
- Dual identifiers can be confusing
- UUID not easily queryable (need JSONB query)

### Alternative: UUID as Separate Column
```python
# Database
id: int  # Primary key
uuid: UUID  # Business identifier (indexed)
data: JSONB  # Recipe data WITHOUT UUID
```

**Pros:**
- Can query by UUID efficiently: `WHERE uuid = ?`
- Both IDs are explicit
- UUID not duplicated in JSONB

**Cons:**
- More columns
- UUID is infrastructure, not business data

---

## Final Recommendation

### Keep Current Architecture, Make These Changes:

1. **Rename ORM class** from `Recipe` to `RecipeModel`
2. **Optionally:** Add `uuid` column to database (separate from JSONB)
3. **Keep:** Recipe, RecipeRecord, RecipeModel as three layers

### Rationale:

Your architecture follows **best practices**:
- ✅ Domain-Driven Design (DDD)
- ✅ Repository Pattern
- ✅ Separation of Concerns
- ✅ Type Safety
- ✅ Testability

The naming collision is the ONLY issue. Once fixed, this is a solid, maintainable architecture that will scale well.

### If You Want to Simplify:

**Only simplify if:**
- This is a prototype/MVP
- Team is very small (1-2 people)
- No plans for complex business logic

**Then consider:**
- Merge RecipeRecord into repository return types (tuple)
- Use RecipeModel directly in business logic
- Lose some type safety and separation for speed

**But for a production system, keep the three layers.**
