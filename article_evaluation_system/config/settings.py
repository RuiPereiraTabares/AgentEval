"""
Configuration settings for the article evaluation system.
"""

import os
from dataclasses import dataclass, field


# Scoring thresholds for verdict determination
THRESHOLDS = {
    "relevance": {
        "excellent": 85,
        "good": 70,
        "partial": 50,
        "poor": 30
    },
    "completeness": {
        "complete": 90,
        "mostly_complete": 70,
        "incomplete": 50
    },
    "validity": {
        "valid": 80,
        "likely_valid": 60,
        "uncertain": 40
    },
    "overall_adequate": 70,  # Minimum score to consider article adequate
    "description_quality": {
        "well_defined": 80,
        "mostly_defined": 60,
        "partially_defined": 40
    },
    "description_quality_reliability": 40  # Below this, evaluation is low-confidence
}

# Thresholds for transfer reason classification (decision tree)
TRANSFER_CLASSIFICATION_THRESHOLDS = {
    "poor_description_ceiling": 40,         # Below this → description is the root cause
    "bad_citation_relevance_ceiling": 50,    # Below this → citation match is poor
    "inadequate_article_overall_ceiling": 60, # Below this → article doesn't solve it
}

# Kepner-Tregoe dimension weights for description quality scoring
KT_DIMENSION_WEIGHTS = {
    "identity": 0.35,   # WHAT — most critical for article matching
    "location": 0.25,   # WHERE
    "timing": 0.20,     # WHEN
    "magnitude": 0.20   # EXTENT
}

# Weights for overall score calculation
SCORE_WEIGHTS = {
    "relevance": 0.40,
    "completeness": 0.30,
    "validity": 0.30
}


@dataclass
class Settings:
    """Application settings."""

    # API Configuration
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    model: str = "claude-sonnet-4-20250514"

    # Rate Limiting
    requests_per_minute: int = 50
    article_fetch_delay: float = 0.5  # seconds between article fetches

    # Caching
    cache_enabled: bool = True
    cache_ttl: int = 3600  # seconds

    # Scoring
    thresholds: dict = field(default_factory=lambda: THRESHOLDS.copy())
    score_weights: dict = field(default_factory=lambda: SCORE_WEIGHTS.copy())

    # Search Configuration
    max_search_results: int = 5
    search_domains: list[str] = field(default_factory=lambda: [
        "support.microsoft.com",
        "learn.microsoft.com"
    ])

    # Output
    output_format: str = "json"  # "json" or "csv"
    verbose: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            verbose=os.environ.get("VERBOSE", "").lower() == "true"
        )
