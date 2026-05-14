"""
Completeness Agent - Assesses whether an article provides complete information.
"""

import json
import logging

from . import BaseAgent

logger = logging.getLogger(__name__)
from ..models.issue import Issue
from ..models.article import Article
from ..models.evaluation import CompletenessResult
from ..utils.prompts import AgentPrompts


class CompletenessAgent(BaseAgent):
    """
    Agent that evaluates article completeness.

    Checks for prerequisites, step-by-step instructions, examples,
    troubleshooting guidance, and success criteria.
    """

    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai"):
        super().__init__(client, model, provider)
        self.system_prompt = AgentPrompts.COMPLETENESS_AGENT

    def evaluate(self, issue: Issue, article: Article) -> CompletenessResult:
        """
        Evaluate article completeness.

        Args:
            issue: Parsed customer issue (for context)
            article: Article to evaluate

        Returns:
            CompletenessResult with scores and verdict
        """
        # Handle missing or invalid article
        if not article.is_valid:
            return CompletenessResult(
                completeness_score=0,
                has_prerequisites=False,
                has_step_by_step=False,
                has_examples=False,
                has_troubleshooting=False,
                has_success_criteria=False,
                missing_elements=["Article could not be fetched or is empty"],
                completeness_verdict="severely_lacking"
            )

        user_message = f"""Evaluate the completeness of this article for solving the customer's issue.

## Customer Issue Context
- Product: {issue.product}
- Issue Type: {issue.issue_type}
- Symptoms: {', '.join(issue.symptoms[:5])}

## Article Information
**Title:** {article.title}
**Type:** {article.article_type}
**Has Prerequisites Section:** {bool(article.prerequisites)}
**Number of Steps:** {len(article.steps)}

## Article Content
{article.content[:8000]}

Evaluate completeness and respond with JSON only."""

        try:
            self._refusal_context = {"case_id": getattr(issue, "case_number", ""), "article_url": article.url}
            response = self._call_llm(self.system_prompt, user_message)
            parsed_data = self._parse_json_response(response)

            return CompletenessResult.from_dict(parsed_data)

        except Exception as e:
            # Provide a heuristic-based fallback
            logger.error(
                f"[CompletenessAgent] Evaluation FAILED, using heuristic fallback: {e}",
                exc_info=True
            )
            return self._heuristic_evaluation(article, str(e))

    def _heuristic_evaluation(self, article: Article, error: str) -> CompletenessResult:
        """Provide basic evaluation when LLM call fails."""
        content_lower = article.content.lower()

        has_prerequisites = bool(article.prerequisites) or "prerequisite" in content_lower
        has_step_by_step = bool(article.steps) or any(
            indicator in content_lower
            for indicator in ["step 1", "step 2", "1.", "2.", "first,", "next,"]
        )
        has_examples = any(
            indicator in content_lower
            for indicator in ["example", "for instance", "such as", "```"]
        )
        has_troubleshooting = any(
            indicator in content_lower
            for indicator in ["troubleshoot", "if you", "common issue", "error"]
        )
        has_success_criteria = any(
            indicator in content_lower
            for indicator in ["verify", "confirm", "should see", "successful"]
        )

        # Calculate score based on heuristics
        score = 20  # Base score
        if has_prerequisites:
            score += 15
        if has_step_by_step:
            score += 25
        if has_examples:
            score += 15
        if has_troubleshooting:
            score += 15
        if has_success_criteria:
            score += 10

        # Determine verdict
        if score >= 90:
            verdict = "complete"
        elif score >= 70:
            verdict = "mostly_complete"
        elif score >= 50:
            verdict = "incomplete"
        else:
            verdict = "severely_lacking"

        missing = []
        if not has_prerequisites:
            missing.append("Prerequisites section")
        if not has_step_by_step:
            missing.append("Step-by-step instructions")
        if not has_examples:
            missing.append("Examples or screenshots")
        if not has_troubleshooting:
            missing.append("Troubleshooting guidance")
        if not has_success_criteria:
            missing.append("Success criteria")

        return CompletenessResult(
            completeness_score=score,
            has_prerequisites=has_prerequisites,
            has_step_by_step=has_step_by_step,
            has_examples=has_examples,
            has_troubleshooting=has_troubleshooting,
            has_success_criteria=has_success_criteria,
            missing_elements=missing,
            completeness_verdict=verdict
        )
