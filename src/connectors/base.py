"""News connector abstract base class."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from src.models.news import NewsItem


class NewsConnector(ABC):
    """Abstract base class for news connectors.

    All connectors must implement the async fetch() method that yields
    NewsItem objects. Items are already sanitized (body = sanitize(raw)).
    """

    @abstractmethod
    async def fetch(self) -> AsyncIterator[NewsItem]:
        """Yield NewsItem objects.

        Items are already sanitized (body = sanitize(raw)).
        """
        ...
