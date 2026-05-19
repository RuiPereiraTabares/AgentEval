"""
Article Relevance Agent - Evaluates how well an article matches a customer issue.
"""

import json
import logging

from . import BaseAgent, LLMRefusalError
from ..utils.content_sanitizer import sanitize_for_rai

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
{sanitize_for_rai(article.content[:8000])}

Evaluate and respond with JSON only."""

        try:
            self._refusal_context = {
                "case_id": getattr(issue, "case_number", ""),
                "article_url": article.url,
                "article_title": article.title or "",
            }
            response = self._call_llm(self.system_prompt, user_message)
            parsed_data = self._parse_json_response(response)

            return RelevanceResult.from_dict(parsed_data)

        except LLMRefusalError as e:
            logger.warning(
                f"[RelevanceAgent] RAI refusal exhausted — using keyword heuristic fallback: {e}"
            )
            return self._heuristic_relevance(issue, article)

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

    def _heuristic_relevance(self, issue: Issue, article: Article) -> RelevanceResult:
        """
        Keyword-overlap heuristic used when the LLM refuses to evaluate.

        Builds a term set from the issue and measures overlap against the article,
        producing a score and verdict that is more meaningful than the hardcoded
        score=30 fallback.
        """
        # Build issue term set
        issue_terms: set[str] = set()
        if issue.product:
            issue_terms.add(issue.product.lower())
        for kw in (issue.keywords or []):
            issue_terms.add(kw.lower())
        for symptom in (issue.symptoms or []):
            issue_terms.update(w.lower() for w in symptom.split() if len(w) > 3)

        article_text = (
            (article.title or "") + " " + (article.content or "")[:3000]
        ).lower()

        matched = [t for t in issue_terms if t in article_text]
        unmatched = [t for t in issue_terms if t not in article_text]

        overlap_ratio = len(matched) / len(issue_terms) if issue_terms else 0.0

        if overlap_ratio >= 0.6:
            score, verdict = 70, "good"
        elif overlap_ratio >= 0.35:
            score, verdict = 55, "acceptable"
        elif overlap_ratio >= 0.15:
            score, verdict = 40, "poor"
        else:
            score, verdict = 20, "irrelevant"

        product_match = self._quick_product_check(issue, article)

        return RelevanceResult(
            relevance_score=score,
            matched_aspects=matched[:5],
            unmatched_aspects=(unmatched[:5] or []) + ["LLM evaluation unavailable (RAI refusal)"],
            version_match=True,
            product_match=product_match,
            is_outdated=False,
            relevance_verdict=verdict,
            relevance_fallback=True,
        )
