"""
Orchestrator Agent - Coordinates all agents and produces final evaluation report.
"""

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
from .transfer_reason_agent import TransferReasonAgent

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
        api_key: str = None,
        client=None,
        model: str = "gpt-4o",
        provider: str = "openai",
        base_url: str = None,
        mwai_token: str = None
    ):
        """
        Initialize the orchestrator.

        Args:
            api_key: API key (if client not provided)
            client: Existing client instance (OpenAI, Anthropic, or MwaiClient)
            model: Model to use for all agents
            provider: API provider ("openai", "anthropic", or "mwai")
            base_url: Custom base URL for API (for proxies/custom endpoints)
            mwai_token: MWAI bearer token (required when provider is "mwai")
        """
        if client is None:
            if provider == "mwai":
                from ..utils.mwai_client import MwaiClient, resolve_mwai_token
                token = resolve_mwai_token(mwai_token)
                client = MwaiClient(token=token)
            elif provider == "openai":
                from openai import OpenAI
                if api_key is None:
                    api_key = os.environ.get("OPENAI_API_KEY")
                if base_url:
                    client = OpenAI(api_key=api_key, base_url=base_url)
                else:
                    client = OpenAI(api_key=api_key)
            else:
                from anthropic import Anthropic
                if api_key is None:
                    api_key = os.environ.get("ANTHROPIC_API_KEY")
                client = Anthropic(api_key=api_key)

        super().__init__(client, model, provider)

        # Initialize all agents with same provider settings
        self.issue_parser = IssueParserAgent(client, model, provider)
        self.relevance_agent = RelevanceAgent(client, model, provider)
        self.completeness_agent = CompletenessAgent(client, model, provider)
        self.validity_agent = ValidityAgent(client, model, provider)
        self.search_agent = SearchAgent(client, model, provider)
        self.gap_agent = GapAnalysisAgent(client, model, provider)
        self.description_quality_agent = DescriptionQualityAgent(client, model, provider)
        self.transfer_reason_agent = TransferReasonAgent(client, model, provider)

        # Initialize article fetcher
        self.article_fetcher = ArticleFetcher()

    def evaluate(
        self,
        customer_issue: str,
        article_url: str | None = None,
        article_urls: list[str] | None = None,
        product_info: dict | None = None,
        transfer_metadata: dict | None = None,
    ) -> dict:
        """
        Perform comprehensive evaluation of article(s) for a customer issue.

        Args:
            customer_issue: The customer's issue description
            article_url: Single article URL to evaluate (optional)
            article_urls: Multiple article URLs to evaluate (optional)
            transfer_metadata: Dict with 'transferred', 'sr_status', 'reopened' from CSV

        Returns:
            Complete evaluation result as dictionary
        """
        logger.info("Starting evaluation workflow")

        # Step 1: Parse the customer issue
        logger.info("Parsing customer issue...")
        issue = self.issue_parser.evaluate(customer_issue, product_info=product_info)
        logger.info(f"Issue parsed: product={issue.product}, type={issue.issue_type}")

        # Inject transfer metadata into issue
        if transfer_metadata:
            issue.transferred = transfer_metadata.get("transferred")
            issue.sr_status = transfer_metadata.get("sr_status", "")
            issue.reopened = transfer_metadata.get("reopened")

        # Step 1b: Evaluate description quality (KT framework)
        logger.info("--- Running DescriptionQualityAgent ---")
        description_quality_result = self.description_quality_agent.evaluate(issue)
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

        # Step 2: Fetch and evaluate each article
        article_evaluations = []
        best_evaluation = None
        best_score = -1

        for url in urls_to_evaluate:
            eval_result = self._evaluate_single_article(issue, url)
            article_evaluations.append(eval_result)

            if eval_result["overall_score"] > best_score:
                best_score = eval_result["overall_score"]
                best_evaluation = eval_result

        # Step 3: Determine if we need to search for better articles
        search_result = None
        if best_score < 70:
            logger.info("Score below threshold, searching for alternatives...")
            search_result = self.search_agent.evaluate(issue, best_score)

        # Step 4: Perform gap analysis if needed
        gap_result = None
        if best_score < 60:
            logger.info("Performing gap analysis...")
            gap_result = self.gap_agent.evaluate(
                issue,
                relevance_result=best_evaluation.get("_relevance_obj"),
                completeness_result=best_evaluation.get("_completeness_obj"),
                validity_result=best_evaluation.get("_validity_obj")
            )

        # Step 5: Build final result
        result = self._build_final_result(
            issue=issue,
            article_evaluations=article_evaluations,
            best_evaluation=best_evaluation,
            search_result=search_result,
            gap_result=gap_result,
            description_quality_result=description_quality_result,
            evaluation_reliability_warning=evaluation_reliability_warning,
            contains_citations=has_citations,
        )

        return result

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

        # Run evaluation agents
        logger.info("--- Running RelevanceAgent ---")
        relevance_result = self.relevance_agent.evaluate(issue, article)
        logger.info(
            f"  RelevanceAgent result: score={relevance_result.relevance_score}, "
            f"verdict={relevance_result.relevance_verdict}, "
            f"product_match={relevance_result.product_match}, "
            f"version_match={relevance_result.version_match}, "
            f"is_outdated={relevance_result.is_outdated}"
        )
        logger.info(f"  Matched aspects: {relevance_result.matched_aspects}")
        logger.info(f"  Unmatched aspects: {relevance_result.unmatched_aspects}")

        logger.info("--- Running CompletenessAgent ---")
        completeness_result = self.completeness_agent.evaluate(issue, article)
        logger.info(
            f"  CompletenessAgent result: score={completeness_result.completeness_score}, "
            f"verdict={completeness_result.completeness_verdict}, "
            f"has_prerequisites={completeness_result.has_prerequisites}, "
            f"has_step_by_step={completeness_result.has_step_by_step}, "
            f"has_examples={completeness_result.has_examples}, "
            f"has_troubleshooting={completeness_result.has_troubleshooting}"
        )
        logger.info(f"  Missing elements: {completeness_result.missing_elements}")

        logger.info("--- Running ValidityAgent ---")
        validity_result = self.validity_agent.evaluate(issue, article)
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

        # Run TransferReasonAgent LAST
        logger.info("--- Running TransferReasonAgent ---")
        transfer_result = self.transfer_reason_agent.evaluate(
            issue=issue,
            description_quality_result=description_quality_result,
            overall_score=0,
            relevance_score=0,
            contains_citations=False,
            verdict="no_citation_provided",
        )
        logger.info(
            f"  TransferReasonAgent result: reason={transfer_result.transfer_reason}, "
            f"confidence={transfer_result.confidence}"
        )

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
            transfer_analysis=transfer_result.to_dict(),
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
        contains_citations: bool = False,
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

        # Run TransferReasonAgent LAST
        relevance_score = best_evaluation.get("relevance", {}).get("relevance_score", 0) if best_evaluation else 0
        logger.info("--- Running TransferReasonAgent ---")
        transfer_result = self.transfer_reason_agent.evaluate(
            issue=issue,
            description_quality_result=description_quality_result,
            overall_score=overall_score,
            relevance_score=relevance_score,
            contains_citations=contains_citations,
            verdict=verdict,
        )
        logger.info(
            f"  TransferReasonAgent result: reason={transfer_result.transfer_reason}, "
            f"confidence={transfer_result.confidence}"
        )

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
            transfer_analysis=transfer_result.to_dict(),
        ).to_dict()

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
