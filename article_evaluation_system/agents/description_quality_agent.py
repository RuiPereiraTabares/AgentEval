"""
Description Quality Agent - Evaluates customer issue descriptions using the
support-readiness framework (Product Clarity / Symptom Specificity / Operational Context).
"""

import json
import logging
import re

from . import BaseAgent
from ..models.issue import Issue
from ..models.evaluation import DescriptionQualityResult
from ..utils.prompts import AgentPrompts
from ..config.settings import SUPPORT_READINESS_WEIGHTS


logger = logging.getLogger(__name__)


class DescriptionQualityAgent(BaseAgent):
    """
    Evaluates the quality of a customer's issue description using the
    support-readiness framework (3 dimensions: Product Clarity, Symptom
    Specificity, Operational Context).
    """

    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai"):
        super().__init__(client, model, provider)
        self.system_prompt = AgentPrompts.DESCRIPTION_QUALITY_AGENT

    def evaluate(self, issue: Issue) -> DescriptionQualityResult:
        """
        Evaluate the quality of a customer issue description.

        Args:
            issue: Parsed Issue object (uses raw_description primarily)

        Returns:
            DescriptionQualityResult with per-dimension support-readiness scores
        """
        description = (issue.raw_description or "").strip()

        # Handle empty descriptions
        if not description:
            logger.warning("[DescriptionQualityAgent] Empty description — returning all-zero scores")
            return DescriptionQualityResult(
                product_clarity_score=0,
                symptom_specificity_score=0,
                operational_context_score=0,
                product_clarity_analysis="No description provided",
                symptom_specificity_analysis="No description provided",
                operational_context_analysis="No description provided",
                description_quality_score=0,
                description_quality_verdict="insufficient",
                missing_elements=[
                    "Entire problem description is missing",
                    "No product or service identified",
                    "No symptom or error described",
                    "No operational context provided",
                ],
                improvement_suggestions=[
                    "Provide a description of the customer's issue",
                ],
            )

        # Build context from parsed issue metadata
        context_parts = []
        if issue.product and issue.product != "Unknown":
            context_parts.append(f"Product: {issue.product}")
        if issue.version:
            context_parts.append(f"Version: {issue.version}")
        if issue.error_codes:
            context_parts.append(f"Error codes: {', '.join(issue.error_codes)}")
        if issue.symptoms:
            context_parts.append(f"Symptoms: {', '.join(issue.symptoms[:5])}")
        if issue.environment:
            context_parts.append(f"Environment: {json.dumps(issue.environment)}")

        context_str = "\n".join(context_parts) if context_parts else "No additional metadata available."

        user_message = (
            f"Evaluate the quality of this customer issue description using the "
            f"support-readiness framework.\n\n"
            f"=== CUSTOMER ISSUE DESCRIPTION ===\n{description}\n\n"
            f"=== PARSED METADATA (for additional context) ===\n{context_str}\n\n"
            f"Evaluate each dimension and respond with JSON only."
        )

        try:
            response = self._call_llm(self.system_prompt, user_message)
            parsed_data = self._parse_json_response(response)
            result = DescriptionQualityResult.from_dict(parsed_data)
            # If all dimension scores are 0 the LLM returned an unexpected format — fall back to heuristic
            if not any([result.product_clarity_score, result.symptom_specificity_score,
                        result.operational_context_score]):
                logger.warning(
                    "[DescriptionQualityAgent] All dimension scores are 0 — "
                    "likely format mismatch, using heuristic fallback"
                )
                return self._heuristic_evaluation(description, issue)
            logger.info(
                f"[DescriptionQualityAgent] Result: overall={result.description_quality_score}, "
                f"verdict={result.description_quality_verdict}, "
                f"product_clarity={result.product_clarity_score}, "
                f"symptom_specificity={result.symptom_specificity_score}, "
                f"operational_context={result.operational_context_score}"
            )
            return result
        except Exception as e:
            logger.warning(
                f"[DescriptionQualityAgent] LLM evaluation failed: {e} — using heuristic fallback"
            )
            return self._heuristic_evaluation(description, issue)

    def _heuristic_evaluation(self, description: str, issue: Issue) -> DescriptionQualityResult:
        """
        Fallback heuristic scoring when the LLM call fails.
        Scores each support-readiness dimension via keyword detection.
        """
        desc_lower = description.lower()

        # --- Product/Service Clarity ---
        product_clarity_score = 10  # base: some text exists
        product_clues = []
        # Known Microsoft products/services
        ms_products = [
            "teams", "exchange", "outlook", "sharepoint", "onedrive", "azure",
            "entra", "intune", "defender", "office", "microsoft 365", "m365",
            "windows", "sql", "power bi", "dynamics", "viva", "copilot",
            "power apps", "power automate", "power platform", "fabric",
        ]
        found_products = [p for p in ms_products if p in desc_lower]
        if issue.product and issue.product != "Unknown":
            product_clarity_score += 40
            product_clues.append(f"Product identified: {issue.product}")
        elif found_products:
            product_clarity_score += 30
            product_clues.append(f"Product keywords: {', '.join(found_products[:3])}")
        # Cloud/on-prem identifiers add clarity
        if any(kw in desc_lower for kw in ["online", "cloud", "on-prem", "on premise", "hybrid", "tenant"]):
            product_clarity_score += 10
            product_clues.append("Deployment type mentioned")
        product_clarity_score = min(product_clarity_score, 100)

        # --- Symptom/Error Specificity ---
        symptom_specificity_score = 5  # base
        symptom_clues = []
        if issue.error_codes:
            symptom_specificity_score += 40
            symptom_clues.append(f"Error codes: {', '.join(issue.error_codes)}")
        # Error code patterns: 0x..., HTTP codes, NNNN, letters+digits
        elif re.search(r'\b(0x[0-9a-fA-F]+|[A-Z]{2,}\d{3,}|\d{3,})\b', description):
            symptom_specificity_score += 30
            symptom_clues.append("Error code pattern found")
        if issue.symptoms:
            symptom_specificity_score += 25
            symptom_clues.append("Symptoms described")
        # Specific failure verbs
        specific_verbs = ["fails", "failed", "failing", "crash", "blocked", "cannot", "unable to",
                          "error", "exception", "timeout", "freeze", "hang", "not loading",
                          "not syncing", "not sending", "not receiving", "not working"]
        found_verbs = sum(1 for v in specific_verbs if v in desc_lower)
        if found_verbs:
            symptom_specificity_score += min(found_verbs * 5, 20)
            symptom_clues.append(f"{found_verbs} specific failure verb(s) found")
        symptom_specificity_score = min(symptom_specificity_score, 100)

        # --- Operational Context ---
        operational_context_score = 0
        context_clues = []
        # Scope / user count
        scope_keywords = ["all users", "some users", "many", "several", "everyone",
                          "multiple", "widespread", "isolated", "affecting", "impacted",
                          "percent", "%", "hundreds", "thousands"]
        found_scope = sum(1 for kw in scope_keywords if kw in desc_lower)
        if found_scope:
            operational_context_score += min(found_scope * 10, 30)
            context_clues.append(f"{found_scope} scope keyword(s) found")
        if re.search(r'\b\d{2,}\s*(user|people|employee|account|machine|device)', desc_lower):
            operational_context_score += 20
            context_clues.append("User count pattern found")
        # Timing context
        timing_keywords = ["since", "started", "began", "after", "yesterday", "today",
                           "last week", "last month", "monday", "tuesday", "wednesday",
                           "thursday", "friday", "intermittent", "continuous", "always",
                           "sometimes", "randomly", "recurring"]
        found_timing = sum(1 for kw in timing_keywords if kw in desc_lower)
        if found_timing:
            operational_context_score += min(found_timing * 10, 25)
            context_clues.append(f"{found_timing} timing keyword(s) found")
        if re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', description):
            operational_context_score += 15
            context_clues.append("Date pattern found")
        # Environment context
        if issue.environment:
            operational_context_score += 15
            context_clues.append("Environment metadata present")
        elif any(kw in desc_lower for kw in ["region", "server", "tenant", "environment", "browser",
                                              "desktop", "mobile", "on-prem", "cloud"]):
            operational_context_score += 10
            context_clues.append("Environment keywords found")
        operational_context_score = min(operational_context_score, 100)

        # Overall weighted score
        overall = round(
            product_clarity_score * SUPPORT_READINESS_WEIGHTS["product_clarity"]
            + symptom_specificity_score * SUPPORT_READINESS_WEIGHTS["symptom_specificity"]
            + operational_context_score * SUPPORT_READINESS_WEIGHTS["operational_context"]
        )

        # Derive verdict
        if overall >= 70:
            verdict = "agent_ready"
        elif overall >= 40:
            verdict = "workable"
        else:
            verdict = "insufficient"

        # Collect missing elements
        missing = []
        if product_clarity_score < 40:
            missing.append("Specific Microsoft product or service name")
        if symptom_specificity_score < 40:
            missing.append("Specific error message, code, or failure description")
        if operational_context_score < 40:
            missing.append("Operational context — scope, environment, or timing")

        suggestions = []
        if product_clarity_score < 60:
            suggestions.append("Name the specific Microsoft product or service affected")
        if symptom_specificity_score < 60:
            suggestions.append("Include error codes, messages, or describe exactly what fails")
        if operational_context_score < 60:
            suggestions.append("Add context: how many users affected, environment, and when it started")

        logger.info(
            f"[DescriptionQualityAgent] Heuristic result: overall={overall}, "
            f"verdict={verdict}, product_clarity={product_clarity_score}, "
            f"symptom_specificity={symptom_specificity_score}, "
            f"operational_context={operational_context_score}"
        )

        return DescriptionQualityResult(
            product_clarity_score=product_clarity_score,
            symptom_specificity_score=symptom_specificity_score,
            operational_context_score=operational_context_score,
            product_clarity_analysis="; ".join(product_clues) if product_clues else "No product clarity clues found (heuristic)",
            symptom_specificity_analysis="; ".join(symptom_clues) if symptom_clues else "No symptom specificity clues found (heuristic)",
            operational_context_analysis="; ".join(context_clues) if context_clues else "No operational context clues found (heuristic)",
            description_quality_score=overall,
            description_quality_verdict=verdict,
            missing_elements=missing,
            improvement_suggestions=suggestions,
        )
