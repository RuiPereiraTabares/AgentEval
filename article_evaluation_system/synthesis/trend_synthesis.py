"""
Trend-based aggregate synthesis — clusters batch results into 3-7 high-impact actions.
"""

import json
import logging
from collections import defaultdict

from ..agents import BaseAgent
from ..models.evaluation import TrendCluster
from ..utils.prompts import AgentPrompts

logger = logging.getLogger(__name__)

# Maximum cases per LLM chunk (to stay within token limits)
_CHUNK_SIZE = 100


class TrendSynthesizer(BaseAgent):
    """Clusters evaluated cases by pattern and produces unified PM actions."""

    def evaluate(self, **kwargs):
        """Not used — call synthesize_trends() directly."""
        raise NotImplementedError("Use synthesize_trends() instead")

    def synthesize_trends(self, results: list[dict]) -> dict:
        """Main entry point: cluster results and produce trend report.

        Args:
            results: List of per-case result dicts (same format as written to CSV).

        Returns:
            Dict with keys: clusters (list[TrendCluster dicts]),
            executive_summary (str).
        """
        if not results:
            return {"clusters": [], "executive_summary": "No cases to analyse."}

        case_summaries = self._build_case_summaries(results)

        if not case_summaries:
            return {"clusters": [], "executive_summary": "No evaluable cases found."}

        # Process in chunks if >_CHUNK_SIZE
        if len(case_summaries) <= _CHUNK_SIZE:
            return self._synthesize_chunk(case_summaries)

        all_clusters: list[dict] = []
        for i in range(0, len(case_summaries), _CHUNK_SIZE):
            chunk = case_summaries[i : i + _CHUNK_SIZE]
            chunk_result = self._synthesize_chunk(chunk)
            all_clusters.extend(chunk_result.get("clusters", []))

        # Merge clusters from chunks via a second LLM pass
        if len(all_clusters) > 7:
            return self._merge_clusters(all_clusters)

        executive_summary = self._build_executive_summary(all_clusters)
        return {"clusters": all_clusters, "executive_summary": executive_summary}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_case_summaries(self, results: list[dict]) -> list[dict]:
        """Compact each result to ~200 tokens for the LLM."""
        summaries = []
        for r in results:
            ev = r.get("evaluation", {})
            if not ev:
                continue

            issue = ev.get("issue_summary", {})
            article = ev.get("current_article_evaluation", {})
            gap = ev.get("content_gaps", {})

            # Determine the key gap (first documentation gap or first PM action)
            doc_gaps = gap.get("documentation_gaps", [])
            pm_actions = ev.get("synthesis_pm_actions", [])
            key_gap = (doc_gaps[0] if doc_gaps else
                       pm_actions[0] if pm_actions else "")

            summaries.append({
                "case_number": r.get("case_number", ""),
                "product": issue.get("product", "Unknown"),
                "area_path": issue.get("area_path", ""),
                "root_cause_category": ev.get("synthesis_root_cause_category", ""),
                "priority": ev.get("synthesis_priority", ""),
                "error_codes": issue.get("error_codes", []),
                "key_gap": key_gap[:200],
                "article_url": article.get("url", ""),
                "article_title": article.get("title", ""),
                "overall_score": ev.get("overall_score", 0),
                "pm_actions": pm_actions[:2],
            })
        return summaries

    def _synthesize_chunk(self, case_summaries: list[dict]) -> dict:
        """Call the LLM to cluster a chunk of case summaries."""
        try:
            user_message = json.dumps(case_summaries, indent=None, default=str)
            response = self._call_llm(AgentPrompts.TREND_SYNTHESIS, user_message)
            parsed = self._parse_json_response(response)

            clusters = []
            for c in parsed.get("clusters", []):
                tc = TrendCluster.from_dict(c)
                clusters.append(tc.to_dict())

            executive_summary = parsed.get("executive_summary", "")
            logger.info(
                f"[TrendSynthesizer] Produced {len(clusters)} clusters "
                f"from {len(case_summaries)} cases"
            )
            return {"clusters": clusters, "executive_summary": executive_summary}

        except Exception as e:
            logger.warning(f"[TrendSynthesizer] LLM call failed, using fallback: {e}")
            return self._deterministic_fallback(case_summaries)

    def _merge_clusters(self, clusters: list[dict]) -> dict:
        """Merge too-many clusters via a second LLM pass."""
        try:
            merge_prompt = (
                "You previously produced these clusters from multiple chunks. "
                "Merge them into 3-7 final clusters by combining similar ones. "
                "Keep the same JSON output format."
            )
            user_message = json.dumps({"clusters": clusters}, indent=None, default=str)
            response = self._call_llm(
                AgentPrompts.TREND_SYNTHESIS + "\n\n" + merge_prompt,
                user_message,
            )
            parsed = self._parse_json_response(response)
            merged = [TrendCluster.from_dict(c).to_dict() for c in parsed.get("clusters", [])]
            executive_summary = parsed.get("executive_summary", "")
            return {"clusters": merged, "executive_summary": executive_summary}
        except Exception:
            # Just take top 7 by case_count
            sorted_clusters = sorted(clusters, key=lambda c: c.get("case_count", 0), reverse=True)
            return {
                "clusters": sorted_clusters[:7],
                "executive_summary": self._build_executive_summary(sorted_clusters[:7]),
            }

    def _deterministic_fallback(self, case_summaries: list[dict]) -> dict:
        """Group by area_path + root_cause_category without LLM.

        Uses area_path as the primary grouping dimension when available,
        falling back to product + root_cause_category for uncategorized cases.
        """
        groups: dict[str, list[dict]] = defaultdict(list)
        for cs in case_summaries:
            area = cs.get("area_path", "")
            if area:
                key = f"{area}|{cs.get('root_cause_category', 'unknown')}"
            else:
                key = f"{cs.get('product', 'Unknown')}|{cs.get('root_cause_category', 'unknown')}"
            groups[key].append(cs)

        # Filter groups with >=2 cases, sort by size desc
        valid_groups = {k: v for k, v in groups.items() if len(v) >= 2}
        sorted_keys = sorted(valid_groups, key=lambda k: len(valid_groups[k]), reverse=True)[:7]

        clusters = []
        for key in sorted_keys:
            cases = valid_groups[key]
            primary_label, root_cause = key.split("|", 1)
            priorities = [c.get("priority", "") for c in cases]
            priority = "red" if "red" in priorities else ("yellow" if "yellow" in priorities else "green")
            area_path = cases[0].get("area_path", "")

            clusters.append(TrendCluster(
                cluster_name=f"{primary_label} — {root_cause}",
                case_count=len(cases),
                case_numbers=[c.get("case_number", "") for c in cases],
                root_cause_pattern=root_cause,
                products_affected=list({c.get("product", "") for c in cases}),
                unified_pm_action=f"Address {root_cause} issues in {primary_label} ({len(cases)} cases)",
                estimated_impact=f"Would resolve ~{len(cases)} cases",
                priority=priority,
                supporting_evidence=[c.get("key_gap", "")[:150] for c in cases[:3] if c.get("key_gap")],
                area_path=area_path,
            ).to_dict())

        executive_summary = self._build_executive_summary(clusters)
        return {"clusters": clusters, "executive_summary": executive_summary}

    @staticmethod
    def _build_executive_summary(clusters: list[dict]) -> str:
        if not clusters:
            return "No significant patterns found."
        total_cases = sum(c.get("case_count", 0) for c in clusters)
        top = clusters[0] if clusters else {}
        return (
            f"Found {len(clusters)} trend clusters covering {total_cases} cases. "
            f"Top pattern: '{top.get('cluster_name', 'N/A')}' "
            f"({top.get('case_count', 0)} cases, priority: {top.get('priority', 'N/A')})."
        )
