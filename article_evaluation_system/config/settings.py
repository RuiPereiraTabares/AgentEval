"""
Configuration settings for the Agentic Insight Engine.
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
        "agent_ready": 70,
        "workable": 40,
    },
    "description_quality_reliability": 40  # Below this, evaluation is low-confidence
}

# Support-readiness dimension weights for description quality scoring
SUPPORT_READINESS_WEIGHTS = {
    "product_clarity": 0.40,       # Is the product/service identifiable?
    "symptom_specificity": 0.40,   # Is the symptom/error actionable?
    "operational_context": 0.20,   # Is there enough scope/env context?
}

# Weights for AI response quality composite score
RESPONSE_QUALITY_WEIGHTS = {
    "response_quality": 0.40,   # Accuracy, completeness, clarity, helpfulness
    "groundedness": 0.30,       # Citation grounding (reused from CitationQualityAgent)
    "issue_resolution": 0.30,   # Does the response address the customer's specific issue?
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
    mwai_token: str = ""
    model: str = "gpt-4o"

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
            model=os.environ.get("MWAI_MODEL", "gpt-4o"),
            verbose=os.environ.get("VERBOSE", "").lower() == "true"
        )
