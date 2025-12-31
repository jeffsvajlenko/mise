"""API key authentication middleware."""

import os
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

# API key header configuration
# The scheme_name shows up in Swagger UI as the security scheme name
API_KEY_HEADER = APIKeyHeader(
    name="X-API-Key",
    scheme_name="API Key",
    description="Enter your API key (generate with: openssl rand -hex 32)",
    auto_error=False
)


def get_api_keys() -> list[str]:
    """
    Get valid API keys from environment variable.

    Returns:
        List of valid API keys. Returns empty list if not configured.
    """
    api_keys_str = os.getenv("API_KEYS", "")
    if not api_keys_str:
        return []

    # Support comma-separated list of keys for multiple family members
    return [key.strip() for key in api_keys_str.split(",") if key.strip()]


async def verify_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    """
    Verify the API key from the request header.

    Args:
        api_key: The API key from the X-API-Key header

    Returns:
        The validated API key

    Raises:
        HTTPException: If API key is missing or invalid
    """
    valid_keys = get_api_keys()

    # If no API keys configured, allow all requests (development mode)
    if not valid_keys:
        return "development"

    # Check if API key is provided
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Please provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Validate API key
    if api_key not in valid_keys:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key
