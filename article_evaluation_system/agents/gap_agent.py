"""
Gap Analysis Agent - Identifies documentation gaps and recommends content creation.
"""

import json
import logging

logger = logging.getLogger(__name__)

from . import BaseAgent
from ..models.issue import Issue
from ..models.evaluation import (
    GapAnalysisResult,
    RelevanceResult,
    CompletenessResult,
    ValidityResult
)
from ..utils.prompts import AgentPrompts


class GapAnalysisAgent(BaseAgent):
    """
    Agent that identifies documentation gaps.

    Analyzes what information is missing from available articles
    and recommends what content should be created.
    """

    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai"):
        super().__init__(client, model, provider)
        self.system_prompt = AgentPrompts.GAP_ANALYSIS_AGENT

    def evaluate(
        self,
        issue: Issue,
        relevance_result: RelevanceResult = None,
        completeness_result: CompletenessResult = None,
        validity_result: ValidityResult = None
    ) -> GapAnalysisResult:
        """
        Analyze documentation gaps.

        Args:
            issue: Parsed customer issue
            relevance_result: Results from relevance evaluation
            completeness_result: Results from completeness evaluation
            validity_result: Results from validity evaluation

        Returns:
            GapAnalysisResult with gap analysis and recommendations
        """
        # Build context from evaluation results
        evaluation_context = self._build_evaluation_context(
            relevance_result, completeness_result, validity_result
        )

        user_message = f"""Analyze documentation gaps for this customer issue.

## Customer Issue
**Product:** {issue.product}
**Version:** {issue.version or "Not specified"}
**Issue Type:** {issue.issue_type}
**Error Codes:** {', '.join(issue.error_codes) if issue.error_codes else "None"}
**Symptoms:** {', '.join(issue.symptoms[:5])}

**Original Description:**
{issue.raw_description[:1500]}

## Current Article Evaluation Results
{evaluation_context}

Identify gaps and recommend documentation improvements."""

        try:
            response = self._call_llm(self.system_prompt, user_message)
            parsed_data = self._parse_json_response(response)

            return GapAnalysisResult.from_dict(parsed_data)

        except Exception as e:
            # Generate gap analysis from evaluation results (expected with MWAI plain text responses)
            logger.info(
                f"[GapAnalysisAgent] Using heuristic gap analysis from evaluation results"
            )
            return self._generate_from_evaluations(
                issue, relevance_result, completeness_result, validity_result
            )

    def _build_evaluation_context(
        self,
        relevance: RelevanceResult = None,
        completeness: CompletenessResult = None,
        validity: ValidityResult = None
    ) -> str:
        """Build context string from evaluation results."""
        parts = []

        if relevance:
            parts.append(f"""**Relevance Evaluation:**
- Score: {relevance.relevance_score}/100
- Verdict: {relevance.relevance_verdict}
- Unmatched aspects: {', '.join(relevance.unmatched_aspects) or 'None'}""")

        if completeness:
            parts.append(f"""**Completeness Evaluation:**
- Score: {completeness.completeness_score}/100
- Verdict: {completeness.completeness_verdict}
- Missing elements: {', '.join(completeness.missing_elements) or 'None'}""")

        if validity:
            parts.append(f"""**Validity Evaluation:**
- Score: {validity.validity_score}/100
- Verdict: {validity.validity_verdict}
- Potential issues: {', '.join(validity.potential_issues) or 'None'}""")

        if not parts:
            return "No article evaluation available (no citation provided)"

        return "\n\n".join(parts)

    def _generate_from_evaluations(
        self,
        issue: Issue,
        relevance: RelevanceResult = None,
        completeness: CompletenessResult = None,
        validity: ValidityResult = None
    ) -> GapAnalysisResult:
        """Generate gap analysis from evaluation results when LLM fails."""
        gaps = []
        outline = []
        expertise = []

        # Analyze relevance gaps
        if relevance:
            gaps.extend(relevance.unmatched_aspects)
            if not relevance.product_match:
                gaps.append(f"Documentation for {issue.product} specifically")
            if not relevance.version_match:
                gaps.append(f"Version-specific documentation for {issue.version}")

        # Analyze completeness gaps
        if completeness:
            gaps.extend(completeness.missing_elements)
            if not completeness.has_prerequisites:
                outline.append("Prerequisites and requirements section")
            if not completeness.has_step_by_step:
                outline.append("Clear step-by-step instructions")
            if not completeness.has_examples:
                outline.append("Practical examples and screenshots")
            if not completeness.has_troubleshooting:
                outline.append("Common issues and troubleshooting")
            if not completeness.has_success_criteria:
                outline.append("Success verification steps")

        # Analyze validity gaps
        if validity:
            gaps.extend(validity.potential_issues)
            if not validity.addresses_root_cause:
                gaps.append("Root cause explanation and resolution")
            if not validity.is_current_solution:
                gaps.append("Updated solution using current methods")

        # Determine expertise needed
        expertise.append(f"{issue.product} product expertise")
        if issue.error_codes:
            expertise.append("Error code diagnostic knowledge")

        # Determine priority and effort
        avg_score = sum(filter(None, [
            relevance.relevance_score if relevance else None,
            completeness.completeness_score if completeness else None,
            validity.validity_score if validity else None
        ])) / max(1, sum(1 for x in [relevance, completeness, validity] if x))

        if avg_score < 40:
            priority = "high"
            effort = "large"
            recommendation = "create_new"
        elif avg_score < 60:
            priority = "medium"
            effort = "medium"
            recommendation = "augment_existing"
        else:
            priority = "low"
            effort = "small"
            recommendation = "augment_existing"

        # Add standard outline items if empty
        if not outline:
            outline = [
                "Overview of the issue",
                "Prerequisites and requirements",
                "Step-by-step resolution",
                "Verification steps",
                "Troubleshooting common problems"
            ]

        return GapAnalysisResult(
            documentation_gaps=gaps[:10],
            suggested_content_outline=outline[:10],
            required_expertise=expertise[:5],
            priority=priority,
            estimated_effort=effort,
            recommendation=recommendation
        )
