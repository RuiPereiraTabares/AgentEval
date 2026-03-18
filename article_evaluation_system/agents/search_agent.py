"""
Article Search Agent - Finds better or supplementary articles.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

from . import BaseAgent
from ..models.issue import Issue
from ..models.evaluation import SearchResult, RecommendedArticle
from ..utils.prompts import AgentPrompts


class SearchAgent(BaseAgent):
    """
    Agent that generates search queries for finding relevant Microsoft articles.

    Produces optimized search queries based on the customer issue
    to find better or supplementary documentation.
    """

    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai"):
        super().__init__(client, model, provider)
        self.system_prompt = AgentPrompts.SEARCH_AGENT

    def evaluate(self, issue: Issue, current_score: int = 0) -> SearchResult:
        """
        Generate search queries for finding relevant articles.

        Args:
            issue: Parsed customer issue
            current_score: Score of current article (to determine if search needed)

        Returns:
            SearchResult with recommended search queries
        """
        user_message = f"""Generate search queries to find Microsoft documentation for this issue.

## Customer Issue
**Product:** {issue.product}
**Version:** {issue.version or "Not specified"}
**Issue Type:** {issue.issue_type}
**Error Codes:** {', '.join(issue.error_codes) if issue.error_codes else "None"}
**Symptoms:** {', '.join(issue.symptoms[:5])}
**Keywords:** {', '.join(issue.keywords[:10])}

**Original Description:**
{issue.raw_description[:1000]}

Generate optimal search queries for Microsoft documentation."""

        try:
            response = self._call_llm(self.system_prompt, user_message)
            try:
                parsed_data = self._parse_json_response(response)
                raw_queries = parsed_data.get("search_queries", [])
                # Normalize: support both new format (list of dicts) and legacy (list of strings)
                search_queries = []
                query_reasons = {}
                for item in raw_queries:
                    if isinstance(item, dict):
                        q = item.get("query", "")
                        r = item.get("reason", "")
                        if q:
                            search_queries.append(q)
                            query_reasons[q] = r
                    elif isinstance(item, str):
                        search_queries.append(item)
            except ValueError:
                # LLM returned plain text instead of JSON — extract queries from it
                search_queries = self._extract_queries_from_text(response)
                query_reasons = {}
                logger.info(f"[SearchAgent] Extracted {len(search_queries)} queries from plain text response")

            # Build search result with generated queries
            recommended_articles = []
            for i, query in enumerate(search_queries[:5]):
                support_url = f"https://support.microsoft.com/search/results?query={query.replace(' ', '+')}"
                reason = query_reasons.get(query, f"Search query #{i+1} based on issue keywords")

                recommended_articles.append(RecommendedArticle(
                    url=support_url,
                    title=f"Search: {query}",
                    relevance_reason=reason,
                    estimated_match_score=70 - (i * 5),
                    article_type="search_result"
                ))

            return SearchResult(
                recommended_articles=recommended_articles,
                search_terms_used=search_queries,
                better_alternative_found=len(search_queries) > 0 and current_score < 70
            )

        except Exception as e:
            # Generate fallback searches from issue data
            return self._generate_fallback_searches(issue)

    @staticmethod
    def _extract_queries_from_text(text: str) -> list[str]:
        """Extract search queries from a plain text LLM response.

        Handles numbered lists, bulleted lists, and quoted strings like:
          1. "Teams call forwarding external number"
          - Teams call forwarding external number
          **"Teams call forwarding external number"**
        """
        queries = []
        for line in text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip list prefixes: "1. ", "- ", "* ", "1) "
            line = re.sub(r'^[\d]+[\.\)]\s*', '', line)
            line = re.sub(r'^[-*]\s*', '', line)
            # Strip markdown bold
            line = line.replace('**', '')
            # Strip surrounding quotes and backticks
            line = line.strip('`"\'')
            line = line.strip()
            # Only keep lines that look like search queries (reasonable length, not headers/prose)
            if 10 < len(line) < 150 and not line.startswith('#'):
                queries.append(line)
        return queries[:7]

    def _generate_fallback_searches(self, issue: Issue) -> SearchResult:
        """Generate basic search queries when LLM call fails."""
        queries = []

        # Product + error code search
        if issue.error_codes:
            queries.append(f"{issue.product} {issue.error_codes[0]}")

        # Product + symptoms search
        if issue.symptoms:
            queries.append(f"{issue.product} {issue.symptoms[0][:50]}")

        # Product + issue type search
        queries.append(f"{issue.product} {issue.issue_type}")

        # Keyword-based search
        if issue.keywords:
            queries.append(" ".join(issue.keywords[:4]))

        recommended_articles = [
            RecommendedArticle(
                url=f"https://support.microsoft.com/search/results?query={q.replace(' ', '+')}",
                title=f"Search: {q}",
                relevance_reason="Fallback search query",
                estimated_match_score=50,
                article_type="search_result"
            )
            for q in queries[:5]
        ]

        return SearchResult(
            recommended_articles=recommended_articles,
            search_terms_used=queries,
            better_alternative_found=True
        )

    def generate_search_urls(self, queries: list[str]) -> dict[str, list[str]]:
        """
        Generate search URLs for Microsoft domains.

        Args:
            queries: List of search query strings

        Returns:
            Dictionary with domain names as keys and URL lists as values
        """
        urls = {
            "support.microsoft.com": [],
            "learn.microsoft.com": []
        }

        for query in queries:
            encoded_query = query.replace(" ", "+")
            urls["support.microsoft.com"].append(
                f"https://support.microsoft.com/search/results?query={encoded_query}"
            )
            urls["learn.microsoft.com"].append(
                f"https://learn.microsoft.com/search/?terms={encoded_query}"
            )

        return urls
