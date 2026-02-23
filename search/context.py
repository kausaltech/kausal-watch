from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

index_language: ContextVar[str] = ContextVar('index_language', default='en')

def get_index_language() -> str | None:
    return index_language.get(None)

@contextmanager
def set_index_language(language: str) -> Generator[None]:
    token = index_language.set(language)
    try:
        yield
    finally:
        index_language.reset(token)
