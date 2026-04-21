"""
Description Quality Agent - Evaluates customer issue descriptions using the
Kepner-Tregoe (KT) Problem Statement framework.
"""

import json
import logging
import re

from . import BaseAgent
from ..models.issue import Issue
from ..models.evaluation import DescriptionQualityResult
from ..utils.prompts import AgentPrompts
from ..config.settings import KT_DIMENSION_WEIGHTS


logger = logging.getLogger(__name__)


class DescriptionQualityAgent(BaseAgent):
    """
    Evaluates the quality of a customer's issue description using the
    Kepner-Tregoe Problem Statement framework (Identity, Location, Timing, Magnitude).
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
            DescriptionQualityResult with per-dimension KT scores
        """
        description = (issue.raw_description or "").strip()

        # Handle empty descriptions
        if not description:
            logger.warning("[DescriptionQualityAgent] Empty description — returning all-zero scores")
            return DescriptionQualityResult(
                identity_score=0,
                location_score=0,
                timing_score=0,
                magnitude_score=0,
                identity_analysis="No description provided",
                location_analysis="No description provided",
                timing_analysis="No description provided",
                magnitude_analysis="No description provided",
                description_quality_score=0,
                description_quality_verdict="poorly_defined",
                missing_kt_elements=[
                    "Entire problem description is missing",
                    "No identity (WHAT) information",
                    "No location (WHERE) information",
                    "No timing (WHEN) information",
                    "No magnitude (EXTENT) information",
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
            f"Kepner-Tregoe Problem Statement framework.\n\n"
            f"=== CUSTOMER ISSUE DESCRIPTION ===\n{description}\n\n"
            f"=== PARSED METADATA (for additional context) ===\n{context_str}\n\n"
            f"Evaluate each KT dimension and respond with JSON only."
        )

        try:
            response = self._call_llm(self.system_prompt, user_message)
            parsed_data = self._parse_json_response(response)
            result = DescriptionQualityResult.from_dict(parsed_data)
            # If all dimension scores are 0 the LLM returned an unexpected format
            # (e.g. wrapped in KT_Dimensions_Evaluation) — fall back to heuristic
            if not any([result.identity_score, result.location_score,
                        result.timing_score, result.magnitude_score]):
                logger.warning(
                    "[DescriptionQualityAgent] All dimension scores are 0 — "
                    "likely format mismatch, using heuristic fallback"
                )
                return self._heuristic_evaluation(description, issue)
            logger.info(
                f"[DescriptionQualityAgent] Result: overall={result.description_quality_score}, "
                f"verdict={result.description_quality_verdict}, "
                f"identity={result.identity_score}, location={result.location_score}, "
                f"timing={result.timing_score}, magnitude={result.magnitude_score}"
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
        Scores each KT dimension via keyword detection.
        """
        desc_lower = description.lower()

        # --- Identity (WHAT) ---
        identity_score = 10  # base: some text exists
        identity_clues = []
        if issue.product and issue.product != "Unknown":
            identity_score += 25
            identity_clues.append(f"Product: {issue.product}")
        if issue.error_codes:
            identity_score += 25
            identity_clues.append(f"Error codes: {', '.join(issue.error_codes)}")
        if issue.symptoms:
            identity_score += 20
            identity_clues.append("Symptoms described")
        if any(kw in desc_lower for kw in ["error", "fail", "crash", "cannot", "unable", "broken", "issue"]):
            identity_score += 10
            identity_clues.append("Problem keywords present")
        identity_score = min(identity_score, 100)

        # --- Location (WHERE) ---
        location_score = 0
        location_clues = []
        location_keywords = [
            "server", "region", "tenant", "site", "url", "http", "page",
            "module", "portal", "admin center", "console", "client",
            "desktop", "mobile", "browser", "web", "on-prem", "cloud",
            "azure", "environment",
        ]
        found_location = sum(1 for kw in location_keywords if kw in desc_lower)
        if found_location:
            location_score = min(20 + found_location * 15, 85)
            location_clues.append(f"{found_location} location keyword(s) found")
        if issue.environment:
            location_score = min(location_score + 20, 90)
            location_clues.append("Environment metadata present")

        # --- Timing (WHEN) ---
        timing_score = 0
        timing_clues = []
        timing_keywords = [
            "since", "started", "began", "after", "yesterday", "today",
            "last week", "last month", "monday", "tuesday", "wednesday",
            "thursday", "friday", "saturday", "sunday", "january", "february",
            "march", "april", "may", "june", "july", "august", "september",
            "october", "november", "december", "intermittent", "continuous",
            "always", "sometimes", "randomly", "every time", "once",
            "recurring", "pattern",
        ]
        found_timing = sum(1 for kw in timing_keywords if kw in desc_lower)
        if found_timing:
            timing_score = min(20 + found_timing * 15, 85)
            timing_clues.append(f"{found_timing} timing keyword(s) found")
        # Check for date patterns (YYYY-MM-DD, MM/DD/YYYY, etc.)
        if re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', description):
            timing_score = min(timing_score + 25, 90)
            timing_clues.append("Date pattern found")

        # --- Magnitude (EXTENT) ---
        magnitude_score = 0
        magnitude_clues = []
        magnitude_keywords = [
            "all users", "some users", "many", "several", "few",
            "everyone", "nobody", "multiple", "widespread", "isolated",
            "growing", "increasing", "declining", "stable", "affecting",
            "impacted", "percent", "%", "hundreds", "thousands",
        ]
        found_magnitude = sum(1 for kw in magnitude_keywords if kw in desc_lower)
        if found_magnitude:
            magnitude_score = min(20 + found_magnitude * 15, 85)
            magnitude_clues.append(f"{found_magnitude} magnitude keyword(s) found")
        # Check for numbers that suggest user counts
        if re.search(r'\b\d{2,}\s*(user|people|employee|account|machine|device)', desc_lower):
            magnitude_score = min(magnitude_score + 25, 90)
            magnitude_clues.append("User count pattern found")

        # Overall weighted score
        overall = round(
            identity_score * KT_DIMENSION_WEIGHTS["identity"]
            + location_score * KT_DIMENSION_WEIGHTS["location"]
            + timing_score * KT_DIMENSION_WEIGHTS["timing"]
            + magnitude_score * KT_DIMENSION_WEIGHTS["magnitude"]
        )

        # Derive verdict
        if overall >= 80:
            verdict = "well_defined"
        elif overall >= 60:
            verdict = "mostly_defined"
        elif overall >= 40:
            verdict = "partially_defined"
        else:
            verdict = "poorly_defined"

        # Collect missing elements
        missing = []
        if identity_score < 40:
            missing.append("Specific product/feature identification (WHAT)")
        if location_score < 40:
            missing.append("Environment or location details (WHERE)")
        if timing_score < 40:
            missing.append("Timing information — when it started or pattern (WHEN)")
        if magnitude_score < 40:
            missing.append("Scope/magnitude — how many affected (EXTENT)")

        suggestions = []
        if identity_score < 60:
            suggestions.append("Include the specific product, feature, and any error codes")
        if location_score < 60:
            suggestions.append("Specify the environment (cloud/on-prem, region, URL)")
        if timing_score < 60:
            suggestions.append("Note when the issue started and whether it is continuous or intermittent")
        if magnitude_score < 60:
            suggestions.append("Quantify how many users/systems are affected and the trend")

        logger.info(
            f"[DescriptionQualityAgent] Heuristic result: overall={overall}, "
            f"verdict={verdict}, identity={identity_score}, location={location_score}, "
            f"timing={timing_score}, magnitude={magnitude_score}"
        )

        return DescriptionQualityResult(
            identity_score=identity_score,
            location_score=location_score,
            timing_score=timing_score,
            magnitude_score=magnitude_score,
            identity_analysis="; ".join(identity_clues) if identity_clues else "No identity clues found (heuristic)",
            location_analysis="; ".join(location_clues) if location_clues else "No location clues found (heuristic)",
            timing_analysis="; ".join(timing_clues) if timing_clues else "No timing clues found (heuristic)",
            magnitude_analysis="; ".join(magnitude_clues) if magnitude_clues else "No magnitude clues found (heuristic)",
            description_quality_score=overall,
            description_quality_verdict=verdict,
            missing_kt_elements=missing,
            improvement_suggestions=suggestions,
        )
