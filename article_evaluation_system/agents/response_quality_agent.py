"""
Response Quality Agent - Evaluates AI response quality across multiple dimensions:
Response Quality, Groundedness (reused from CitationQualityAgent), and Issue Resolution.
"""

import json
import logging

from . import BaseAgent
from ..models.issue import Issue
from ..models.evaluation import CitationQualityResult, ResponseQualityResult
from ..utils.prompts import AgentPrompts


logger = logging.getLogger(__name__)


class ResponseQualityAgent(BaseAgent):
    """
    Evaluates the quality of an AI-generated customer support response
    across three dimensions with a single LLM call (Response Quality +
    Issue Resolution), reusing groundedness from CitationQualityAgent.
    """

    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai"):
        super().__init__(client, model, provider)
        self.system_prompt = AgentPrompts.RESPONSE_QUALITY_AGENT

    def evaluate(
        self,
        issue: Issue,
        ai_response: str,
        citation_quality_result: CitationQualityResult,
    ) -> ResponseQualityResult:
        """
        Evaluate AI response quality.

        Args:
            issue: Parsed Issue object
            ai_response: The AI-generated response text
            citation_quality_result: Result from CitationQualityAgent (groundedness reused)

        Returns:
            ResponseQualityResult with per-dimension scores and weighted overall
        """
        # Extract groundedness from citation quality (no LLM call)
        groundedness_score = citation_quality_result.overall_grounding_score
        groundedness_analysis = (
            f"{citation_quality_result.overall_verdict}: "
            f"{citation_quality_result.citations_good} good, "
            f"{citation_quality_result.citations_partial} partial, "
            f"{citation_quality_result.citations_bad} bad out of "
            f"{citation_quality_result.citations_total} citations. "
            f"Cited: {citation_quality_result.cited_percentage:.0f}%, "
            f"Uncited: {citation_quality_result.uncited_percentage:.0f}%"
        )

        # Handle empty AI response
        if not (ai_response or "").strip():
            logger.warning("[ResponseQualityAgent] Empty AI response — returning groundedness-only score")
            return ResponseQualityResult(
                groundedness_score=groundedness_score,
                groundedness_analysis=groundedness_analysis,
                ai_response_quality_score=round(groundedness_score * 0.30),
                ai_response_quality_verdict="poor",
                quality_weaknesses=["No AI response provided"],
                improvement_suggestions=["Provide an AI-generated response to evaluate"],
            )

        # Build user message for LLM
        description = (issue.raw_description or "").strip()
        user_message = (
            f"=== CUSTOMER ISSUE ===\n{description[:3000]}\n\n"
            f"=== AI RESPONSE ===\n{ai_response[:5000]}\n\n"
            f"Evaluate the response quality and issue resolution. Respond with JSON only."
        )

        try:
            response = self._call_llm(self.system_prompt, user_message)
            parsed_data = self._parse_json_response(response)
            result = ResponseQualityResult.from_dict(
                parsed_data,
                groundedness_score=groundedness_score,
                groundedness_analysis=groundedness_analysis,
            )
            logger.info(
                f"[ResponseQualityAgent] Result: overall={result.ai_response_quality_score}, "
                f"verdict={result.ai_response_quality_verdict}, "
                f"response_quality={result.response_quality_score}, "
                f"groundedness={result.groundedness_score}, "
                f"issue_resolution={result.issue_resolution_score}"
            )
            return result
        except Exception as e:
            logger.warning(
                f"[ResponseQualityAgent] LLM evaluation failed: {e} — returning groundedness-only fallback"
            )
            # Fallback: return groundedness-only score
            from ..config.settings import RESPONSE_QUALITY_WEIGHTS
            fallback_overall = round(groundedness_score * RESPONSE_QUALITY_WEIGHTS["groundedness"])
            return ResponseQualityResult(
                groundedness_score=groundedness_score,
                groundedness_analysis=groundedness_analysis,
                ai_response_quality_score=fallback_overall,
                ai_response_quality_verdict="poor" if fallback_overall < 40 else "fair",
                quality_weaknesses=[f"LLM evaluation failed: {e}"],
                improvement_suggestions=["Retry evaluation"],
            )
