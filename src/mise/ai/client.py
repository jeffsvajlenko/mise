"""Anthropic API client configuration and initialization."""

from anthropic import Anthropic
from mise.config import get_anthropic_api_key, get_ai_model, get_ai_max_tokens


# Module-level client instance (lazy-loaded)
_client: Anthropic | None = None


def get_anthropic_client() -> Anthropic:
    """
    Get or create the Anthropic client instance.

    Returns:
        Anthropic: Configured Anthropic client

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set in environment
    """
    global _client

    if _client is None:
        api_key = get_anthropic_api_key()
        _client = Anthropic(api_key=api_key)

    return _client


def get_default_model() -> str:
    """
    Get the default AI model to use.

    Returns:
        str: Model identifier (default: claude-haiku-4-20250514)
    """
    return get_ai_model()


def get_default_max_tokens() -> int:
    """
    Get the default max tokens for AI requests.

    Returns:
        int: Max tokens (default: 4096)
    """
    return get_ai_max_tokens()
