"""Dependency injection for FastAPI endpoints."""

from typing import Generator
from mise.db.unit_of_work import UnitOfWork


def get_uow() -> Generator[UnitOfWork, None, None]:
    """
    Dependency that provides a Unit of Work instance.

    Yields:
        UnitOfWork: Database unit of work
    """
    with UnitOfWork() as uow:
        yield uow
