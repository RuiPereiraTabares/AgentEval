"""
Trend-based aggregate synthesis — clusters batch results into 3-7 high-impact actions.
"""

import json
import logging
from collections import defaultdict
from statistics import mean

from ..agents import BaseAgent
from ..models.evaluation import CitationOverlap, TrendCluster
from ..utils.prompts import AgentPrompts

logger = logging.getLogger(__name__)

# Maximum cases per LLM chunk (MWAI user-message limit is 50 000 chars)
_CHUNK_SIZE = 40
_MAX_USER_CHARS = 45_000  # Leave headroom for JSON overhead


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
            return {"clusters": [], "executive_summary": "No cases to analyse.", "citation_overlaps": []}

        case_summaries = self._build_case_summaries(results)

        if not case_summaries:
            return {"clusters": [], "executive_summary": "No evaluable cases found.", "citation_overlaps": []}

        citation_overlaps = self._build_citation_overlaps(results, case_summaries)

        # Process in chunks if >_CHUNK_SIZE
        if len(case_summaries) <= _CHUNK_SIZE:
            result = self._synthesize_chunk(case_summaries)
            result["citation_overlaps"] = citation_overlaps
            return result

        all_clusters: list[dict] = []
        for i in range(0, len(case_summaries), _CHUNK_SIZE):
            chunk = case_summaries[i : i + _CHUNK_SIZE]
            chunk_result = self._synthesize_chunk(chunk)
            all_clusters.extend(chunk_result.get("clusters", []))

        # Merge clusters from chunks via a second LLM pass
        if len(all_clusters) > 7:
            result = self._merge_clusters(all_clusters)
            result["citation_overlaps"] = citation_overlaps
            return result

        executive_summary = self._build_executive_summary(all_clusters)
        return {"clusters": all_clusters, "executive_summary": executive_summary, "citation_overlaps": citation_overlaps}

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

            raw_desc = issue.get("raw_description", "")
            area_path = issue.get("area_path", "")
            if not area_path and "exchange" in issue.get("product", "").lower():
                area_path = r.get("sap_path", "")

            summaries.append({
                "case_number": r.get("case_number", ""),
                "product": issue.get("product", "Unknown"),
                "area_path": area_path,
                "root_cause_category": ev.get("synthesis_root_cause_category", ""),
                "priority": ev.get("synthesis_priority", ""),
                "error_codes": issue.get("error_codes", []),
                "key_gap": key_gap[:200],
                "article_url": article.get("url", ""),
                "article_title": article.get("title", ""),
                "overall_score": ev.get("overall_score", 0),
                "pm_actions": pm_actions[:2],
                "issue_description": raw_desc[:300],
            })
        return summaries

    def _synthesize_chunk(self, case_summaries: list[dict]) -> dict:
        """Call the LLM to cluster a chunk of case summaries."""
        try:
            user_message = json.dumps(case_summaries, indent=None, default=str)
            if len(user_message) > _MAX_USER_CHARS:
                # Trim verbose fields to fit within the MWAI 50 000-char limit
                trimmed = [
                    {
                        **c,
                        "issue_description": c.get("issue_description", "")[:100],
                        "key_gap": c.get("key_gap", "")[:80],
                        "pm_actions": [a[:80] for a in c.get("pm_actions", [])[:1]],
                    }
                    for c in case_summaries
                ]
                user_message = json.dumps(trimmed, indent=None, default=str)
                logger.debug(
                    f"[TrendSynthesizer] Trimmed summaries to {len(user_message)} chars "
                    f"for {len(case_summaries)} cases"
                )
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

            # Only add to group if semantically similar to the first case (centroid)
            desc = cs.get("issue_description", "")
            bucket = groups[key]
            if bucket:
                centroid_desc = bucket[0].get("issue_description", "")
                if self._jaccard(desc, centroid_desc) < 0.15:
                    # Route to an "other" bucket for this area
                    area_label = area or cs.get("product", "Unknown")
                    key = f"{area_label}|other"
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
        return {"clusters": clusters, "executive_summary": executive_summary, "citation_overlaps": []}

    @staticmethod
    def _jaccard(text_a: str, text_b: str) -> float:
        """Token-set Jaccard similarity between two texts."""
        a = {t for t in text_a.lower().split() if len(t) > 2}
        b = {t for t in text_b.lower().split() if len(t) > 2}
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    @staticmethod
    def _extract_urls(result: dict) -> list:
        """All article URLs referenced in a case result."""
        ev = result.get("evaluation", {})
        urls = []
        primary = ev.get("current_article_evaluation", {}).get("url", "")
        if primary:
            urls.append(primary)
        for pcr in ev.get("citation_quality", {}).get("per_citation_results", []):
            u = pcr.get("url", "")
            if u and u not in urls:
                urls.append(u)
        return urls

    def _build_citation_overlaps(self, results: list[dict], case_summaries: list[dict]) -> list[dict]:
        """Find URLs cited by ≥2 cases and classify as duplicate_issues or cross_coverage."""
        # Build case_number → description map
        desc_map: dict[str, str] = {
            cs.get("case_number", ""): cs.get("issue_description", "")
            for cs in case_summaries
        }

        # Build url → list of (case_number, description, snippet)
        url_cases: dict[str, list] = defaultdict(list)
        for result in results:
            case_num = result.get("case_number", "")
            desc = desc_map.get(case_num, "")
            snippet = desc[:150]
            for url in self._extract_urls(result):
                if not url:
                    continue
                # Avoid duplicate case entries per URL
                existing = [e[0] for e in url_cases[url]]
                if case_num not in existing:
                    url_cases[url].append((case_num, desc, snippet))

        overlaps = []
        for url, entries in url_cases.items():
            if len(entries) < 2:
                continue

            case_numbers = [e[0] for e in entries]
            descs = [e[1] for e in entries]
            snippets = [e[2] for e in entries]

            # Compute pairwise Jaccard scores
            pairs = []
            for i in range(len(descs)):
                for j in range(i + 1, len(descs)):
                    pairs.append(self._jaccard(descs[i], descs[j]))
            avg_similarity = mean(pairs) if pairs else 0.0

            n = len(entries)
            if avg_similarity >= 0.35:
                overlap_type = "duplicate_issues"
                flag_reason = (
                    f"{n} cases describe the same problem (similarity: {avg_similarity:.2f}). "
                    "Likely duplicates — one consolidated fix should close all."
                )
                recommendation = (
                    "Consolidate these cases into a single ticket. "
                    "One targeted article update or fix should resolve all of them."
                )
            else:
                overlap_type = "cross_coverage"
                flag_reason = (
                    f"{n} cases cite this article for different problems. "
                    "Changes to this article have hidden impact across unrelated issues."
                )
                recommendation = (
                    "Review this article carefully before editing. "
                    "Changes may inadvertently affect multiple unrelated support scenarios."
                )

            overlaps.append(CitationOverlap(
                url=url,
                overlap_type=overlap_type,
                case_count=n,
                case_numbers=case_numbers,
                similarity_score=avg_similarity,
                issue_snippets=snippets,
                flag_reason=flag_reason,
                recommendation=recommendation,
            ).to_dict())

        # Sort: cross_coverage first, then by case_count desc
        overlaps.sort(key=lambda o: (0 if o["overlap_type"] == "cross_coverage" else 1, -o["case_count"]))
        return overlaps

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
