"""
Transfer Reason Agent — Classifies WHY a case was transferred.

Runs LAST (after all other agents), synthesising CSV metadata, upstream agent
scores, and escalation-signal detection to produce a root-cause classification.

Classification decision tree (cascading — description checked BEFORE citation):

  transferred == False  → "not_transferred"
  transferred == True:
      escalation_signals >= 2        → "customer_escalation"
      description_quality < 40:
          has citations + relevance < 50 → "poor_description_bad_citation"
          has citations + relevance >= 50 → "poor_description"
          no citations                   → "poor_description"
      description_quality >= 40:
          no citations      → "no_citation_found"
          relevance < 50    → "bad_citation_match"
          overall < 60      → "inadequate_article"
          else              → "unknown"
"""

import logging
import re

from . import BaseAgent
from ..models.issue import Issue
from ..models.evaluation import TransferReasonResult, ConfidenceLevel
from ..utils.prompts import AgentPrompts
from ..config.settings import TRANSFER_CLASSIFICATION_THRESHOLDS

logger = logging.getLogger(__name__)

# Heuristic keyword patterns for quick escalation pre-screening
_ESCALATION_KEYWORDS = [
    re.compile(r"\bescalat(e|ed|ion|ing)\b", re.IGNORECASE),
    re.compile(r"\btransfer\s+(me|this|the case|to)\b", re.IGNORECASE),
    re.compile(r"\bspeak\s+to\s+(a\s+)?(manager|supervisor|specialist|engineer)\b", re.IGNORECASE),
    re.compile(r"\bneed\s+(a\s+)?specialist\b", re.IGNORECASE),
    re.compile(r"\b(unacceptable|ridiculous|outrageous)\b", re.IGNORECASE),
    re.compile(r"\b(\d+)(st|nd|rd|th)\s+time\s+(calling|contacting|reaching)\b", re.IGNORECASE),
    re.compile(r"\balready\s+contact(ed)?\s+support\b", re.IGNORECASE),
    re.compile(r"\bprevious\s+case\b", re.IGNORECASE),
    re.compile(r"\bSLA\s+breach\b", re.IGNORECASE),
    re.compile(r"\bbusiness\s+is\s+stopped\b", re.IGNORECASE),
    re.compile(r"\bcritical\s+deadline\b", re.IGNORECASE),
    re.compile(r"\bexecutive\s+sponsor\b", re.IGNORECASE),
    re.compile(r"\bVP\s+is\s+asking\b", re.IGNORECASE),
]

# Minimum description length to warrant an LLM escalation call
_MIN_DESC_LENGTH_FOR_LLM = 30


class TransferReasonAgent(BaseAgent):
    """Classifies the root cause of a case transfer."""

    def evaluate(
        self,
        issue: Issue,
        description_quality_result=None,
        overall_score: int = 0,
        relevance_score: int = 0,
        contains_citations: bool = False,
        verdict: str = "",
    ) -> TransferReasonResult:
        """
        Classify why this case was transferred.

        Args:
            issue: Parsed customer issue (with transfer metadata populated).
            description_quality_result: DescriptionQualityResult from upstream.
            overall_score: Overall article evaluation score (0-100).
            relevance_score: Relevance score from RelevanceAgent (0-100).
            contains_citations: Whether the case included article citations.
            verdict: Overall verdict string from orchestrator.

        Returns:
            TransferReasonResult with classification and narrative.
        """
        transferred = issue.transferred
        sr_status = issue.sr_status
        reopened = issue.reopened
        desc_quality = (
            description_quality_result.description_quality_score
            if description_quality_result
            else 0
        )

        logger.info(
            f"[TransferReasonAgent] Starting classification: "
            f"transferred={transferred}, desc_quality={desc_quality}, "
            f"overall={overall_score}, relevance={relevance_score}, "
            f"has_citations={contains_citations}"
        )

        # ------------------------------------------------------------------
        # Fast path: not transferred (or column absent → None)
        # ------------------------------------------------------------------
        if not transferred:
            reason = "not_transferred"
            logger.info(f"[TransferReasonAgent] Fast path: {reason}")
            return TransferReasonResult(
                transfer_reason=reason,
                confidence="high",
                transferred=transferred,
                sr_status=sr_status,
                reopened=reopened,
                contributing_factors=["Case was not transferred"],
                description_quality_score=desc_quality,
                overall_article_score=overall_score,
                relevance_score=relevance_score,
                contains_citations=contains_citations,
                narrative="This case was not transferred — no root-cause analysis required.",
            )

        # ------------------------------------------------------------------
        # Escalation detection (heuristic + optional LLM)
        # ------------------------------------------------------------------
        escalation_signals = self._detect_escalation_signals(issue)
        logger.info(
            f"[TransferReasonAgent] Escalation signals detected: {len(escalation_signals)} "
            f"— {escalation_signals}"
        )

        # ------------------------------------------------------------------
        # Thresholds
        # ------------------------------------------------------------------
        thresholds = TRANSFER_CLASSIFICATION_THRESHOLDS
        poor_desc_ceiling = thresholds["poor_description_ceiling"]
        bad_cite_ceiling = thresholds["bad_citation_relevance_ceiling"]
        inad_article_ceiling = thresholds["inadequate_article_overall_ceiling"]

        # ------------------------------------------------------------------
        # Classification decision tree
        # ------------------------------------------------------------------
        contributing_factors: list[str] = []
        reason: str = "unknown"
        confidence: ConfidenceLevel = "medium"

        # 1. Customer escalation (intent overrides all)
        if len(escalation_signals) >= 2:
            reason = "customer_escalation"
            confidence = "high"
            contributing_factors.append(
                f"Detected {len(escalation_signals)} escalation signal(s) in description"
            )
            for sig in escalation_signals:
                contributing_factors.append(f"Signal: {sig}")

        # 2. Poor description (checked BEFORE citation quality)
        elif desc_quality < poor_desc_ceiling:
            if contains_citations and relevance_score < bad_cite_ceiling:
                # Cascade: bad description CAUSED a bad citation
                reason = "poor_description_bad_citation"
                confidence = "high"
                contributing_factors.append(
                    f"Description quality score ({desc_quality}) below threshold ({poor_desc_ceiling})"
                )
                contributing_factors.append(
                    f"Citation relevance ({relevance_score}) also below threshold ({bad_cite_ceiling}) "
                    f"— likely a downstream effect of the vague description"
                )
            elif contains_citations and relevance_score >= bad_cite_ceiling:
                # Bad description, but citation happened to be OK
                reason = "poor_description"
                confidence = "high"
                contributing_factors.append(
                    f"Description quality score ({desc_quality}) below threshold ({poor_desc_ceiling})"
                )
                contributing_factors.append(
                    "Citations present with acceptable relevance, but the root risk remains "
                    "the vague description"
                )
            else:
                # No citations at all
                reason = "poor_description"
                confidence = "high"
                contributing_factors.append(
                    f"Description quality score ({desc_quality}) below threshold ({poor_desc_ceiling})"
                )
                contributing_factors.append(
                    "No citations were provided — the vague description likely prevented "
                    "the LLM from finding relevant articles"
                )

        # 3. Description adequate (>= threshold) — now check citation quality
        else:
            if not contains_citations:
                reason = "no_citation_found"
                confidence = "high"
                contributing_factors.append(
                    f"Description quality adequate ({desc_quality} >= {poor_desc_ceiling})"
                )
                contributing_factors.append(
                    "No citations were found despite a reasonable description — "
                    "possible documentation gap"
                )

            elif relevance_score < bad_cite_ceiling:
                reason = "bad_citation_match"
                confidence = "high"
                contributing_factors.append(
                    f"Description quality adequate ({desc_quality} >= {poor_desc_ceiling})"
                )
                contributing_factors.append(
                    f"Citation relevance ({relevance_score}) below threshold ({bad_cite_ceiling}) "
                    f"— the LLM selected an article that does not match the issue"
                )

            elif overall_score < inad_article_ceiling:
                reason = "inadequate_article"
                confidence = "medium"
                contributing_factors.append(
                    f"Description quality adequate ({desc_quality} >= {poor_desc_ceiling})"
                )
                contributing_factors.append(
                    f"Citation is relevant (relevance={relevance_score}) but overall score "
                    f"({overall_score}) below threshold ({inad_article_ceiling}) — "
                    f"the article does not fully resolve the issue"
                )

            else:
                reason = "unknown"
                confidence = "low"
                contributing_factors.append(
                    "All quality signals are above thresholds — the transfer reason "
                    "could not be determined from available data"
                )

        # ------------------------------------------------------------------
        # Build narrative
        # ------------------------------------------------------------------
        narrative = self._build_narrative(
            reason=reason,
            desc_quality=desc_quality,
            overall_score=overall_score,
            relevance_score=relevance_score,
            contains_citations=contains_citations,
            escalation_signals=escalation_signals,
        )

        logger.info(
            f"[TransferReasonAgent] Classification: reason={reason}, "
            f"confidence={confidence}"
        )

        return TransferReasonResult(
            transfer_reason=reason,
            confidence=confidence,
            transferred=transferred,
            sr_status=sr_status,
            reopened=reopened,
            contributing_factors=contributing_factors,
            description_quality_score=desc_quality,
            overall_article_score=overall_score,
            relevance_score=relevance_score,
            contains_citations=contains_citations,
            escalation_signals_detected=escalation_signals,
            narrative=narrative,
        )

    # ------------------------------------------------------------------
    # Escalation detection
    # ------------------------------------------------------------------

    def _detect_escalation_signals(self, issue: Issue) -> list[str]:
        """Detect escalation signals using heuristics, then optionally LLM."""
        text = issue.raw_description or ""
        signals: list[str] = []

        # Heuristic keyword scan
        for pattern in _ESCALATION_KEYWORDS:
            match = pattern.search(text)
            if match:
                # Grab a snippet of context around the match
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                snippet = text[start:end].strip()
                signals.append(f"Keyword match: '...{snippet}...'")

        # If heuristics found something OR the text is long enough, try LLM
        if len(text) >= _MIN_DESC_LENGTH_FOR_LLM and (signals or len(text) > 200):
            llm_signals = self._llm_escalation_detection(text)
            if llm_signals:
                for sig in llm_signals:
                    if sig not in signals:
                        signals.append(sig)

        return signals

    def _llm_escalation_detection(self, text: str) -> list[str]:
        """Use LLM to detect escalation signals. Returns list of signals or empty on failure."""
        try:
            response = self._call_llm(
                system_prompt=AgentPrompts.TRANSFER_REASON_ESCALATION_DETECTION,
                user_message=f"Analyze this support case description for escalation signals:\n\n{text[:2000]}",
            )
            data = self._parse_json_response(response)
            if data.get("escalation_detected"):
                return data.get("escalation_signals", [])
            return []
        except Exception as e:
            logger.warning(f"[TransferReasonAgent] LLM escalation detection failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Narrative builder
    # ------------------------------------------------------------------

    def _build_narrative(
        self,
        reason: str,
        desc_quality: int,
        overall_score: int,
        relevance_score: int,
        contains_citations: bool,
        escalation_signals: list[str],
    ) -> str:
        """Generate a human-readable explanation for the classification."""
        if reason == "not_transferred":
            return "This case was not transferred — no root-cause analysis required."

        if reason == "customer_escalation":
            sigs = "; ".join(escalation_signals[:3])
            return (
                f"The case was transferred because the customer explicitly requested "
                f"escalation. Detected signals: {sigs}."
            )

        if reason == "poor_description":
            if contains_citations:
                return (
                    f"The case description is too vague (KT score: {desc_quality}/100) to "
                    f"enable effective article matching. Although a citation was provided, "
                    f"the root risk is the poor description."
                )
            return (
                f"The case description is too vague (KT score: {desc_quality}/100). "
                f"No citations were found, likely because the LLM could not identify "
                f"the issue clearly enough to search for articles."
            )

        if reason == "poor_description_bad_citation":
            return (
                f"The vague description (KT score: {desc_quality}/100) likely caused "
                f"the LLM to select an irrelevant article (relevance: {relevance_score}/100). "
                f"The root cause is the poor description; the bad citation is a downstream effect."
            )

        if reason == "no_citation_found":
            return (
                f"The description was adequate (KT score: {desc_quality}/100) but no "
                f"citations were found. This suggests a documentation gap — relevant "
                f"articles may not exist for this issue."
            )

        if reason == "bad_citation_match":
            return (
                f"The description was adequate (KT score: {desc_quality}/100) but the "
                f"cited article is not relevant (relevance: {relevance_score}/100). "
                f"The LLM selected the wrong article."
            )

        if reason == "inadequate_article":
            return (
                f"The description was adequate (KT score: {desc_quality}/100) and the "
                f"citation is relevant (relevance: {relevance_score}/100), but the article "
                f"does not fully solve the problem (overall: {overall_score}/100)."
            )

        return (
            f"The transfer reason could not be determined. All quality signals are within "
            f"acceptable ranges (description: {desc_quality}, relevance: {relevance_score}, "
            f"overall: {overall_score})."
        )
