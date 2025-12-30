"""Pytest configuration and fixtures for testing."""
import os
import pytest
from pathlib import Path
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import Session

from mise.db.database import Base
from mise.db.unit_of_work import UnitOfWork


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Configure environment for testing.

    Sets DATABASE_URL to point to test database so all code uses the test DB.
    This runs automatically before all tests.
    """
    test_db_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://mise_user:mise_password@localhost:5432/mise_test"
    )
    # Override DATABASE_URL for the entire test session
    os.environ["DATABASE_URL"] = test_db_url

    # Recreate engine with test database URL
    # This is necessary because mise.db.database creates the engine at import time
    import mise.db.database
    mise.db.database.engine = create_engine(
        test_db_url,
        echo=False,  # Disable echo in tests
        pool_pre_ping=True
    )

    yield


@pytest.fixture(scope="session")
def test_db_url(setup_test_environment):
    """
    Get test database URL from environment.

    Returns the TEST_DATABASE_URL that was set by setup_test_environment.
    """
    return os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
def test_engine(test_db_url):
    """
    Create test database engine.

    This is session-scoped to reuse the same engine across all tests.
    """
    engine = create_engine(
        test_db_url,
        echo=False,  # Disable SQL logging in tests
        pool_pre_ping=True
    )
    return engine


@pytest.fixture(scope="session")
def setup_test_database(test_engine):
    """
    Create all tables in test database.

    Runs once at the start of the test session.
    Drops all tables at the end of the session.
    """
    # Create all tables
    Base.metadata.create_all(test_engine)

    yield

    # Drop all tables after tests
    Base.metadata.drop_all(test_engine)


@pytest.fixture(scope="function", autouse=True)
def clean_database(setup_test_database):
    """
    Truncate all tables before each test to ensure isolation.

    Runs automatically for all tests to provide a clean database state.
    Uses the same engine as the application code to ensure consistency.
    """
    # Import here to get the engine after it's been reconfigured
    from mise.db.database import engine
    import logging
    logger = logging.getLogger(__name__)

    # Before test: truncate all tables
    with engine.begin() as connection:
        # Truncate in reverse order of dependencies to handle foreign keys
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))

    yield
    # No cleanup after - will be cleaned before next test


@pytest.fixture
def db_session(test_engine, setup_test_database):
    """
    Provide a clean database session for each test.

    Uses nested transactions to ensure test isolation:
    - Each test starts with a clean slate
    - Changes are rolled back after each test
    - No test data persists between tests

    Usage:
        def test_something(db_session):
            recipe = RecipeDbModel(data={...})
            db_session.add(recipe)
            db_session.commit()
            # Data is automatically rolled back after test
    """
    # Start a connection and transaction
    connection = test_engine.connect()
    transaction = connection.begin()

    # Create session bound to the connection
    session = Session(bind=connection)

    # Use nested transaction for test isolation
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        """Automatically restart savepoint after commit/rollback."""
        if transaction.nested and not transaction._parent.nested:
            session.begin_nested()

    yield session

    # Cleanup
    session.close()
    # Only rollback if transaction is still active (not already deassociated)
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def uow(test_engine, setup_test_database):
    """
    Provide a Unit of Work for testing.

    Similar to db_session but uses the UnitOfWork pattern.
    Automatically rolls back after each test.

    Usage:
        def test_with_uow(uow):
            recipe = uow.recipes.create(recipe_data)
            # Data is automatically rolled back after test
    """
    # Start a connection and transaction
    connection = test_engine.connect()
    transaction = connection.begin()

    # Create UnitOfWork with test session
    session = Session(bind=connection)
    uow_instance = UnitOfWork.__new__(UnitOfWork)
    uow_instance.session = session
    uow_instance._recipes = None
    uow_instance._ingestions = None

    yield uow_instance

    # Cleanup
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def temp_file_storage(tmp_path):
    """
    Provide a temporary file storage for testing.

    Creates a temporary directory that is cleaned up after the test.

    Usage:
        def test_file_storage(temp_file_storage):
            storage = temp_file_storage
            metadata = storage.save_recipe_file(...)
    """
    from mise.storage.files import FileStorage

    storage_path = tmp_path / "test_files"
    storage = FileStorage(storage_path)

    yield storage

    # Cleanup is automatic with tmp_path


@pytest.fixture
def sample_recipe():
    """
    Provide a sample Recipe for testing.

    Returns a valid Recipe domain object that can be used in tests.
    """
    from mise.schema.recipe import Recipe, Ingredient, RecipeStep, Tag

    return Recipe(
        title="Test Recipe",
        description="A recipe for testing",
        prep_time=10,
        cook_time=20,
        servings=4,
        ingredients=[
            Ingredient(
                text="200g flour",
                name="flour",
                quantity=200.0,
                unit="g"
            ),
            Ingredient(
                text="100ml water",
                name="water",
                quantity=100.0,
                unit="ml"
            )
        ],
        steps=[
            RecipeStep(instruction="Mix flour and water"),
            RecipeStep(instruction="Bake at 180°C")
        ],
        tags=[
            Tag(key="difficulty", value="easy"),
            Tag(key="meal_type", value="dinner")
        ]
    )


@pytest.fixture
def sample_recipe_db_model(sample_recipe):
    """
    Provide a sample RecipeDbModel for testing.

    Returns a RecipeDbModel ready to be inserted into the database.
    """
    from mise.db.models import RecipeDbModel

    return RecipeDbModel(
        data=sample_recipe.model_dump(mode='json')
    )


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require database)"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests (no external dependencies)"
    )
