"""Exceptions for recipe ingestion."""


class IngestionError(Exception):
    """Base exception for ingestion errors."""

    def __init__(self, message: str, retryable: bool = False):
        """
        Initialize ingestion error.

        Args:
            message: Error message
            retryable: Whether this error is retryable (e.g., network errors)
        """
        super().__init__(message)
        self.message: str = message
        self.retryable: bool = retryable


class ExtractionError(IngestionError):
    """Error during recipe extraction (AI, parsing, etc.)."""

    def __init__(self, message: str, retryable: bool = True):
        """
        Initialize extraction error.

        Args:
            message: Error message
            retryable: Whether this error is retryable (default: True for AI errors)
        """
        super().__init__(message, retryable)


class SourceFetchError(IngestionError):
    """Error fetching source content (webpage, video, etc.)."""

    def __init__(self, message: str, retryable: bool = True):
        """
        Initialize source fetch error.

        Args:
            message: Error message
            retryable: Whether this error is retryable (default: True for network errors)
        """
        super().__init__(message, retryable)


class DuplicateRecipeError(IngestionError):
    """Recipe already exists from this source."""

    def __init__(self, message: str, existing_recipe_id: int):
        """
        Initialize duplicate recipe error.

        Args:
            message: Error message
            existing_recipe_id: ID of existing recipe
        """
        super().__init__(message, retryable=False)
        self.existing_recipe_id: int = existing_recipe_id


class ValidationError(IngestionError):
    """Error validating extracted recipe data."""

    def __init__(self, message: str):
        """
        Initialize validation error.

        Args:
            message: Error message
        """
        super().__init__(message, retryable=False)
