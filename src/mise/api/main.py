"""FastAPI application for Mise recipe management."""

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from mise.config import load_env
from mise.api.auth import verify_api_key

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
        # Add security scheme for Swagger UI
        swagger_ui_init_oauth={
            "usePkceWithAuthorizationCodeGrant": True,
        },
    )

    # Configure CORS (optional - only needed for browser-based clients)
    # For API-only usage, leave API_CORS_ORIGINS empty to disable CORS
    cors_origins = os.getenv("API_CORS_ORIGINS", "")
    if cors_origins:
        allowed_origins = [origin.strip() for origin in cors_origins.split(",")]
        logger.info(f"Enabling CORS for origins: {allowed_origins}")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-API-Key", "Authorization"],
            max_age=3600,  # Cache preflight requests for 1 hour
        )
    else:
        logger.info("CORS disabled - API client mode (most secure)")

    # Import and include routers
    from mise.api.routes import ingestions, recipes, files, health

    # Health endpoint is public (no authentication required)
    app.include_router(health.router, tags=["health"])

    # All other endpoints require API key authentication
    app.include_router(
        ingestions.router,
        prefix="/api/ingestions",
        tags=["ingestions"],
        dependencies=[Depends(verify_api_key)]
    )
    app.include_router(
        recipes.router,
        prefix="/api/recipes",
        tags=["recipes"],
        dependencies=[Depends(verify_api_key)]
    )
    app.include_router(
        files.router,
        prefix="/api/files",
        tags=["files"],
        dependencies=[Depends(verify_api_key)]
    )

    return app


app = create_app()
