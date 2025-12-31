"""FastAPI application for Mise recipe management."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mise.config import load_env

# Load environment variables
load_env()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    logger.info("Starting Mise API server")
    yield
    logger.info("Shutting down Mise API server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Mise Recipe API",
        description="API for recipe management and ingestion",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Configure from environment
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and include routers
    from mise.api.routes import ingestions, recipes, files, health

    app.include_router(health.router, tags=["health"])
    app.include_router(ingestions.router, prefix="/api/ingestions", tags=["ingestions"])
    app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])
    app.include_router(files.router, prefix="/api/files", tags=["files"])

    return app


app = create_app()
