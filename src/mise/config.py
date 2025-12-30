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
                print("Loaded configuration from .env")
        else:
            if verbose:
                print("No .env file found, using environment variables and defaults")

    _env_loaded = True


# Load environment on import (silently)
load_env()


# AI Configuration
def get_anthropic_api_key() -> str:
    """Get Anthropic API key from environment."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not found in environment. "
            "Please set it in your .env file or environment variables."
        )
    return api_key


def get_ai_model() -> str:
    """Get AI model name from environment."""
    return os.getenv("AI_MODEL", "claude-haiku-4-20250514")


def get_ai_max_tokens() -> int:
    """Get AI max tokens from environment."""
    max_tokens = os.getenv("AI_MAX_TOKENS", "4096")
    try:
        return int(max_tokens)
    except ValueError:
        return 4096
