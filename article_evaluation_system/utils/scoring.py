"""
Scoring utilities for the Agentic Insight Engine.
"""

from ..config.settings import THRESHOLDS, SCORE_WEIGHTS


class ScoringUtils:
    """Utility class for scoring calculations."""

    @staticmethod
    def calculate_overall_score(
        relevance_score: int,
        completeness_score: int,
        validity_score: int,
        weights: dict = None
    ) -> int:
        """
        Calculate weighted overall score.

        Args:
            relevance_score: Score from relevance evaluation (0-100)
            completeness_score: Score from completeness evaluation (0-100)
            validity_score: Score from validity evaluation (0-100)
            weights: Optional custom weights

        Returns:
            Weighted overall score (0-100)
        """
        if weights is None:
            weights = SCORE_WEIGHTS

        score = (
            relevance_score * weights.get("relevance", 0.4) +
            completeness_score * weights.get("completeness", 0.3) +
            validity_score * weights.get("validity", 0.3)
        )
        return round(score)

    @staticmethod
    def get_relevance_verdict(score: int, thresholds: dict = None) -> str:
        """Get relevance verdict from score."""
        if thresholds is None:
            thresholds = THRESHOLDS["relevance"]

        if score >= thresholds["excellent"]:
            return "excellent"
        elif score >= thresholds["good"]:
            return "good"
        elif score >= thresholds["partial"]:
            return "partial"
        elif score >= thresholds["poor"]:
            return "poor"
        else:
            return "irrelevant"

    @staticmethod
    def get_completeness_verdict(score: int, thresholds: dict = None) -> str:
        """Get completeness verdict from score."""
        if thresholds is None:
            thresholds = THRESHOLDS["completeness"]

        if score >= thresholds["complete"]:
            return "complete"
        elif score >= thresholds["mostly_complete"]:
            return "mostly_complete"
        elif score >= thresholds["incomplete"]:
            return "incomplete"
        else:
            return "severely_lacking"

    @staticmethod
    def get_validity_verdict(score: int, thresholds: dict = None) -> str:
        """Get validity verdict from score."""
        if thresholds is None:
            thresholds = THRESHOLDS["validity"]

        if score >= thresholds["valid"]:
            return "valid"
        elif score >= thresholds["likely_valid"]:
            return "likely_valid"
        elif score >= thresholds["uncertain"]:
            return "uncertain"
        else:
            return "likely_invalid"

    @staticmethod
    def get_overall_verdict(
        overall_score: int,
        relevance_verdict: str,
        has_article: bool = True
    ) -> str:
        """
        Determine overall verdict.

        Args:
            overall_score: The weighted overall score
            relevance_verdict: Verdict from relevance evaluation
            has_article: Whether an article was provided

        Returns:
            Overall verdict string
        """
        if not has_article:
            return "no_citation_provided"

        if overall_score >= THRESHOLDS["overall_adequate"]:
            if relevance_verdict in ["excellent", "good"]:
                return "adequate"
            else:
                return "needs_supplementation"
        elif overall_score >= 50:
            return "needs_supplementation"
        else:
            return "inadequate"

    @staticmethod
    def get_action_required(verdict: str, has_better_alternative: bool = False) -> str:
        """
        Determine required action based on verdict.

        Args:
            verdict: Overall verdict
            has_better_alternative: Whether a better article was found

        Returns:
            Action required string
        """
        if verdict == "adequate":
            return "none"
        elif verdict == "needs_supplementation":
            return "add_context" if not has_better_alternative else "find_better_article"
        elif verdict == "no_citation_provided":
            return "find_better_article"
        else:  # inadequate
            return "create_content" if not has_better_alternative else "find_better_article"
