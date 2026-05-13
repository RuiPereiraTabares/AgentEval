"""
Orchestrator Agent - Coordinates all agents and produces final evaluation report.
"""

import concurrent.futures
import json
import logging
import os

from . import BaseAgent
from .issue_parser import IssueParserAgent
from .relevance_agent import RelevanceAgent
from .completeness_agent import CompletenessAgent
from .validity_agent import ValidityAgent
from .search_agent import SearchAgent
from .gap_agent import GapAnalysisAgent
from .description_quality_agent import DescriptionQualityAgent
from .citation_quality_agent import CitationQualityAgent
from .response_quality_agent import ResponseQualityAgent
from .area_classification_agent import AreaClassificationAgent

from ..models.issue import Issue
from ..models.article import Article
from ..models.evaluation import EvaluationResult
from ..utils.article_fetcher import ArticleFetcher
from ..utils.scoring import ScoringUtils
from ..utils.prompts import AgentPrompts
from ..config.settings import THRESHOLDS


logger = logging.getLogger(__name__)


class Orchestrator(BaseAgent):
    """
    Orchestrates the multi-agent evaluation workflow.

    Coordinates all specialized agents to produce a comprehensive
    evaluation of whether an article adequately addresses a customer issue.
    """

    def __init__(
        self,
        client=None,
        model: str = "gpt-4o",
        provider: str = "mwai",
        mwai_token: str = None,
        mwai_token_is_explicit: bool | None = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            client: Existing MwaiClient instance (optional)
            model: Model to use for all agents
            provider: API provider ("mwai")
            mwai_token: MWAI bearer token (resolved automatically if not provided)
            mwai_token_is_explicit:
                Whether the provided token should be treated as a user-supplied
                static token (no MSAL refresh). When None, inferred from whether
                mwai_token was provided.
        """
        if client is None:
            from ..utils.mwai_client import MwaiClient, resolve_mwai_token
            token = resolve_mwai_token(mwai_token)
            if mwai_token_is_explicit is None:
                mwai_token_is_explicit = bool(mwai_token)
            client = MwaiClient(token=token, _via_msal=not mwai_token_is_explicit, model=model)

        super().__init__(client, model, provider)

        # Initialize all agents with same provider settings
        self.issue_parser = IssueParserAgent(client, model, provider)
        self.area_classification_agent = AreaClassificationAgent(client, model, provider)
        self.relevance_agent = RelevanceAgent(client, model, provider)
        self.completeness_agent = CompletenessAgent(client, model, provider)
        self.validity_agent = ValidityAgent(client, model, provider)
        self.search_agent = SearchAgent(client, model, provider)
        self.gap_agent = GapAnalysisAgent(client, model, provider)
        self.description_quality_agent = DescriptionQualityAgent(client, model, provider)
        self.citation_quality_agent = CitationQualityAgent(client, model, provider)
        self.response_quality_agent = ResponseQualityAgent(client, model, provider)

        # Initialize article fetcher
        self.article_fetcher = ArticleFetcher()

    def evaluate(
        self,
        customer_issue: str,
        article_url: str | None = None,
        article_urls: list[str] | None = None,
        product_info: dict | None = None,
    ) -> dict:
        """
        Perform comprehensive evaluation of article(s) for a customer issue.

        Args:
            customer_issue: The customer's issue description
            article_url: Single article URL to evaluate (optional)
            article_urls: Multiple article URLs to evaluate (optional)

        Returns:
            Complete evaluation result as dictionary
        """
        logger.info("Starting evaluation workflow")

        # Step 1: Parse the customer issue
        logger.info("Parsing customer issue...")
        issue = self.issue_parser.evaluate(customer_issue, product_info=product_info)
        logger.info(f"Issue parsed: product={issue.product}, type={issue.issue_type}")

        # Step 1a+1b: Classify area path and evaluate description quality (parallel)
        logger.info("--- Running AreaClassificationAgent + DescriptionQualityAgent (parallel) ---")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_area = executor.submit(self.area_classification_agent.classify, issue)
            future_desc = executor.submit(self.description_quality_agent.evaluate, issue)
            area_result = future_area.result()
            description_quality_result = future_desc.result()

        if area_result:
            issue.area_path = area_result["area_path"]
            issue.area_path_confidence = area_result["area_confidence"]
            logger.info(
                f"[AreaClassificationAgent] area_path='{issue.area_path}', "
                f"confidence={issue.area_path_confidence}"
            )

        reliability_threshold = THRESHOLDS.get("description_quality_reliability", 40)
        evaluation_reliability_warning = (
            description_quality_result.description_quality_score < reliability_threshold
        )
        if evaluation_reliability_warning:
            logger.warning(
                f"[DescriptionQualityAgent] LOW CONFIDENCE: description quality score "
                f"{description_quality_result.description_quality_score} < threshold {reliability_threshold}. "
                f"Evaluation reliability may be compromised."
            )
        else:
            logger.info(
                f"[DescriptionQualityAgent] Description quality OK: "
                f"score={description_quality_result.description_quality_score}, "
                f"verdict={description_quality_result.description_quality_verdict}"
            )

        # Determine which URLs to evaluate
        urls_to_evaluate = []
        if article_urls:
            urls_to_evaluate = article_urls
        elif article_url:
            urls_to_evaluate = [article_url]

        # Determine whether this case has citations
        has_citations = bool(urls_to_evaluate)

        # Handle case with no citation
        if not urls_to_evaluate:
            return self._handle_no_citation(
                issue, description_quality_result, evaluation_reliability_warning
            )

        # Step 2: Fetch and evaluate each article (parallel when multiple URLs)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(urls_to_evaluate)) as executor:
            article_evaluations = list(executor.map(
                lambda url: self._evaluate_single_article(issue, url),
                urls_to_evaluate
            ))

        best_evaluation = max(article_evaluations, key=lambda e: e["overall_score"])
        best_score = best_evaluation["overall_score"]

        # Step 3+4: Search for alternatives and/or gap analysis (parallel when both needed)
        search_result = None
        gap_result = None
        if best_score < 60:
            logger.info("Score below 60 — running Search + GapAnalysis in parallel...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_search = executor.submit(self.search_agent.evaluate, issue, best_score)
                future_gap = executor.submit(
                    self.gap_agent.evaluate,
                    issue,
                    relevance_result=best_evaluation.get("_relevance_obj"),
                    completeness_result=best_evaluation.get("_completeness_obj"),
                    validity_result=best_evaluation.get("_validity_obj"),
                )
                search_result = future_search.result()
                gap_result = future_gap.result()
        elif best_score < 70:
            logger.info("Score below threshold, searching for alternatives...")
            search_result = self.search_agent.evaluate(issue, best_score)

        # Step 5: Build final result
        result = self._build_final_result(
            issue=issue,
            article_evaluations=article_evaluations,
            best_evaluation=best_evaluation,
            search_result=search_result,
            gap_result=gap_result,
            description_quality_result=description_quality_result,
            evaluation_reliability_warning=evaluation_reliability_warning,
        )

        return result

    def evaluate_with_citations(
        self,
        customer_issue: str,
        ai_response: str,
        citation_urls: list[str],
        product_info: dict | None = None,
    ) -> dict:
        """
        Evaluate an AI response with inline citations.

        Runs:
        1. IssueParserAgent (reuse)
        2. DescriptionQualityAgent (reuse)
        3. CitationQualityAgent on the AI response + citation URLs

        Args:
            customer_issue: The customer's issue description
            ai_response: The AI-generated response with [N] citation markers
            citation_urls: Ordered list of cited URLs ([1] = index 0, etc.)
            product_info: SAP product metadata from CSV (optional)

        Returns:
            Complete evaluation result as dictionary
        """
        logger.info("Starting citation-quality evaluation workflow")

        # Step 1: Parse the customer issue
        logger.info("Parsing customer issue...")
        issue = self.issue_parser.evaluate(customer_issue, product_info=product_info)
        logger.info(f"Issue parsed: product={issue.product}, type={issue.issue_type}")

        # Step 1a+1b: Classify area path and evaluate description quality (parallel)
        logger.info("--- Running AreaClassificationAgent + DescriptionQualityAgent (parallel) ---")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_area = executor.submit(self.area_classification_agent.classify, issue)
            future_desc = executor.submit(self.description_quality_agent.evaluate, issue)
            area_result = future_area.result()
            description_quality_result = future_desc.result()

        if area_result:
            issue.area_path = area_result["area_path"]
            issue.area_path_confidence = area_result["area_confidence"]
            logger.info(
                f"[AreaClassificationAgent] area_path='{issue.area_path}', "
                f"confidence={issue.area_path_confidence}"
            )

        reliability_threshold = THRESHOLDS.get("description_quality_reliability", 40)
        evaluation_reliability_warning = (
            description_quality_result.description_quality_score < reliability_threshold
        )
        if evaluation_reliability_warning:
            logger.warning(
                f"[DescriptionQualityAgent] LOW CONFIDENCE: score "
                f"{description_quality_result.description_quality_score} < {reliability_threshold}"
            )

        # Step 3: Citation quality evaluation
        logger.info("--- Running CitationQualityAgent ---")
        citation_quality_result = self.citation_quality_agent.evaluate(
            ai_response=ai_response,
            citation_urls=citation_urls,
            article_fetcher=self.article_fetcher,
        )
        logger.info(
            f"  CitationQualityAgent result: grounding_score={citation_quality_result.overall_grounding_score}, "
            f"verdict={citation_quality_result.overall_verdict}, "
            f"good={citation_quality_result.citations_good}, "
            f"partial={citation_quality_result.citations_partial}, "
            f"bad={citation_quality_result.citations_bad}"
        )

        # Step 3b: Evaluate best citation article with R/C/V agents (+3 LLM calls)
        best_article_eval = {}
        if citation_quality_result.per_citation_results:
            best_pcr = max(
                citation_quality_result.per_citation_results,
                key=lambda r: r.support_score,
            )
            best_url = best_pcr.url
            if best_url:
                logger.info(
                    f"--- Running R/C/V on best citation [{best_pcr.citation_index}]: "
                    f"{best_url[:80]}... (support_score={best_pcr.support_score}) ---"
                )
                best_article_eval = self._evaluate_single_article(issue, best_url)

        # Step 4: Response quality evaluation (1 LLM call — reuses groundedness)
        logger.info("--- Running ResponseQualityAgent ---")
        response_quality_result = self.response_quality_agent.evaluate(
            issue=issue,
            ai_response=ai_response,
            citation_quality_result=citation_quality_result,
        )
        logger.info(
            f"  ResponseQualityAgent result: overall={response_quality_result.ai_response_quality_score}, "
            f"verdict={response_quality_result.ai_response_quality_verdict}, "
            f"response_quality={response_quality_result.response_quality_score}, "
            f"groundedness={response_quality_result.groundedness_score}, "
            f"issue_resolution={response_quality_result.issue_resolution_score}"
        )

        # Use composite response quality score as the overall score
        composite_score = response_quality_result.ai_response_quality_score

        # Build recommendation (fallback)
        recommendation = self._generate_citation_recommendation(
            issue, citation_quality_result, evaluation_reliability_warning,
            response_quality_result=response_quality_result,
        )

        # Synthesize recommendation via LLM
        citation_verdict = "adequate" if composite_score >= 70 else (
            "needs_supplementation" if composite_score >= 50 else "inadequate"
        )
        logger.info("--- Running Synthesis ---")
        synthesis = self._synthesize_recommendation(
            issue=issue,
            overall_score=composite_score,
            verdict=citation_verdict,
            evaluation_reliability_warning=evaluation_reliability_warning,
            best_evaluation=best_article_eval,
            description_quality_result=description_quality_result,
            citation_quality_result=citation_quality_result,
            response_quality_result=response_quality_result,
        )
        if synthesis.get("narrative_recommendation"):
            recommendation = synthesis["narrative_recommendation"]

        # Clean internal objects from best article evaluation
        clean_article_eval = {
            k: v for k, v in best_article_eval.items() if not k.startswith("_")
        } if best_article_eval else {}

        return EvaluationResult(
            issue_summary=issue.to_dict(),
            current_article_evaluation=clean_article_eval,
            overall_score=composite_score,
            verdict=citation_verdict,
            action_required="none" if composite_score >= 70 else "add_context",
            description_quality=description_quality_result.to_dict(),
            evaluation_reliability_warning=evaluation_reliability_warning,
            citation_quality=citation_quality_result.to_dict(),
            response_quality=response_quality_result.to_dict(),
            final_recommendation=recommendation,
            synthesis_priority=synthesis.get("synthesis_priority", ""),
            synthesis_priority_reason=synthesis.get("synthesis_priority_reason", ""),
            synthesis_pm_actions=synthesis.get("synthesis_pm_actions", []),
            synthesis_root_cause_category=synthesis.get("synthesis_root_cause_category", ""),
        ).to_dict()

    def _generate_citation_recommendation(
        self,
        issue: Issue,
        cq_result,
        evaluation_reliability_warning: bool,
        response_quality_result=None,
    ) -> str:
        """Generate recommendation for citation-quality evaluation."""
        # Use composite score when available, fall back to grounding score
        if response_quality_result is not None:
            composite = response_quality_result.ai_response_quality_score
            rq_verdict = response_quality_result.ai_response_quality_verdict
            rec = (
                f"AI response quality for this {issue.product} issue: "
                f"{rq_verdict} (score: {composite}/100). "
                f"Breakdown — Response Quality: {response_quality_result.response_quality_score}/100, "
                f"Groundedness: {response_quality_result.groundedness_score}/100, "
                f"Issue Resolution: {response_quality_result.issue_resolution_score}/100."
            )
        else:
            score = cq_result.overall_grounding_score
            verdict = cq_result.overall_verdict
            if verdict == "well_grounded":
                rec = (
                    f"The AI response for this {issue.product} issue is well-grounded "
                    f"(score: {score}/100). {cq_result.citations_good} of "
                    f"{cq_result.citations_total} citations are well-supported by their articles."
                )
            elif verdict == "partially_grounded":
                rec = (
                    f"The AI response is partially grounded (score: {score}/100). "
                    f"{cq_result.citations_partial} citations have partial support. "
                    f"Consider verifying unsupported claims."
                )
            else:
                rec = (
                    f"The AI response is poorly grounded (score: {score}/100). "
                    f"{cq_result.citations_bad} of {cq_result.citations_total} citations "
                    f"are not supported by their articles. Response reliability is low."
                )

        if cq_result.uncited_percentage > 30:
            rec += f" Note: {cq_result.uncited_percentage:.0f}% of the response has no citations."

        if evaluation_reliability_warning:
            rec = (
                "[LOW CONFIDENCE] The customer's issue description is vague or incomplete. "
                + rec
            )
        return rec

    def _evaluate_single_article(self, issue: Issue, url: str) -> dict:
        """Evaluate a single article."""
        logger.info(f"Evaluating article: {url[:80]}...")

        # Fetch article content
        article = self.article_fetcher.fetch(url)

        if not article.is_valid:
            logger.warning(f"Failed to fetch article: {article.fetch_error}")
            return {
                "url": url,
                "fetch_error": article.fetch_error,
                "overall_score": 0,
                "relevance": {"relevance_score": 0, "relevance_verdict": "irrelevant"},
                "completeness": {"completeness_score": 0, "completeness_verdict": "severely_lacking"},
                "validity": {"validity_score": 0, "validity_verdict": "invalid"}
            }

        logger.info(f"Article fetched: title='{article.title}', content_length={len(article.content)}")

        # Run R/C/V evaluation agents in parallel
        logger.info("--- Running RelevanceAgent + CompletenessAgent + ValidityAgent (parallel) ---")
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_rel = executor.submit(self.relevance_agent.evaluate, issue, article)
            future_comp = executor.submit(self.completeness_agent.evaluate, issue, article)
            future_val = executor.submit(self.validity_agent.evaluate, issue, article)
            relevance_result = future_rel.result()
            completeness_result = future_comp.result()
            validity_result = future_val.result()

        logger.info(
            f"  RelevanceAgent result: score={relevance_result.relevance_score}, "
            f"verdict={relevance_result.relevance_verdict}, "
            f"product_match={relevance_result.product_match}, "
            f"version_match={relevance_result.version_match}, "
            f"is_outdated={relevance_result.is_outdated}"
        )
        logger.info(f"  Matched aspects: {relevance_result.matched_aspects}")
        logger.info(f"  Unmatched aspects: {relevance_result.unmatched_aspects}")
        logger.info(
            f"  CompletenessAgent result: score={completeness_result.completeness_score}, "
            f"verdict={completeness_result.completeness_verdict}, "
            f"has_prerequisites={completeness_result.has_prerequisites}, "
            f"has_step_by_step={completeness_result.has_step_by_step}, "
            f"has_examples={completeness_result.has_examples}, "
            f"has_troubleshooting={completeness_result.has_troubleshooting}"
        )
        logger.info(f"  Missing elements: {completeness_result.missing_elements}")
        logger.info(
            f"  ValidityAgent result: score={validity_result.validity_score}, "
            f"verdict={validity_result.validity_verdict}, "
            f"addresses_root_cause={validity_result.addresses_root_cause}, "
            f"is_current={validity_result.is_current_solution}, "
            f"env_compatible={validity_result.environment_compatible}, "
            f"confidence={validity_result.confidence_level}"
        )
        logger.info(f"  Potential issues: {validity_result.potential_issues}")

        # Calculate overall score
        overall_score = ScoringUtils.calculate_overall_score(
            relevance_result.relevance_score,
            completeness_result.completeness_score,
            validity_result.validity_score
        )
        logger.info(
            f"--- Overall Score: {overall_score} "
            f"(relevance={relevance_result.relevance_score}*0.4 + "
            f"completeness={completeness_result.completeness_score}*0.3 + "
            f"validity={validity_result.validity_score}*0.3) ---"
        )

        return {
            "url": url,
            "title": article.title,
            "relevance": relevance_result.to_dict(),
            "completeness": completeness_result.to_dict(),
            "validity": validity_result.to_dict(),
            "overall_score": overall_score,
            # Store objects for gap analysis
            "_relevance_obj": relevance_result,
            "_completeness_obj": completeness_result,
            "_validity_obj": validity_result
        }

    def _handle_no_citation(
        self,
        issue: Issue,
        description_quality_result=None,
        evaluation_reliability_warning: bool = False,
    ) -> dict:
        """Handle case where no article citation was provided."""
        logger.info("No citation provided, searching for relevant articles...")

        # Search for relevant articles
        search_result = self.search_agent.evaluate(issue)

        # Perform gap analysis without existing article
        gap_result = self.gap_agent.evaluate(issue)

        recommendation = self._generate_no_citation_recommendation(issue, search_result)
        if evaluation_reliability_warning:
            recommendation = (
                "[LOW CONFIDENCE] The customer's issue description is vague or incomplete, "
                "reducing confidence in this evaluation. " + recommendation
            )

        # Synthesize recommendation via LLM
        logger.info("--- Running Synthesis ---")
        synthesis = self._synthesize_recommendation(
            issue=issue,
            overall_score=0,
            verdict="no_citation_provided",
            evaluation_reliability_warning=evaluation_reliability_warning,
            description_quality_result=description_quality_result,
            gap_result=gap_result,
            search_result=search_result,
        )
        if synthesis.get("narrative_recommendation"):
            recommendation = synthesis["narrative_recommendation"]

        return EvaluationResult(
            issue_summary=issue.to_dict(),
            current_article_evaluation={},
            overall_score=0,
            verdict="no_citation_provided",
            action_required="find_better_article",
            recommended_articles=[a.to_dict() for a in search_result.recommended_articles],
            content_gaps=gap_result.to_dict(),
            final_recommendation=recommendation,
            description_quality=description_quality_result.to_dict() if description_quality_result else {},
            evaluation_reliability_warning=evaluation_reliability_warning,
            synthesis_priority=synthesis.get("synthesis_priority", ""),
            synthesis_priority_reason=synthesis.get("synthesis_priority_reason", ""),
            synthesis_pm_actions=synthesis.get("synthesis_pm_actions", []),
            synthesis_root_cause_category=synthesis.get("synthesis_root_cause_category", ""),
        ).to_dict()

    def _build_final_result(
        self,
        issue: Issue,
        article_evaluations: list[dict],
        best_evaluation: dict,
        search_result=None,
        gap_result=None,
        description_quality_result=None,
        evaluation_reliability_warning: bool = False,
    ) -> dict:
        """Build the final evaluation result."""
        overall_score = best_evaluation["overall_score"] if best_evaluation else 0
        relevance_verdict = best_evaluation.get("relevance", {}).get("relevance_verdict", "poor")

        # Determine verdict
        verdict = ScoringUtils.get_overall_verdict(
            overall_score,
            relevance_verdict,
            has_article=True
        )

        logger.info(
            f"=== FINAL VERDICT: {verdict.upper()} === "
            f"(overall_score={overall_score}, relevance_verdict={relevance_verdict}, "
            f"threshold={THRESHOLDS['overall_adequate']})"
        )
        if overall_score >= THRESHOLDS["overall_adequate"]:
            if relevance_verdict in ["excellent", "good"]:
                logger.info("  Verdict reason: score >= threshold AND relevance is excellent/good")
            else:
                logger.info(
                    f"  Verdict reason: score >= threshold BUT relevance is '{relevance_verdict}' "
                    f"(not excellent/good) -> needs_supplementation"
                )
        elif overall_score >= 50:
            logger.info(f"  Verdict reason: score >= 50 but < threshold -> needs_supplementation")
        else:
            logger.info(f"  Verdict reason: score < 50 -> inadequate")

        # Determine action required
        action_required = ScoringUtils.get_action_required(
            verdict,
            has_better_alternative=search_result.better_alternative_found if search_result else False
        )
        logger.info(f"  Action required: {action_required}")

        # Clean up internal objects from evaluation
        clean_evaluations = []
        for eval_item in article_evaluations:
            clean_eval = {k: v for k, v in eval_item.items() if not k.startswith("_")}
            clean_evaluations.append(clean_eval)

        # Build primary article evaluation
        primary_eval = clean_evaluations[0] if clean_evaluations else {}

        # Generate final recommendation
        final_recommendation = self._generate_recommendation(
            issue=issue,
            verdict=verdict,
            best_evaluation=best_evaluation,
            search_result=search_result,
            evaluation_reliability_warning=evaluation_reliability_warning,
        )

        # Synthesize recommendation via LLM
        logger.info("--- Running Synthesis ---")
        synthesis = self._synthesize_recommendation(
            issue=issue,
            overall_score=overall_score,
            verdict=verdict,
            evaluation_reliability_warning=evaluation_reliability_warning,
            best_evaluation=best_evaluation,
            description_quality_result=description_quality_result,
            gap_result=gap_result,
            search_result=search_result,
        )
        # Use narrative as final_recommendation if available
        if synthesis.get("narrative_recommendation"):
            final_recommendation = synthesis["narrative_recommendation"]

        return EvaluationResult(
            issue_summary=issue.to_dict(),
            current_article_evaluation={
                "url": primary_eval.get("url", ""),
                "title": primary_eval.get("title", ""),
                "relevance": primary_eval.get("relevance", {}),
                "completeness": primary_eval.get("completeness", {}),
                "validity": primary_eval.get("validity", {}),
                "all_articles": clean_evaluations if len(clean_evaluations) > 1 else None
            },
            overall_score=overall_score,
            verdict=verdict,
            action_required=action_required,
            recommended_articles=[
                a.to_dict() for a in search_result.recommended_articles
            ] if search_result else [],
            content_gaps=gap_result.to_dict() if gap_result else {},
            final_recommendation=final_recommendation,
            description_quality=description_quality_result.to_dict() if description_quality_result else {},
            evaluation_reliability_warning=evaluation_reliability_warning,
            synthesis_priority=synthesis.get("synthesis_priority", ""),
            synthesis_priority_reason=synthesis.get("synthesis_priority_reason", ""),
            synthesis_pm_actions=synthesis.get("synthesis_pm_actions", []),
            synthesis_root_cause_category=synthesis.get("synthesis_root_cause_category", ""),
        ).to_dict()

    def _synthesize_recommendation(
        self,
        issue: Issue,
        overall_score: int,
        verdict: str,
        evaluation_reliability_warning: bool = False,
        best_evaluation: dict | None = None,
        description_quality_result=None,
        citation_quality_result=None,
        response_quality_result=None,
        gap_result=None,
        search_result=None,
    ) -> dict:
        """Synthesize all agent results into a structured recommendation via LLM.

        Returns dict with keys: synthesis_priority, synthesis_priority_reason,
        synthesis_pm_actions, synthesis_root_cause_category, narrative_recommendation.
        Falls back to auto-computed values on failure.
        """
        # Build context dict with all agent outputs
        context = {
            "issue_summary": {
                "product": issue.product,
                "issue_type": issue.issue_type,
                "severity": issue.severity,
                "keywords": issue.keywords[:5] if issue.keywords else [],
                "symptoms": issue.symptoms[:3] if issue.symptoms else [],
                "raw_description": (issue.raw_description or "")[:500],
                "error_codes": issue.error_codes if issue.error_codes else [],
                "area_path": issue.area_path or "",
                "area_path_confidence": issue.area_path_confidence,
            },
            "overall_score": overall_score,
            "verdict": verdict,
            "evaluation_reliability_warning": evaluation_reliability_warning,
        }

        # Article evaluation (R/C/V scores)
        if best_evaluation:
            rel = best_evaluation.get("relevance", {})
            comp = best_evaluation.get("completeness", {})
            val = best_evaluation.get("validity", {})
            context["article_evaluation"] = {
                "url": best_evaluation.get("url", ""),
                "title": best_evaluation.get("title", ""),
                "relevance_score": rel.get("relevance_score", 0),
                "relevance_verdict": rel.get("relevance_verdict", ""),
                "unmatched_aspects": rel.get("unmatched_aspects", [])[:3],
                "product_match": rel.get("product_match"),
                "is_outdated": rel.get("is_outdated"),
                "completeness_score": comp.get("completeness_score", 0),
                "completeness_verdict": comp.get("completeness_verdict", ""),
                "missing_elements": comp.get("missing_elements", [])[:3],
                "validity_score": val.get("validity_score", 0),
                "validity_verdict": val.get("validity_verdict", ""),
                "potential_issues": val.get("potential_issues", [])[:3],
                "addresses_root_cause": val.get("addresses_root_cause"),
            }

        # Description quality (support-readiness)
        if description_quality_result:
            dq = description_quality_result.to_dict() if hasattr(description_quality_result, "to_dict") else description_quality_result
            context["description_quality"] = {
                "score": dq.get("description_quality_score", 0),
                "verdict": dq.get("description_quality_verdict", ""),
                "missing_elements": dq.get("missing_elements", [])[:3],
            }

        # Citation quality — truncate per-citation reasoning
        if citation_quality_result:
            cq = citation_quality_result.to_dict() if hasattr(citation_quality_result, "to_dict") else citation_quality_result
            pcr_truncated = []
            for pcr in cq.get("per_citation_results", [])[:3]:
                pcr_truncated.append({
                    "url": pcr.get("url", ""),
                    "support_score": pcr.get("support_score", 0),
                    "verdict": pcr.get("verdict", ""),
                    "reasoning": (pcr.get("support_reasoning", "") or "")[:200],
                })
            context["citation_quality"] = {
                "overall_grounding_score": cq.get("overall_grounding_score", 0),
                "overall_verdict": cq.get("overall_verdict", ""),
                "citations_good": cq.get("citations_good", 0),
                "citations_partial": cq.get("citations_partial", 0),
                "citations_bad": cq.get("citations_bad", 0),
                "uncited_percentage": cq.get("uncited_percentage", 0),
                "per_citation": pcr_truncated,
            }

        # Response quality
        if response_quality_result:
            rq = response_quality_result.to_dict() if hasattr(response_quality_result, "to_dict") else response_quality_result
            context["response_quality"] = {
                "ai_response_quality_score": rq.get("ai_response_quality_score", 0),
                "ai_response_quality_verdict": rq.get("ai_response_quality_verdict", ""),
                "response_quality_score": rq.get("response_quality_score", 0),
                "groundedness_score": rq.get("groundedness_score", 0),
                "issue_resolution_score": rq.get("issue_resolution_score", 0),
                "quality_weaknesses": rq.get("quality_weaknesses", [])[:3],
            }

        # Gap analysis
        if gap_result:
            ga = gap_result.to_dict() if hasattr(gap_result, "to_dict") else gap_result
            context["gap_analysis"] = {
                "documentation_gaps": ga.get("documentation_gaps", []),
                "suggested_content_outline": ga.get("suggested_content_outline", []),
                "required_expertise": ga.get("required_expertise", []),
                "estimated_effort": ga.get("estimated_effort", ""),
                "priority": ga.get("priority", ""),
                "recommendation": ga.get("recommendation", ""),
            }

        # Search results
        if search_result:
            sr = search_result
            if hasattr(sr, "recommended_articles"):
                context["search_results"] = {
                    "better_alternative_found": sr.better_alternative_found,
                    "search_terms": sr.search_terms_used[:2] if sr.search_terms_used else [],
                    "recommended_articles": [
                        {
                            "title": a.title,
                            "url": a.url,
                            "relevance_reason": a.relevance_reason,
                            "estimated_match_score": a.estimated_match_score,
                        }
                        for a in sr.recommended_articles[:3]
                    ],
                }

        # Call LLM
        try:
            user_message = json.dumps(context, indent=2, default=str)
            response = self._call_llm(AgentPrompts.ORCHESTRATOR_SUMMARY, user_message)
            parsed = self._parse_json_response(response)

            # Validate required keys and enum values
            valid_priorities = {"red", "yellow", "green"}
            valid_root_causes = {
                "content_gap", "wrong_citation",
                "article_outdated", "citation_quality_low", "response_quality_low",
                "adequate", "no_content",
            }

            priority = str(parsed.get("priority", "")).lower().strip()
            if priority not in valid_priorities:
                raise ValueError(f"Invalid priority: {priority}")

            root_cause = str(parsed.get("root_cause_category", "")).lower().strip()
            if root_cause not in valid_root_causes:
                raise ValueError(f"Invalid root_cause_category: {root_cause}")

            pm_actions = parsed.get("pm_actions", [])
            if not isinstance(pm_actions, list):
                pm_actions = [str(pm_actions)]

            narrative = str(parsed.get("narrative_recommendation", ""))
            priority_reason = str(parsed.get("priority_reason", ""))

            logger.info(
                f"[Orchestrator] Synthesis complete: priority={priority.upper()}, "
                f"root_cause={root_cause}, actions={len(pm_actions)}"
            )

            return {
                "synthesis_priority": priority,
                "synthesis_priority_reason": priority_reason,
                "synthesis_pm_actions": pm_actions,
                "synthesis_root_cause_category": root_cause,
                "narrative_recommendation": narrative,
            }

        except Exception as e:
            logger.warning(f"[Orchestrator] Synthesis LLM call failed, using fallback: {e}")
            return self._synthesis_fallback(overall_score, verdict)

    def _synthesis_fallback(self, overall_score: int, verdict: str) -> dict:
        """Auto-compute synthesis fields when LLM call fails."""
        if overall_score < 40 or verdict in ("inadequate", "no_citation_provided"):
            priority = "red"
        elif overall_score < 70 or verdict == "needs_supplementation":
            priority = "yellow"
        else:
            priority = "green"

        root_cause_map = {
            "adequate": "adequate",
            "no_citation_provided": "no_content",
            "needs_supplementation": "content_gap",
            "inadequate": "content_gap",
        }

        return {
            "synthesis_priority": priority,
            "synthesis_priority_reason": f"Auto-computed from overall_score={overall_score}, verdict={verdict}",
            "synthesis_pm_actions": [],
            "synthesis_root_cause_category": root_cause_map.get(verdict, "content_gap"),
            "narrative_recommendation": "",
        }

    def _generate_recommendation(
        self,
        issue: Issue,
        verdict: str,
        best_evaluation: dict,
        search_result=None,
        evaluation_reliability_warning: bool = False,
    ) -> str:
        """Generate human-readable recommendation."""
        score = best_evaluation.get("overall_score", 0) if best_evaluation else 0
        relevance_verdict = best_evaluation.get("relevance", {}).get("relevance_verdict", "unknown")

        if verdict == "adequate":
            recommendation = (
                f"The provided article adequately addresses the {issue.product} issue. "
                f"Overall score: {score}/100. The article is relevant and provides "
                f"sufficient information for resolution."
            )

        elif verdict == "needs_supplementation":
            missing = best_evaluation.get("completeness", {}).get("missing_elements", [])
            missing_str = ", ".join(missing[:3]) if missing else "additional context"
            recommendation = (
                f"The article partially addresses the issue (score: {score}/100) but needs "
                f"supplementation. Missing: {missing_str}. "
                f"Consider providing additional resources or context."
            )

        elif verdict == "inadequate":
            unmatched = best_evaluation.get("relevance", {}).get("unmatched_aspects", [])
            unmatched_str = ", ".join(unmatched[:3]) if unmatched else "key aspects of the issue"
            recommendation = (
                f"The article does not adequately address the issue (score: {score}/100). "
                f"Not covered: {unmatched_str}. "
            )
            if search_result and search_result.search_terms_used:
                recommendation += f"Suggested search: '{search_result.search_terms_used[0]}'"

        else:
            recommendation = (
                f"No article was provided for evaluation. "
                f"Search for relevant documentation using: {issue.get_search_query()}"
            )

        if evaluation_reliability_warning:
            recommendation = (
                "[LOW CONFIDENCE] The customer's issue description is vague or incomplete, "
                "reducing confidence in this evaluation. " + recommendation
            )

        return recommendation

    def _generate_no_citation_recommendation(self, issue: Issue, search_result) -> str:
        """Generate recommendation when no citation provided."""
        search_terms = search_result.search_terms_used[:2] if search_result else []
        return (
            f"No article citation was provided for this {issue.product} {issue.issue_type} issue. "
            f"Recommended searches: {', '.join(search_terms) if search_terms else issue.get_search_query()}. "
            f"Consider searching support.microsoft.com and learn.microsoft.com for relevant documentation."
        )
