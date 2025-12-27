"""Configuration management for different environments."""
import os
from pathlib import Path
from dotenv import load_dotenv


_env_loaded = False


def load_env(verbose: bool = False):
    """
    Load environment variables from the appropriate .env file.

    Loads .env.{ENV} if ENV is set, otherwise loads .env.development by default.
    Falls back to .env if the specific file doesn't exist.

    Args:
        verbose: If True, print which config file was loaded
    """
    global _env_loaded

    # Only load once
    if _env_loaded:
        return

    # Determine which environment we're in
    env = os.getenv("ENV", "development")

    # Get the project root directory (where .env files are located)
    project_root = Path(__file__).parent.parent.parent

    # Try to load environment-specific file
    env_file = project_root / f".env.{env}"
    if env_file.exists():
        load_dotenv(env_file)
        if verbose:
            print(f"Loaded configuration from {env_file.name}")
    else:
        # Fallback to generic .env
        fallback_file = project_root / ".env"
        if fallback_file.exists():
            load_dotenv(fallback_file)
            if verbose:
                print(f"Loaded configuration from .env")
        else:
            if verbose:
                print(f"No .env file found, using environment variables and defaults")

    _env_loaded = True


# Load environment on import (silently)
load_env()
