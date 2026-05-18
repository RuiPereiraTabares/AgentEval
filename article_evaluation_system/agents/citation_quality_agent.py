"""
Citation Quality Agent - Evaluates whether cited articles actually support
the claims made in the AI-generated response.
"""

import concurrent.futures
import logging

from . import BaseAgent
from ..models.evaluation import PerCitationResult, CitationQualityResult
from ..utils.prompts import AgentPrompts
from ..utils.citation_parser import parse_citations
from ..utils.article_fetcher import ArticleFetcher


logger = logging.getLogger(__name__)


class CitationQualityAgent(BaseAgent):
    """
    Evaluates citation grounding quality in AI-generated responses.

    For each citation [N] in the response, fetches the cited article and
    uses the LLM to determine whether the article actually supports the
    claims attributed to it.
    """

    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai"):
        super().__init__(client, model, provider)
        self.system_prompt = AgentPrompts.CITATION_QUALITY_AGENT

    def evaluate(
        self,
        ai_response: str,
        citation_urls: list[str],
        article_fetcher: ArticleFetcher | None = None,
    ) -> CitationQualityResult:
        """
        Evaluate citation quality for an AI response.

        Args:
            ai_response: The AI-generated response text with [N] markers.
            citation_urls: Ordered list of URLs where index 0 = [1], etc.
            article_fetcher: Optional ArticleFetcher instance (creates one if None).

        Returns:
            CitationQualityResult with per-citation scores and overall grounding.
        """
        if not ai_response or not citation_urls:
            logger.warning("[CitationQualityAgent] Empty response or no citation URLs")
            return CitationQualityResult()

        # Step 1: Parse citations from the AI response (no LLM call)
        parse_result = parse_citations(ai_response)
        logger.info(
            f"[CitationQualityAgent] Parsed {len(parse_result.unique_citation_indices)} "
            f"unique citations, {len(parse_result.segments)} segments, "
            f"cited={parse_result.cited_percentage():.1f}%, "
            f"uncited={parse_result.uncited_percentage():.1f}%"
        )

        if not parse_result.unique_citation_indices:
            logger.warning("[CitationQualityAgent] No citation markers found in response")
            return CitationQualityResult(
                uncited_percentage=100.0,
                cited_percentage=0.0,
            )

        if article_fetcher is None:
            article_fetcher = ArticleFetcher()

        # Step 2: Evaluate each unique citation
        # Pre-classify citations into skipped (no URL / no text) vs valid for LLM eval
        skipped_results = []
        valid_citations = []  # list of (citation_idx, url, cited_text, coverage_pct)
        for citation_idx in parse_result.unique_citation_indices:
            url_index = citation_idx - 1
            if url_index < 0 or url_index >= len(citation_urls):
                logger.warning(
                    f"[CitationQualityAgent] Citation [{citation_idx}] has no "
                    f"corresponding URL (only {len(citation_urls)} URLs provided)"
                )
                skipped_results.append(PerCitationResult(
                    citation_index=citation_idx,
                    url="",
                    support_score=0,
                    verdict="bad",
                    coverage_percentage=parse_result.coverage_percentage(citation_idx),
                    support_reasoning=f"No URL provided for citation [{citation_idx}]",
                ))
                continue

            url = citation_urls[url_index]
            coverage_pct = parse_result.coverage_percentage(citation_idx)
            cited_text = parse_result.text_for_citation(citation_idx)

            if not cited_text.strip():
                logger.warning(
                    f"[CitationQualityAgent] Citation [{citation_idx}] has no attributed text"
                )
                skipped_results.append(PerCitationResult(
                    citation_index=citation_idx,
                    url=url,
                    support_score=0,
                    verdict="bad",
                    coverage_percentage=coverage_pct,
                    support_reasoning="No text attributed to this citation",
                ))
                continue

            valid_citations.append((citation_idx, url, cited_text, coverage_pct))

        # Evaluate valid citations in parallel (typically 2–6 citations per response)
        evaluated_results = []
        if valid_citations:
            max_workers = min(6, len(valid_citations))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        self._evaluate_single_citation,
                        citation_idx, url, cited_text, coverage_pct, article_fetcher
                    ): citation_idx
                    for citation_idx, url, cited_text, coverage_pct in valid_citations
                }
                for future in concurrent.futures.as_completed(futures):
                    evaluated_results.append(future.result())

        per_citation_results = skipped_results + evaluated_results
        per_citation_results.sort(key=lambda r: r.citation_index)

        # Step 3: Aggregate
        return CitationQualityResult.from_per_citation(
            per_citation_results,
            cited_pct=parse_result.cited_percentage(),
            uncited_pct=parse_result.uncited_percentage(),
        )

    def _evaluate_single_citation(
        self,
        citation_idx: int,
        url: str,
        cited_text: str,
        coverage_pct: float,
        article_fetcher: ArticleFetcher,
    ) -> PerCitationResult:
        """Evaluate a single citation by fetching the article and calling the LLM."""
        logger.info(
            f"[CitationQualityAgent] Evaluating citation [{citation_idx}]: "
            f"{url[:80]}... (coverage={coverage_pct:.1f}%)"
        )

        # Fetch article
        article = article_fetcher.fetch(url)
        if not article.is_valid:
            logger.warning(
                f"[CitationQualityAgent] Failed to fetch [{citation_idx}]: {article.fetch_error}"
            )
            return PerCitationResult(
                citation_index=citation_idx,
                url=url,
                support_score=0,
                verdict="bad",
                coverage_percentage=coverage_pct,
                support_reasoning=f"Could not fetch article: {article.fetch_error}",
            )

        # Truncate content to avoid token limits
        article_content = article.content[:8000]

        user_message = (
            f"=== TEXT FROM AI RESPONSE (attributed to this citation) ===\n"
            f"{cited_text[:3000]}\n\n"
            f"=== ARTICLE CONTENT (URL: {url}) ===\n"
            f"Title: {article.title}\n"
            f"{article_content}\n\n"
            f"Evaluate whether this article supports the claims in the cited text. "
            f"Respond with JSON only."
        )

        try:
            self._refusal_context = {"article_url": url}
            response = self._call_llm(self.system_prompt, user_message)
            parsed = self._parse_json_response(response)
            result = PerCitationResult.from_dict(
                parsed,
                citation_index=citation_idx,
                url=url,
                coverage_percentage=coverage_pct,
            )
            logger.info(
                f"[CitationQualityAgent] [{citation_idx}] score={result.support_score}, "
                f"verdict={result.verdict}"
            )
            return result
        except Exception as e:
            logger.warning(
                f"[CitationQualityAgent] LLM evaluation failed for [{citation_idx}]: {e}"
            )
            return PerCitationResult(
                citation_index=citation_idx,
                url=url,
                support_score=0,
                verdict="bad",
                coverage_percentage=coverage_pct,
                support_reasoning=f"LLM evaluation failed: {e}",
            )
