"""
Issue data model for parsed customer issues.
"""

from dataclasses import dataclass, field
from typing import Literal


IssueType = Literal["configuration", "error", "how-to", "troubleshooting", "performance", "unknown"]
Severity = Literal["low", "medium", "high", "critical"]


@dataclass
class Issue:
    """Represents a parsed customer issue."""

    product: str
    symptoms: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    issue_type: IssueType = "unknown"
    version: str | None = None
    error_codes: list[str] = field(default_factory=list)
    environment: dict = field(default_factory=dict)
    severity: Severity = "medium"
    raw_description: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "product": self.product,
            "version": self.version,
            "error_codes": self.error_codes,
            "symptoms": self.symptoms,
            "issue_type": self.issue_type,
            "keywords": self.keywords,
            "environment": self.environment,
            "severity": self.severity,
            "raw_description": self.raw_description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Issue":
        """Create Issue from dictionary."""
        return cls(
            product=data.get("product", "Unknown"),
            version=data.get("version"),
            error_codes=data.get("error_codes", []),
            symptoms=data.get("symptoms", []),
            issue_type=data.get("issue_type", "unknown"),
            keywords=data.get("keywords", []),
            environment=data.get("environment", {}),
            severity=data.get("severity", "medium"),
            raw_description=data.get("raw_description", ""),
        )

    def get_search_query(self) -> str:
        """Generate a search query string from issue data."""
        parts = []
        if self.product:
            parts.append(self.product)
        if self.error_codes:
            parts.extend(self.error_codes[:2])
        if self.keywords:
            parts.extend(self.keywords[:3])
        return " ".join(parts)
