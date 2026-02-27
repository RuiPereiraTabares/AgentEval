"""
Article data model for Microsoft support articles.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


ArticleType = Literal["troubleshooting", "how-to", "reference", "tutorial", "unknown"]


@dataclass
class Article:
    """Represents a Microsoft support article."""

    url: str
    title: str = ""
    content: str = ""
    last_updated: str | None = None
    applies_to: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    article_type: ArticleType = "unknown"
    fetch_error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "last_updated": self.last_updated,
            "applies_to": self.applies_to,
            "prerequisites": self.prerequisites,
            "steps": self.steps,
            "article_type": self.article_type,
            "fetch_error": self.fetch_error
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Article":
        """Create Article from dictionary."""
        return cls(
            url=data.get("url", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            last_updated=data.get("last_updated"),
            applies_to=data.get("applies_to", []),
            prerequisites=data.get("prerequisites", []),
            steps=data.get("steps", []),
            article_type=data.get("article_type", "unknown"),
            fetch_error=data.get("fetch_error")
        )

    @property
    def is_valid(self) -> bool:
        """Check if article was successfully fetched."""
        return self.fetch_error is None and bool(self.content)

    @property
    def is_microsoft_article(self) -> bool:
        """Check if URL is from Microsoft domains."""
        microsoft_domains = [
            "support.microsoft.com",
            "learn.microsoft.com",
            "docs.microsoft.com",
            "techcommunity.microsoft.com"
        ]
        return any(domain in self.url for domain in microsoft_domains)

    def get_content_summary(self, max_length: int = 500) -> str:
        """Get a truncated summary of the content."""
        if len(self.content) <= max_length:
            return self.content
        return self.content[:max_length] + "..."
