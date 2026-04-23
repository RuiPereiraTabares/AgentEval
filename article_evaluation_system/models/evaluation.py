"""
Evaluation result data models.
"""

from dataclasses import dataclass, field
from typing import Literal


import logging

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers for normalizing unpredictable LLM JSON responses
# ---------------------------------------------------------------------------

# Maps qualitative labels to numeric scores (0-100).
# Exhaustive to handle any label variant the LLM might produce.
_RELEVANCE_LABEL_MAP = {
    # High tier (90-100)
    "excellent": 95, "perfect": 95, "exact match": 95, "exact": 95,
    "very high": 90, "directly relevant": 90, "highly relevant": 90,
    # Good tier (70-89)
    "high": 85, "strong": 85, "good": 75, "relevant": 75,
    "mostly relevant": 75, "mostly_relevant": 75, "above average": 75,
    # Partial tier (50-69)
    "medium": 55, "moderate": 55, "average": 55, "fair": 55,
    "partial": 45, "partially relevant": 45, "partially_relevant": 45,
    "somewhat relevant": 45, "somewhat": 45, "mixed": 45,
    # Poor tier (20-49)
    "low": 25, "poor": 20, "weak": 20, "below average": 25,
    "marginally relevant": 25, "marginal": 25, "tangential": 25,
    "tangentially related": 25, "minimal": 20, "limited": 25,
    # Irrelevant tier (0-19)
    "very low": 10, "irrelevant": 5, "not relevant": 5,
    "not_relevant": 5, "unrelated": 5, "none": 0, "no": 5, "n/a": 0,
    # Boolean-like
    "true": 85, "false": 10, "yes": 85, "no match": 5,
}

_COMPLETENESS_LABEL_MAP = {
    # Complete tier (90-100)
    "complete": 95, "fully complete": 95, "fully_complete": 95,
    "comprehensive": 95, "excellent": 95, "perfect": 95,
    "very high": 90, "very complete": 90,
    # Mostly complete tier (70-89)
    "high": 85, "mostly complete": 75, "mostly_complete": 75,
    "good": 75, "adequate": 75, "sufficient": 75, "above average": 75,
    "mostly comprehensive": 75, "largely complete": 75,
    # Incomplete tier (40-69)
    "medium": 55, "moderate": 55, "average": 55, "fair": 55,
    "partial": 45, "partially complete": 45, "partially_complete": 45,
    "incomplete": 35, "somewhat complete": 45, "somewhat": 45,
    "mixed": 45, "limited": 40,
    # Severely lacking tier (0-39)
    "low": 25, "poor": 20, "below average": 25,
    "severely lacking": 15, "severely_lacking": 15, "lacking": 20,
    "very low": 10, "very incomplete": 10, "minimal": 15,
    "insufficient": 25, "inadequate": 20, "weak": 20,
    "none": 0, "missing": 10, "empty": 0, "n/a": 0,
    # Boolean-like
    "true": 85, "false": 20, "yes": 85, "no": 20,
}

_VALIDITY_LABEL_MAP = {
    # Valid tier (80-100)
    "valid": 90, "correct": 90, "applicable": 85, "effective": 85,
    "very high": 90, "excellent": 95, "perfect": 95,
    "highly valid": 90, "confirmed": 90, "verified": 90,
    # Likely valid tier (60-79)
    "high": 85, "likely valid": 70, "likely_valid": 70,
    "mostly valid": 70, "mostly_valid": 70, "good": 75,
    "probably valid": 70, "should work": 70, "adequate": 70,
    "largely valid": 70, "above average": 75,
    # Uncertain tier (40-59)
    "partially valid": 55, "partially_valid": 55, "partial": 45,
    "medium": 55, "moderate": 55, "average": 55, "fair": 55,
    "uncertain": 45, "questionable": 45, "mixed": 45,
    "somewhat valid": 50, "somewhat": 45, "unclear": 45,
    "inconclusive": 45, "limited": 40,
    # Likely invalid tier (20-39)
    "likely invalid": 25, "likely_invalid": 25, "low": 20,
    "mostly invalid": 25, "mostly_invalid": 25, "poor": 20,
    "probably invalid": 25, "below average": 25, "weak": 20,
    "unlikely": 25, "doubtful": 25, "insufficient": 25,
    # Invalid tier (0-19)
    "invalid": 10, "incorrect": 10, "not valid": 10, "not_valid": 10,
    "inapplicable": 10, "not applicable": 10, "not_applicable": 10,
    "very low": 10, "none": 0, "n/a": 0, "no": 10,
    "does not apply": 10, "wrong": 10, "ineffective": 10,
    # Boolean-like
    "true": 85, "false": 10, "yes": 85,
}


def _collect_all_values(data: dict) -> dict:
    """Recursively collect all key-value pairs from nested dicts into a flat dict.
    Later (deeper) values override earlier ones for the same key."""
    flat = {}
    for key, value in data.items():
        flat[key.lower()] = value
        if isinstance(value, dict):
            for k, v in _collect_all_values(value).items():
                flat[k.lower()] = v
    return flat


def _parse_numeric_string(val: str) -> int | None:
    """Try to extract a numeric score from a string like '70', '7/10', '70%', '7 out of 10'."""
    import re
    s = val.strip()
    # Pure integer
    try:
        n = int(s)
        return n if 0 <= n <= 100 else None
    except ValueError:
        pass
    # Percentage like "70%"
    m = re.match(r'^(\d+)\s*%$', s)
    if m:
        return int(m.group(1))
    # Fraction like "7/10" or "70/100"
    m = re.match(r'^(\d+)\s*/\s*(\d+)$', s)
    if m:
        num, denom = int(m.group(1)), int(m.group(2))
        if denom > 0:
            return int(num * 100 / denom)
    # "X out of Y"
    m = re.match(r'^(\d+)\s+out\s+of\s+(\d+)$', s, re.IGNORECASE)
    if m:
        num, denom = int(m.group(1)), int(m.group(2))
        if denom > 0:
            return int(num * 100 / denom)
    return None


def _extract_score(flat: dict, score_key: str, label_keys: list[str],
                   label_map: dict, default: int = 0) -> int:
    """Extract a numeric score from flat dict, trying direct score key first,
    then falling back to mapping qualitative labels."""
    # Try the exact score key (e.g. "relevance_score")
    val = flat.get(score_key)
    if val is not None and isinstance(val, (int, float)):
        return int(val)
    if val is not None and isinstance(val, str):
        n = _parse_numeric_string(val)
        if n is not None:
            return n

    # Try "score" as a generic key
    val = flat.get("score")
    if val is not None and isinstance(val, (int, float)):
        return int(val)
    if val is not None and isinstance(val, str):
        n = _parse_numeric_string(val)
        if n is not None:
            return n

    # Try mapping qualitative labels from known keys
    for lk in label_keys:
        val = flat.get(lk)
        if isinstance(val, str):
            # Try label map first
            mapped = label_map.get(val.lower().strip())
            if mapped is not None:
                _logger.info(f"  Mapped label '{val}' -> score {mapped}")
                return mapped
            # Try parsing as a numeric string
            n = _parse_numeric_string(val)
            if n is not None:
                _logger.info(f"  Parsed numeric string '{val}' -> score {n}")
                return n
        elif isinstance(val, bool):
            return 80 if val else 20
        elif isinstance(val, (int, float)):
            return int(val)

    # LAST RESORT: scan ALL values in flat dict for any recognizable score
    # This handles cases where the LLM uses completely unexpected key names
    _logger.debug(f"  Last-resort scan of all flat keys: {list(flat.keys())}")
    for key, val in flat.items():
        if isinstance(val, (int, float)) and 0 < val <= 100 and key not in ("score",):
            _logger.info(f"  Last-resort: found numeric value {val} under key '{key}'")
            return int(val)
    for key, val in flat.items():
        if isinstance(val, str):
            mapped = label_map.get(val.lower().strip())
            if mapped is not None:
                _logger.info(f"  Last-resort: mapped label '{val}' (key='{key}') -> score {mapped}")
                return mapped
            n = _parse_numeric_string(val)
            if n is not None:
                _logger.info(f"  Last-resort: parsed numeric string '{val}' (key='{key}') -> score {n}")
                return n

    _logger.warning(f"  Could not extract score from flat keys: {list(flat.keys())}")
    return default


def _extract_bool(flat: dict, key: str, default: bool) -> bool:
    """Extract a boolean, searching by lowercase key."""
    val = flat.get(key)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower().strip() in ("true", "yes", "1")
    return default


def _extract_list(flat: dict, keys: list[str], default=None) -> list:
    """Extract a list value trying multiple possible keys."""
    for k in keys:
        val = flat.get(k)
        if isinstance(val, list):
            return val
    return default if default is not None else []


def _extract_str(flat: dict, key: str, valid_values: set, default: str) -> str:
    """Extract a string value, validating against allowed values."""
    val = flat.get(key)
    if isinstance(val, str) and val.lower().strip() in valid_values:
        return val.lower().strip()
    return default


RelevanceVerdict = Literal["excellent", "good", "partial", "poor", "irrelevant"]
CompletenessVerdict = Literal["complete", "mostly_complete", "incomplete", "severely_lacking"]
ValidityVerdict = Literal["valid", "likely_valid", "uncertain", "likely_invalid", "invalid"]
ConfidenceLevel = Literal["high", "medium", "low"]
OverallVerdict = Literal["adequate", "needs_supplementation", "inadequate", "no_citation_provided"]
ActionRequired = Literal["none", "add_context", "find_better_article", "create_content"]
GapPriority = Literal["high", "medium", "low"]
GapEffort = Literal["small", "medium", "large"]
GapRecommendation = Literal["augment_existing", "create_new", "combine_multiple"]
DescriptionQualityVerdict = Literal["well_defined", "mostly_defined", "partially_defined", "poorly_defined"]
CitationSupportVerdict = Literal["good", "partial", "bad"]
CitationGroundingVerdict = Literal["well_grounded", "partially_grounded", "poorly_grounded", "ungrounded"]
ResponseQualityVerdict = Literal["excellent", "good", "fair", "poor"]


_RESPONSE_QUALITY_LABEL_MAP = {
    # High tier (80-100)
    "excellent": 95, "perfect": 95, "outstanding": 95, "very high": 90,
    "comprehensive": 90, "thorough": 85,
    # Good tier (60-79)
    "high": 80, "good": 75, "strong": 75, "above average": 75,
    "adequate": 70, "sufficient": 70, "mostly good": 70,
    # Fair tier (40-59)
    "medium": 55, "moderate": 55, "average": 55, "fair": 55,
    "partial": 45, "mixed": 45, "somewhat": 45, "limited": 40,
    # Poor tier (0-39)
    "low": 25, "poor": 20, "weak": 20, "below average": 25,
    "inadequate": 15, "bad": 10, "very low": 10,
    "none": 0, "n/a": 0,
    # Boolean-like
    "true": 80, "false": 10, "yes": 80, "no": 10,
}


_DESCRIPTION_QUALITY_LABEL_MAP = {
    # High tier (80-100)
    "excellent": 95, "perfect": 95, "well defined": 90, "well_defined": 90,
    "very high": 90, "comprehensive": 90, "detailed": 85, "clear": 85,
    "thorough": 85, "complete": 85,
    # Good tier (60-79)
    "high": 80, "good": 75, "mostly defined": 70, "mostly_defined": 70,
    "adequate": 70, "sufficient": 70, "above average": 75,
    # Partial tier (40-59)
    "medium": 55, "moderate": 55, "average": 55, "fair": 55,
    "partial": 45, "partially defined": 45, "partially_defined": 45,
    "somewhat": 45, "mixed": 45, "limited": 40,
    # Poor tier (0-39)
    "low": 25, "poor": 20, "poorly defined": 15, "poorly_defined": 15,
    "weak": 20, "below average": 25, "vague": 20, "unclear": 20,
    "very low": 10, "minimal": 15, "insufficient": 20, "inadequate": 20,
    "none": 0, "missing": 0, "empty": 0, "n/a": 0,
    "absent": 0, "not present": 0, "not specified": 0, "not mentioned": 0,
    "not provided": 0, "unavailable": 0,
    # Boolean-like
    "true": 80, "false": 10, "yes": 80, "no": 10,
}


_KT_ALT_DIM_MAP = {"what": "identity", "where": "location", "when": "timing", "extent": "magnitude"}


def _normalize_kt_structure(data: dict) -> dict:
    """
    Pre-process alternative LLM response structures into the expected flat format.

    Handles two common deviations:
    1. Response wrapped under a "kt_evaluation" key.
    2. KT dimensions named what/where/when/extent instead of
       identity/location/timing/magnitude, with qualitative sub-dicts.
    """
    # Unwrap a "kt_evaluation" wrapper when it contains the dimension keys
    if "kt_evaluation" in data and isinstance(data.get("kt_evaluation"), dict):
        inner = data["kt_evaluation"]
        if any(k in inner for k in _KT_ALT_DIM_MAP):
            merged = dict(inner)
            for k, v in data.items():
                if k != "kt_evaluation":
                    merged.setdefault(k, v)
            data = merged

    if not any(k in data for k in _KT_ALT_DIM_MAP):
        return data  # already in expected format

    normalized: dict = {}
    for alt_key, canonical in _KT_ALT_DIM_MAP.items():
        val = data.get(alt_key)
        if val is None:
            continue
        if isinstance(val, (int, float)) and 0 <= val <= 100:
            normalized[f"{canonical}_score"] = int(val)
        elif isinstance(val, str):
            n = _parse_numeric_string(val)
            if n is not None:
                normalized[f"{canonical}_score"] = n
            else:
                mapped = _DESCRIPTION_QUALITY_LABEL_MAP.get(val.lower().strip())
                if mapped is not None:
                    normalized[f"{canonical}_score"] = mapped
        elif isinstance(val, dict):
            score = None
            # 1. Explicit numeric score key
            for sk in ("score", "score_value", "points", "rating", "value", "numeric_score"):
                sv = val.get(sk)
                if isinstance(sv, (int, float)) and 0 <= sv <= 100:
                    score = int(sv)
                    break
                if isinstance(sv, str):
                    n = _parse_numeric_string(sv)
                    if n is not None:
                        score = n
                        break
            # 2. Qualitative label from known sub-keys
            if score is None:
                for qk in ("quality", "clarity", "level", "assessment", "rating", "specificity"):
                    qv = val.get(qk)
                    if isinstance(qv, str):
                        mapped = _DESCRIPTION_QUALITY_LABEL_MAP.get(qv.lower().strip())
                        if mapped is not None:
                            score = mapped
                            break
            # 3. Scan all string values in the sub-dict
            if score is None:
                for sv in val.values():
                    if isinstance(sv, str):
                        mapped = _DESCRIPTION_QUALITY_LABEL_MAP.get(sv.lower().strip())
                        if mapped is not None:
                            score = mapped
                            break
            if score is not None:
                normalized[f"{canonical}_score"] = score
            # Extract analysis text
            for ak in ("analysis", "description", "details", "explanation", "reasoning", "notes"):
                av = val.get(ak)
                if isinstance(av, str) and av:
                    normalized[f"{canonical}_analysis"] = av
                    break

    # Copy non-dimension keys (overall score, verdict, missing elements, etc.)
    for k, v in data.items():
        if k not in _KT_ALT_DIM_MAP:
            normalized.setdefault(k, v)

    return normalized if normalized else data


@dataclass
class DescriptionQualityResult:
    """Result from the Description Quality Agent (Kepner-Tregoe framework)."""

    # Per-dimension scores (0-100)
    identity_score: int = 0
    location_score: int = 0
    timing_score: int = 0
    magnitude_score: int = 0

    # Per-dimension analysis strings
    identity_analysis: str = ""
    location_analysis: str = ""
    timing_analysis: str = ""
    magnitude_analysis: str = ""

    # Overall
    description_quality_score: int = 0
    description_quality_verdict: DescriptionQualityVerdict = "poorly_defined"

    # Missing info
    missing_kt_elements: list[str] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "identity_score": self.identity_score,
            "location_score": self.location_score,
            "timing_score": self.timing_score,
            "magnitude_score": self.magnitude_score,
            "identity_analysis": self.identity_analysis,
            "location_analysis": self.location_analysis,
            "timing_analysis": self.timing_analysis,
            "magnitude_analysis": self.magnitude_analysis,
            "description_quality_score": self.description_quality_score,
            "description_quality_verdict": self.description_quality_verdict,
            "missing_kt_elements": self.missing_kt_elements,
            "improvement_suggestions": self.improvement_suggestions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DescriptionQualityResult":
        data = _normalize_kt_structure(data)
        flat = _collect_all_values(data)

        identity_score = _extract_score(
            flat, "identity_score",
            ["identity_score", "identityscore", "identity", "what_score", "whatscore"],
            _DESCRIPTION_QUALITY_LABEL_MAP,
        )
        location_score = _extract_score(
            flat, "location_score",
            ["location_score", "locationscore", "location", "where_score", "wherescore"],
            _DESCRIPTION_QUALITY_LABEL_MAP,
        )
        timing_score = _extract_score(
            flat, "timing_score",
            ["timing_score", "timingscore", "timing", "when_score", "whenscore"],
            _DESCRIPTION_QUALITY_LABEL_MAP,
        )
        magnitude_score = _extract_score(
            flat, "magnitude_score",
            ["magnitude_score", "magnitudescore", "magnitude", "extent_score", "extentscore"],
            _DESCRIPTION_QUALITY_LABEL_MAP,
        )

        # Overall score — use provided value or compute from dimensions
        from ..config.settings import KT_DIMENSION_WEIGHTS
        overall = _extract_score(
            flat, "description_quality_score",
            ["description_quality_score", "descriptionqualityscore", "overall_score", "overallscore"],
            _DESCRIPTION_QUALITY_LABEL_MAP,
        )
        if overall == 0 and any([identity_score, location_score, timing_score, magnitude_score]):
            overall = round(
                identity_score * KT_DIMENSION_WEIGHTS["identity"]
                + location_score * KT_DIMENSION_WEIGHTS["location"]
                + timing_score * KT_DIMENSION_WEIGHTS["timing"]
                + magnitude_score * KT_DIMENSION_WEIGHTS["magnitude"]
            )

        # Derive verdict from score
        verdict_map = {
            (0, 40): "poorly_defined",
            (40, 60): "partially_defined",
            (60, 80): "mostly_defined",
            (80, 101): "well_defined",
        }
        verdict = _extract_str(
            flat, "description_quality_verdict",
            {"well_defined", "mostly_defined", "partially_defined", "poorly_defined"},
            "poorly_defined",
        )
        if verdict == "poorly_defined" and overall > 0:
            for (lo, hi), v in verdict_map.items():
                if lo <= overall < hi:
                    verdict = v
                    break

        return cls(
            identity_score=identity_score,
            location_score=location_score,
            timing_score=timing_score,
            magnitude_score=magnitude_score,
            identity_analysis=flat.get("identity_analysis", "") or "",
            location_analysis=flat.get("location_analysis", "") or "",
            timing_analysis=flat.get("timing_analysis", "") or "",
            magnitude_analysis=flat.get("magnitude_analysis", "") or "",
            description_quality_score=overall,
            description_quality_verdict=verdict,
            missing_kt_elements=_extract_list(flat, [
                "missing_kt_elements", "missingktelements",
                "missing_elements", "missingelements",
                "missing_information", "missinginformation",
            ]),
            improvement_suggestions=_extract_list(flat, [
                "improvement_suggestions", "improvementsuggestions",
                "suggestions", "recommendations",
            ]),
        )


@dataclass
class RelevanceResult:
    """Result from the Relevance Agent."""

    relevance_score: int
    matched_aspects: list[str] = field(default_factory=list)
    unmatched_aspects: list[str] = field(default_factory=list)
    version_match: bool = True
    product_match: bool = True
    is_outdated: bool = False
    relevance_verdict: RelevanceVerdict = "partial"

    def to_dict(self) -> dict:
        return {
            "relevance_score": self.relevance_score,
            "matched_aspects": self.matched_aspects,
            "unmatched_aspects": self.unmatched_aspects,
            "version_match": self.version_match,
            "product_match": self.product_match,
            "is_outdated": self.is_outdated,
            "relevance_verdict": self.relevance_verdict
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RelevanceResult":
        flat = _collect_all_values(data)
        score = _extract_score(
            flat, "relevance_score",
            [
                "relevance_score", "relevancescore", "score",
                "relevance", "relevant", "isrelevant", "is_relevant",
                "article_relevance", "articlerelevance",
                "relevance_verdict", "relevanceverdict",
                "relevance_level", "relevancelevel",
                "match", "match_level", "matchlevel",
                "verdict", "result", "rating", "assessment", "evaluation",
            ],
            _RELEVANCE_LABEL_MAP,
        )
        verdict_map = {(0, 30): "irrelevant", (30, 50): "poor", (50, 70): "partial",
                       (70, 90): "good", (90, 101): "excellent"}
        verdict = _extract_str(flat, "relevance_verdict",
                               {"excellent", "good", "partial", "poor", "irrelevant"}, "partial")
        if verdict == "partial" and score > 0:
            for (lo, hi), v in verdict_map.items():
                if lo <= score < hi:
                    verdict = v
                    break
        return cls(
            relevance_score=score,
            matched_aspects=_extract_list(flat, [
                "matched_aspects", "matchedaspects", "matched",
                "matching_aspects", "matchingaspects",
                "high_relevance_factors", "highrelevancefactors",
                "strengths", "matches",
            ]),
            unmatched_aspects=_extract_list(flat, [
                "unmatched_aspects", "unmatchedaspects", "unmatched",
                "unmatching_aspects", "unmatchingaspects",
                "low_relevance_factors", "lowrelevancefactors",
                "gaps", "weaknesses", "mismatches",
            ]),
            version_match=any(_extract_bool(flat, k, False) for k in [
                "version_match", "versionmatch", "version_appropriate",
            ]) if any(k in flat for k in ["version_match", "versionmatch", "version_appropriate"]) else True,
            product_match=any(_extract_bool(flat, k, False) for k in [
                "product_match", "productmatch", "product_relevant",
            ]) if any(k in flat for k in ["product_match", "productmatch", "product_relevant"]) else True,
            is_outdated=any(_extract_bool(flat, k, False) for k in [
                "is_outdated", "isoutdated", "outdated", "deprecated",
            ]),
            relevance_verdict=verdict,
        )


@dataclass
class CompletenessResult:
    """Result from the Completeness Agent."""

    completeness_score: int
    has_prerequisites: bool = False
    has_step_by_step: bool = False
    has_examples: bool = False
    has_troubleshooting: bool = False
    has_success_criteria: bool = False
    missing_elements: list[str] = field(default_factory=list)
    completeness_verdict: CompletenessVerdict = "incomplete"

    def to_dict(self) -> dict:
        return {
            "completeness_score": self.completeness_score,
            "has_prerequisites": self.has_prerequisites,
            "has_step_by_step": self.has_step_by_step,
            "has_examples": self.has_examples,
            "has_troubleshooting": self.has_troubleshooting,
            "has_success_criteria": self.has_success_criteria,
            "missing_elements": self.missing_elements,
            "completeness_verdict": self.completeness_verdict
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CompletenessResult":
        flat = _collect_all_values(data)
        score = _extract_score(
            flat, "completeness_score",
            [
                "completeness_score", "completenessscore", "score",
                "completeness", "complete", "iscomplete", "is_complete",
                "articlecompleteness", "article_completeness",
                "doc_completeness", "doccompleteness",
                "documentation_completeness", "documentationcompleteness",
                "completeness_verdict", "completenessverdict",
                "completeness_level", "completenesslevel",
                "coverage", "content_coverage", "contentcoverage",
                "verdict", "result", "rating", "assessment", "evaluation",
            ],
            _COMPLETENESS_LABEL_MAP,
        )
        verdict_map = {(0, 50): "severely_lacking", (50, 70): "incomplete",
                       (70, 90): "mostly_complete", (90, 101): "complete"}
        verdict = _extract_str(flat, "completeness_verdict",
                               {"complete", "mostly_complete", "incomplete", "severely_lacking"}, "incomplete")
        if verdict == "incomplete" and score > 0:
            for (lo, hi), v in verdict_map.items():
                if lo <= score < hi:
                    verdict = v
                    break
        return cls(
            completeness_score=score,
            has_prerequisites=any(_extract_bool(flat, k, False) for k in [
                "has_prerequisites", "hasprerequisites", "prerequisites_section",
                "prerequisitessection", "prerequisites", "prereqs",
            ]),
            has_step_by_step=any(_extract_bool(flat, k, False) for k in [
                "has_step_by_step", "hasstepbystep", "step_by_step", "stepbystep",
                "steps_clear", "stepsclear", "has_steps", "hassteps",
            ]),
            has_examples=any(_extract_bool(flat, k, False) for k in [
                "has_examples", "hasexamples", "examples", "has_code_samples",
                "hascodesamples", "has_screenshots", "hasscreenshots",
            ]),
            has_troubleshooting=any(_extract_bool(flat, k, False) for k in [
                "has_troubleshooting", "hastroubleshooting", "troubleshooting",
                "has_troubleshooting_steps", "hastroubleshootingsteps",
            ]),
            has_success_criteria=any(_extract_bool(flat, k, False) for k in [
                "has_success_criteria", "hassuccesscriteria", "success_criteria",
                "successcriteria", "has_verification", "hasverification",
            ]),
            missing_elements=_extract_list(flat, [
                "missing_elements", "missingelements",
                "missing_components", "missingcomponents",
                "missing_sections", "missingsections",
                "gaps", "issues", "weaknesses",
            ]),
            completeness_verdict=verdict,
        )


@dataclass
class ValidityResult:
    """Result from the Validity Agent."""

    validity_score: int
    addresses_root_cause: bool = False
    is_current_solution: bool = True
    environment_compatible: bool = True
    potential_issues: list[str] = field(default_factory=list)
    confidence_level: ConfidenceLevel = "medium"
    validity_verdict: ValidityVerdict = "uncertain"

    def to_dict(self) -> dict:
        return {
            "validity_score": self.validity_score,
            "addresses_root_cause": self.addresses_root_cause,
            "is_current_solution": self.is_current_solution,
            "environment_compatible": self.environment_compatible,
            "potential_issues": self.potential_issues,
            "confidence_level": self.confidence_level,
            "validity_verdict": self.validity_verdict
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ValidityResult":
        flat = _collect_all_values(data)
        score = _extract_score(
            flat, "validity_score",
            [
                "validity_score", "validityscore", "score",
                "validity", "valid", "isvalid", "is_valid",
                "issolutionvalid", "is_solution_valid",
                "solution_valid", "solutionvalid",
                "article_validity", "articlevalidity",
                "validity_verdict", "validityverdict",
                "validity_level", "validitylevel",
                "effectiveness", "applicability", "applicable",
                "verdict", "result", "rating", "assessment", "evaluation",
            ],
            _VALIDITY_LABEL_MAP,
        )
        verdict_map = {(0, 20): "invalid", (20, 40): "likely_invalid", (40, 60): "uncertain",
                       (60, 80): "likely_valid", (80, 101): "valid"}
        verdict = _extract_str(flat, "validity_verdict",
                               {"valid", "likely_valid", "uncertain", "likely_invalid", "invalid"}, "uncertain")
        if verdict == "uncertain" and score > 0:
            for (lo, hi), v in verdict_map.items():
                if lo <= score < hi:
                    verdict = v
                    break
        return cls(
            validity_score=score,
            addresses_root_cause=any(_extract_bool(flat, k, False) for k in [
                "addresses_root_cause", "addressesrootcause",
                "root_cause", "rootcause", "addresses_cause",
            ]),
            is_current_solution=not any(_extract_bool(flat, k, False) for k in [
                "is_deprecated", "isdeprecated", "deprecated", "outdated",
            ]) if any(k in flat for k in ["is_deprecated", "isdeprecated", "deprecated", "outdated"]) else _extract_bool(flat, "is_current_solution", True),
            environment_compatible=any(_extract_bool(flat, k, True) for k in [
                "environment_compatible", "environmentcompatible",
                "env_compatible", "envcompatible", "compatible",
            ]) if any(k in flat for k in ["environment_compatible", "environmentcompatible", "env_compatible", "envcompatible", "compatible"]) else True,
            potential_issues=_extract_list(flat, [
                "potential_issues", "potentialissues",
                "issues", "concerns", "risks", "problems",
                "reasons", "limitations", "caveats",
            ]),
            confidence_level=_extract_str(flat, "confidence_level", {"high", "medium", "low"}, "medium"),
            validity_verdict=verdict,
        )


@dataclass
class RecommendedArticle:
    """A recommended article from search results."""

    url: str
    title: str
    relevance_reason: str
    estimated_match_score: int
    last_updated: str | None = None
    article_type: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "relevance_reason": self.relevance_reason,
            "estimated_match_score": self.estimated_match_score,
            "last_updated": self.last_updated,
            "article_type": self.article_type
        }


@dataclass
class SearchResult:
    """Result from the Search Agent."""

    recommended_articles: list[RecommendedArticle] = field(default_factory=list)
    search_terms_used: list[str] = field(default_factory=list)
    better_alternative_found: bool = False

    def to_dict(self) -> dict:
        return {
            "recommended_articles": [a.to_dict() for a in self.recommended_articles],
            "search_terms_used": self.search_terms_used,
            "better_alternative_found": self.better_alternative_found
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SearchResult":
        data = _flatten_to_fields(data, {"recommended_articles", "search_terms_used"})
        articles = [
            RecommendedArticle(**a) if isinstance(a, dict) else a
            for a in data.get("recommended_articles", [])
        ]
        return cls(
            recommended_articles=articles,
            search_terms_used=data.get("search_terms_used", []),
            better_alternative_found=data.get("better_alternative_found", False)
        )


@dataclass
class GapAnalysisResult:
    """Result from the Gap Analysis Agent."""

    documentation_gaps: list[str] = field(default_factory=list)
    suggested_content_outline: list[str] = field(default_factory=list)
    required_expertise: list[str] = field(default_factory=list)
    priority: GapPriority = "medium"
    estimated_effort: GapEffort = "medium"
    recommendation: GapRecommendation = "augment_existing"

    def to_dict(self) -> dict:
        return {
            "documentation_gaps": self.documentation_gaps,
            "suggested_content_outline": self.suggested_content_outline,
            "required_expertise": self.required_expertise,
            "priority": self.priority,
            "estimated_effort": self.estimated_effort,
            "recommendation": self.recommendation
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GapAnalysisResult":
        data = _flatten_to_fields(data, {"documentation_gaps", "suggested_content_outline", "priority"})
        return cls(
            documentation_gaps=data.get("documentation_gaps", []),
            suggested_content_outline=data.get("suggested_content_outline", []),
            required_expertise=data.get("required_expertise", []),
            priority=data.get("priority", "medium"),
            estimated_effort=data.get("estimated_effort", "medium"),
            recommendation=data.get("recommendation", "augment_existing")
        )


_CITATION_SUPPORT_LABEL_MAP = {
    "excellent": 95, "perfect": 95, "strong": 90, "well supported": 90,
    "supported": 85, "good": 80, "high": 85,
    "mostly supported": 70, "mostly_supported": 70, "above average": 75,
    "medium": 55, "moderate": 55, "partial": 50, "partially supported": 50,
    "partially_supported": 50, "mixed": 50, "fair": 55,
    "weak": 25, "low": 20, "poor": 15, "poorly supported": 15,
    "poorly_supported": 15, "not supported": 5, "not_supported": 5,
    "unsupported": 5, "none": 0, "n/a": 0,
}


@dataclass
class PerCitationResult:
    """Result of evaluating a single citation against its attributed text."""

    citation_index: int = 0
    url: str = ""
    support_score: int = 0
    verdict: CitationSupportVerdict = "bad"
    coverage_percentage: float = 0.0
    support_reasoning: str = ""
    key_claims_supported: list[str] = field(default_factory=list)
    key_claims_unsupported: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "citation_index": self.citation_index,
            "url": self.url,
            "support_score": self.support_score,
            "verdict": self.verdict,
            "coverage_percentage": round(self.coverage_percentage, 1),
            "support_reasoning": self.support_reasoning,
            "key_claims_supported": self.key_claims_supported,
            "key_claims_unsupported": self.key_claims_unsupported,
        }

    @classmethod
    def from_dict(cls, data: dict, citation_index: int = 0,
                  url: str = "", coverage_percentage: float = 0.0) -> "PerCitationResult":
        flat = _collect_all_values(data)
        score = _extract_score(
            flat, "support_score",
            ["support_score", "supportscore", "score", "support",
             "grounding_score", "groundingscore"],
            _CITATION_SUPPORT_LABEL_MAP,
        )
        verdict_map = {(0, 40): "bad", (40, 70): "partial", (70, 101): "good"}
        verdict = _extract_str(
            flat, "verdict", {"good", "partial", "bad"}, "bad"
        )
        if verdict == "bad" and score > 0:
            for (lo, hi), v in verdict_map.items():
                if lo <= score < hi:
                    verdict = v
                    break
        return cls(
            citation_index=citation_index,
            url=url,
            support_score=score,
            verdict=verdict,
            coverage_percentage=coverage_percentage,
            support_reasoning=flat.get("support_reasoning", "") or flat.get("reasoning", "") or "",
            key_claims_supported=_extract_list(flat, [
                "key_claims_supported", "keyclaimssupported",
                "claims_supported", "claimssupported",
                "supported_claims", "supportedclaims",
            ]),
            key_claims_unsupported=_extract_list(flat, [
                "key_claims_unsupported", "keyclaimsunsupported",
                "claims_unsupported", "claimsunsupported",
                "unsupported_claims", "unsupportedclaims",
            ]),
        )


@dataclass
class CitationQualityResult:
    """Aggregated citation quality evaluation for an AI response."""

    per_citation_results: list[PerCitationResult] = field(default_factory=list)
    overall_grounding_score: int = 0
    overall_verdict: CitationGroundingVerdict = "ungrounded"
    cited_percentage: float = 0.0
    uncited_percentage: float = 100.0
    citations_total: int = 0
    citations_good: int = 0
    citations_partial: int = 0
    citations_bad: int = 0

    def to_dict(self) -> dict:
        return {
            "per_citation_results": [r.to_dict() for r in self.per_citation_results],
            "overall_grounding_score": self.overall_grounding_score,
            "overall_verdict": self.overall_verdict,
            "cited_percentage": round(self.cited_percentage, 1),
            "uncited_percentage": round(self.uncited_percentage, 1),
            "citations_total": self.citations_total,
            "citations_good": self.citations_good,
            "citations_partial": self.citations_partial,
            "citations_bad": self.citations_bad,
        }

    @classmethod
    def from_per_citation(cls, results: list[PerCitationResult],
                          cited_pct: float, uncited_pct: float) -> "CitationQualityResult":
        """Build aggregate result from per-citation results."""
        if not results:
            return cls()

        good = sum(1 for r in results if r.verdict == "good")
        partial = sum(1 for r in results if r.verdict == "partial")
        bad = sum(1 for r in results if r.verdict == "bad")

        # Coverage-weighted overall score
        total_coverage = sum(r.coverage_percentage for r in results)
        if total_coverage > 0:
            overall = round(
                sum(r.support_score * r.coverage_percentage for r in results)
                / total_coverage
            )
        else:
            overall = round(sum(r.support_score for r in results) / len(results))

        # Derive verdict from overall score
        if overall >= 70:
            verdict = "well_grounded"
        elif overall >= 50:
            verdict = "partially_grounded"
        elif overall >= 25:
            verdict = "poorly_grounded"
        else:
            verdict = "ungrounded"

        return cls(
            per_citation_results=results,
            overall_grounding_score=overall,
            overall_verdict=verdict,
            cited_percentage=cited_pct,
            uncited_percentage=uncited_pct,
            citations_total=len(results),
            citations_good=good,
            citations_partial=partial,
            citations_bad=bad,
        )


@dataclass
class ResponseQualityResult:
    """Result from the ResponseQualityAgent — multi-dimensional AI response evaluation."""

    # Per-dimension scores (0-100)
    response_quality_score: int = 0
    response_quality_analysis: str = ""
    groundedness_score: int = 0
    groundedness_analysis: str = ""
    issue_resolution_score: int = 0
    issue_resolution_analysis: str = ""

    # Aggregate
    ai_response_quality_score: int = 0
    ai_response_quality_verdict: ResponseQualityVerdict = "poor"

    # Detail lists
    quality_weaknesses: list[str] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "response_quality_score": self.response_quality_score,
            "response_quality_analysis": self.response_quality_analysis,
            "groundedness_score": self.groundedness_score,
            "groundedness_analysis": self.groundedness_analysis,
            "issue_resolution_score": self.issue_resolution_score,
            "issue_resolution_analysis": self.issue_resolution_analysis,
            "ai_response_quality_score": self.ai_response_quality_score,
            "ai_response_quality_verdict": self.ai_response_quality_verdict,
            "quality_weaknesses": self.quality_weaknesses,
            "improvement_suggestions": self.improvement_suggestions,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        groundedness_score: int = 0,
        groundedness_analysis: str = "",
    ) -> "ResponseQualityResult":
        """Build from LLM JSON output. Groundedness is passed in from CitationQualityAgent."""
        flat = _collect_all_values(data)

        rq_score = _extract_score(
            flat, "response_quality_score",
            ["response_quality_score", "responsequalityscore",
             "quality_score", "qualityscore", "response_quality"],
            _RESPONSE_QUALITY_LABEL_MAP,
        )
        ir_score = _extract_score(
            flat, "issue_resolution_score",
            ["issue_resolution_score", "issueresolutionscore",
             "resolution_score", "resolutionscore", "issue_resolution"],
            _RESPONSE_QUALITY_LABEL_MAP,
        )

        rq_analysis = flat.get("response_quality_analysis", "") or flat.get("quality_analysis", "") or ""
        ir_analysis = flat.get("issue_resolution_analysis", "") or flat.get("resolution_analysis", "") or ""

        # Compute weighted overall
        from ..config.settings import RESPONSE_QUALITY_WEIGHTS
        overall = round(
            rq_score * RESPONSE_QUALITY_WEIGHTS["response_quality"]
            + groundedness_score * RESPONSE_QUALITY_WEIGHTS["groundedness"]
            + ir_score * RESPONSE_QUALITY_WEIGHTS["issue_resolution"]
        )

        # Derive verdict
        if overall >= 80:
            verdict = "excellent"
        elif overall >= 60:
            verdict = "good"
        elif overall >= 40:
            verdict = "fair"
        else:
            verdict = "poor"

        return cls(
            response_quality_score=rq_score,
            response_quality_analysis=rq_analysis,
            groundedness_score=groundedness_score,
            groundedness_analysis=groundedness_analysis,
            issue_resolution_score=ir_score,
            issue_resolution_analysis=ir_analysis,
            ai_response_quality_score=overall,
            ai_response_quality_verdict=verdict,
            quality_weaknesses=_extract_list(flat, [
                "quality_weaknesses", "qualityweaknesses",
                "weaknesses", "issues", "problems",
            ]),
            improvement_suggestions=_extract_list(flat, [
                "improvement_suggestions", "improvementsuggestions",
                "suggestions", "recommendations", "improvements",
            ]),
        )


@dataclass
class EvaluationResult:
    """Complete evaluation result from the Orchestrator."""

    issue_summary: dict = field(default_factory=dict)
    current_article_evaluation: dict = field(default_factory=dict)
    overall_score: int = 0
    verdict: OverallVerdict = "inadequate"
    action_required: ActionRequired = "find_better_article"
    recommended_articles: list[dict] = field(default_factory=list)
    content_gaps: dict = field(default_factory=dict)
    final_recommendation: str = ""
    description_quality: dict = field(default_factory=dict)
    evaluation_reliability_warning: bool = False
    citation_quality: dict = field(default_factory=dict)
    response_quality: dict = field(default_factory=dict)
    # LLM-synthesized recommendation fields
    synthesis_priority: str = ""
    synthesis_priority_reason: str = ""
    synthesis_pm_actions: list[str] = field(default_factory=list)
    synthesis_root_cause_category: str = ""

    def to_dict(self) -> dict:
        return {
            "issue_summary": self.issue_summary,
            "current_article_evaluation": self.current_article_evaluation,
            "overall_score": self.overall_score,
            "verdict": self.verdict,
            "action_required": self.action_required,
            "recommended_articles": self.recommended_articles,
            "content_gaps": self.content_gaps,
            "final_recommendation": self.final_recommendation,
            "description_quality": self.description_quality,
            "evaluation_reliability_warning": self.evaluation_reliability_warning,
            "citation_quality": self.citation_quality,
            "response_quality": self.response_quality,
            "synthesis_priority": self.synthesis_priority,
            "synthesis_priority_reason": self.synthesis_priority_reason,
            "synthesis_pm_actions": self.synthesis_pm_actions,
            "synthesis_root_cause_category": self.synthesis_root_cause_category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvaluationResult":
        return cls(
            issue_summary=data.get("issue_summary", {}),
            current_article_evaluation=data.get("current_article_evaluation", {}),
            overall_score=data.get("overall_score", 0),
            verdict=data.get("verdict", "inadequate"),
            action_required=data.get("action_required", "find_better_article"),
            recommended_articles=data.get("recommended_articles", []),
            content_gaps=data.get("content_gaps", {}),
            final_recommendation=data.get("final_recommendation", ""),
            description_quality=data.get("description_quality", {}),
            evaluation_reliability_warning=data.get("evaluation_reliability_warning", False),
            citation_quality=data.get("citation_quality", {}),
            response_quality=data.get("response_quality", {}),
            synthesis_priority=data.get("synthesis_priority", ""),
            synthesis_priority_reason=data.get("synthesis_priority_reason", ""),
            synthesis_pm_actions=data.get("synthesis_pm_actions", []),
            synthesis_root_cause_category=data.get("synthesis_root_cause_category", ""),
        )


@dataclass
class TrendCluster:
    """A cluster of related cases with a unified PM action."""

    cluster_name: str = ""
    case_count: int = 0
    case_numbers: list[str] = field(default_factory=list)
    root_cause_pattern: str = ""
    products_affected: list[str] = field(default_factory=list)
    unified_pm_action: str = ""
    estimated_impact: str = ""
    priority: str = ""
    supporting_evidence: list[str] = field(default_factory=list)
    area_path: str = ""

    def to_dict(self) -> dict:
        return {
            "cluster_name": self.cluster_name,
            "case_count": self.case_count,
            "case_numbers": self.case_numbers,
            "root_cause_pattern": self.root_cause_pattern,
            "products_affected": self.products_affected,
            "unified_pm_action": self.unified_pm_action,
            "estimated_impact": self.estimated_impact,
            "priority": self.priority,
            "supporting_evidence": self.supporting_evidence,
            "area_path": self.area_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TrendCluster":
        return cls(
            cluster_name=data.get("cluster_name", ""),
            case_count=data.get("case_count", 0),
            case_numbers=data.get("case_numbers", []),
            root_cause_pattern=data.get("root_cause_pattern", ""),
            products_affected=data.get("products_affected", []),
            unified_pm_action=data.get("unified_pm_action", ""),
            estimated_impact=data.get("estimated_impact", ""),
            priority=data.get("priority", ""),
            supporting_evidence=data.get("supporting_evidence", []),
            area_path=data.get("area_path", ""),
        )


@dataclass
class CitationOverlap:
    """Cases that share the same cited article URL."""
    url: str = ""
    overlap_type: str = ""   # "duplicate_issues" | "cross_coverage"
    case_count: int = 0
    case_numbers: list = field(default_factory=list)
    similarity_score: float = 0.0   # avg Jaccard between issue descriptions
    issue_snippets: list = field(default_factory=list)  # first 150 chars per case
    flag_reason: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url, "overlap_type": self.overlap_type,
            "case_count": self.case_count, "case_numbers": self.case_numbers,
            "similarity_score": round(self.similarity_score, 3),
            "issue_snippets": self.issue_snippets,
            "flag_reason": self.flag_reason, "recommendation": self.recommendation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CitationOverlap":
        return cls(
            url=data.get("url", ""),
            overlap_type=data.get("overlap_type", ""),
            case_count=data.get("case_count", 0),
            case_numbers=data.get("case_numbers", []),
            similarity_score=data.get("similarity_score", 0.0),
            issue_snippets=data.get("issue_snippets", []),
            flag_reason=data.get("flag_reason", ""),
            recommendation=data.get("recommendation", ""),
        )
