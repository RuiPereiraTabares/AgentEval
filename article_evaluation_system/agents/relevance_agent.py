"""
Article Relevance Agent - Evaluates how well an article matches a customer issue.
"""

import json
import logging

from . import BaseAgent

logger = logging.getLogger(__name__)
from ..models.issue import Issue
from ..models.article import Article
from ..models.evaluation import RelevanceResult
from ..utils.prompts import AgentPrompts


class RelevanceAgent(BaseAgent):
    """
    Agent that evaluates article relevance to customer issues.

    Scores how well an article matches the customer's specific problem,
    considering product, version, error codes, and symptoms.
    """

    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai"):
        super().__init__(client, model, provider)
        self.system_prompt = AgentPrompts.RELEVANCE_AGENT

    def evaluate(self, issue: Issue, article: Article) -> RelevanceResult:
        """
        Evaluate article relevance to an issue.

        Args:
            issue: Parsed customer issue
            article: Article to evaluate

        Returns:
            RelevanceResult with scores and verdict
        """
        # Handle missing or invalid article
        if not article.is_valid:
            return RelevanceResult(
                relevance_score=0,
                matched_aspects=[],
                unmatched_aspects=["Article could not be fetched or is empty"],
                version_match=False,
                product_match=False,
                is_outdated=False,
                relevance_verdict="irrelevant"
            )

        user_message = f"""Evaluate the relevance of this article to the customer issue.

## Customer Issue (Parsed)
```json
{json.dumps(issue.to_dict(), indent=2)}
```

## Article Information
**Title:** {article.title}
**URL:** {article.url}
**Last Updated:** {article.last_updated or "Unknown"}
**Applies To:** {', '.join(article.applies_to) if article.applies_to else "Not specified"}

## Article Content
{article.content[:8000]}

Evaluate and respond with JSON only."""

        try:
            self._refusal_context = {"case_id": getattr(issue, "case_id", ""), "article_url": article.url}
            response = self._call_llm(self.system_prompt, user_message)
            parsed_data = self._parse_json_response(response)

            return RelevanceResult.from_dict(parsed_data)

        except Exception as e:
            # Return a default low-score result on failure
            logger.error(
                f"[RelevanceAgent] Evaluation FAILED, returning fallback score=30: {e}",
                exc_info=True
            )
            return RelevanceResult(
                relevance_score=30,
                matched_aspects=[],
                unmatched_aspects=["Evaluation failed: " + str(e)],
                version_match=True,
                product_match=self._quick_product_check(issue, article),
                is_outdated=False,
                relevance_verdict="poor"
            )

    def _quick_product_check(self, issue: Issue, article: Article) -> bool:
        """Quick check if article mentions the same product."""
        if not issue.product:
            return True

        product_lower = issue.product.lower()
        content_lower = article.content.lower()
        title_lower = article.title.lower()

        return product_lower in content_lower or product_lower in title_lower
