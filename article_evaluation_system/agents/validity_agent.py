"""
Solution Validity Agent - Determines if an article's solution would actually work.
"""

import json
import logging

from . import BaseAgent

logger = logging.getLogger(__name__)
from ..models.issue import Issue
from ..models.article import Article
from ..models.evaluation import ValidityResult
from ..utils.prompts import AgentPrompts


class ValidityAgent(BaseAgent):
    """
    Agent that evaluates solution validity.

    Determines if the proposed solution addresses the root cause,
    is current (not deprecated), and would work in the customer's environment.
    """

    def __init__(self, client, model: str = "gpt-4o", provider: str = "openai"):
        super().__init__(client, model, provider)
        self.system_prompt = AgentPrompts.VALIDITY_AGENT

    def evaluate(self, issue: Issue, article: Article) -> ValidityResult:
        """
        Evaluate solution validity.

        Args:
            issue: Parsed customer issue
            article: Article containing the proposed solution

        Returns:
            ValidityResult with scores and verdict
        """
        # Handle missing or invalid article
        if not article.is_valid:
            return ValidityResult(
                validity_score=0,
                addresses_root_cause=False,
                is_current_solution=False,
                environment_compatible=False,
                potential_issues=["Article could not be fetched or is empty"],
                confidence_level="low",
                validity_verdict="invalid"
            )

        user_message = f"""Evaluate whether this article's solution would actually solve the customer's problem.

## Customer Issue
**Product:** {issue.product}
**Version:** {issue.version or "Not specified"}
**Issue Type:** {issue.issue_type}
**Error Codes:** {', '.join(issue.error_codes) if issue.error_codes else "None"}
**Symptoms:** {', '.join(issue.symptoms[:5])}
**Environment:** {json.dumps(issue.environment) if issue.environment else "Not specified"}

**Original Description:**
{issue.raw_description[:1000]}

## Article Solution
**Title:** {article.title}
**Last Updated:** {article.last_updated or "Unknown"}

**Content:**
{article.content[:8000]}

Evaluate validity and respond with JSON only."""

        try:
            response = self._call_claude(self.system_prompt, user_message)
            parsed_data = self._parse_json_response(response)

            return ValidityResult.from_dict(parsed_data)

        except Exception as e:
            # Return uncertain result on failure
            logger.error(
                f"[ValidityAgent] Evaluation FAILED, returning fallback score=50: {e}",
                exc_info=True
            )
            return ValidityResult(
                validity_score=50,
                addresses_root_cause=False,
                is_current_solution=True,
                environment_compatible=True,
                potential_issues=["Validity evaluation failed: " + str(e)],
                confidence_level="low",
                validity_verdict="uncertain"
            )
