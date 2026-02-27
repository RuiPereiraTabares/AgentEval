"""
Semantic Kernel Plugin for Article Evaluation.

Exposes article evaluation capabilities as SK kernel functions that can be
used in SK applications, pipelines, and planners.
"""

import json
from typing import Annotated, Optional

from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function

from ..models.issue import Issue
from ..models.article import Article
from ..utils.article_fetcher import ArticleFetcher
from ..utils.scoring import ScoringUtils

from .llm_adapter import SKChatCompletionAdapter


class ArticleEvaluationPlugin:
    """
    Semantic Kernel plugin that provides article evaluation capabilities.

    This plugin exposes 7 kernel functions for evaluating Microsoft support
    articles against customer issues:
    - parse_issue: Parse customer issue to structured data
    - evaluate_relevance: Score article relevance (0-100)
    - evaluate_completeness: Score article completeness (0-100)
    - evaluate_validity: Score solution validity (0-100)
    - search_articles: Generate search queries for alternatives
    - analyze_gaps: Identify documentation gaps
    - evaluate_article: Full orchestrated evaluation
    """

    def __init__(self, kernel: Kernel, service_id: Optional[str] = None):
        """
        Initialize the ArticleEvaluationPlugin.

        Args:
            kernel: Configured Semantic Kernel instance
            service_id: Optional service ID for the chat completion service
        """
        self.kernel = kernel
        self.adapter = SKChatCompletionAdapter(kernel, service_id)
        self.article_fetcher = ArticleFetcher()

        # Import prompts
        from ..utils.prompts import AgentPrompts
        self.prompts = AgentPrompts

    def _call_llm(self, system_prompt: str, user_message: str) -> str:
        """Make an LLM call via the SK adapter."""
        return self.adapter.call(system_prompt, user_message)

    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        import re

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError(f"Could not parse JSON from response: {response[:200]}")

    @kernel_function(
        name="parse_issue",
        description="Parse a customer issue description into structured data including product, symptoms, error codes, and keywords."
    )
    def parse_issue(
        self,
        issue_description: Annotated[str, "The raw customer issue description text"]
    ) -> Annotated[str, "JSON string with parsed issue data"]:
        """
        Parse a customer issue description into structured data.

        Args:
            issue_description: The raw customer issue text

        Returns:
            JSON string containing parsed issue with product, symptoms,
            error codes, keywords, and other relevant information
        """
        if not issue_description or not issue_description.strip():
            return json.dumps({
                "product": "Unknown",
                "symptoms": ["No issue description provided"],
                "issue_type": "unknown",
                "severity": "low",
                "error_codes": [],
                "keywords": []
            })

        user_message = f"""Parse the following customer issue:

{issue_description}

Extract all relevant information and respond with JSON only."""

        try:
            response = self._call_llm(self.prompts.ISSUE_PARSER, user_message)
            parsed_data = self._parse_json_response(response)
            parsed_data["raw_description"] = issue_description
            return json.dumps(parsed_data)
        except Exception as e:
            # Return basic parsed issue on failure
            return json.dumps({
                "product": "Microsoft 365",
                "symptoms": [issue_description[:200]],
                "issue_type": "troubleshooting",
                "severity": "medium",
                "error_codes": [],
                "keywords": [],
                "raw_description": issue_description,
                "parse_error": str(e)
            })

    @kernel_function(
        name="evaluate_relevance",
        description="Evaluate how relevant a support article is to a customer issue. Returns a score from 0-100."
    )
    def evaluate_relevance(
        self,
        issue_json: Annotated[str, "JSON string of parsed issue (from parse_issue)"],
        article_url: Annotated[str, "URL of the article to evaluate"]
    ) -> Annotated[str, "JSON string with relevance score and verdict"]:
        """
        Evaluate the relevance of an article to a customer issue.

        Args:
            issue_json: JSON string of parsed issue data
            article_url: URL of the article to evaluate

        Returns:
            JSON string with relevance_score (0-100), matched_aspects,
            unmatched_aspects, and relevance_verdict
        """
        try:
            issue_data = json.loads(issue_json)
            issue = Issue.from_dict(issue_data)
            issue.raw_description = issue_data.get("raw_description", "")
        except (json.JSONDecodeError, Exception) as e:
            return json.dumps({
                "relevance_score": 0,
                "relevance_verdict": "error",
                "error": f"Failed to parse issue JSON: {e}"
            })

        # Fetch the article
        article = self.article_fetcher.fetch(article_url)
        if not article.is_valid:
            return json.dumps({
                "relevance_score": 0,
                "matched_aspects": [],
                "unmatched_aspects": ["Article could not be fetched"],
                "relevance_verdict": "irrelevant",
                "fetch_error": article.fetch_error
            })

        user_message = f"""Evaluate the relevance of this article to the customer issue.

## Customer Issue (Parsed)
```json
{json.dumps(issue.to_dict(), indent=2)}
```

## Article Information
**Title:** {article.title}
**URL:** {article.url}
**Last Updated:** {article.last_updated or "Unknown"}
**Applies To:** {', '.join(article.applies_to) if article.applies_to else "Not specified"}

## Article Content
{article.content[:8000]}

Evaluate and respond with JSON only."""

        try:
            response = self._call_llm(self.prompts.RELEVANCE_AGENT, user_message)
            return response
        except Exception as e:
            return json.dumps({
                "relevance_score": 30,
                "matched_aspects": [],
                "unmatched_aspects": ["Evaluation failed"],
                "relevance_verdict": "poor",
                "error": str(e)
            })

    @kernel_function(
        name="evaluate_completeness",
        description="Evaluate how complete an article is for solving a customer issue. Returns a score from 0-100."
    )
    def evaluate_completeness(
        self,
        issue_json: Annotated[str, "JSON string of parsed issue (from parse_issue)"],
        article_url: Annotated[str, "URL of the article to evaluate"]
    ) -> Annotated[str, "JSON string with completeness score and verdict"]:
        """
        Evaluate the completeness of an article.

        Args:
            issue_json: JSON string of parsed issue data
            article_url: URL of the article to evaluate

        Returns:
            JSON string with completeness_score (0-100), has_prerequisites,
            has_step_by_step, missing_elements, and completeness_verdict
        """
        try:
            issue_data = json.loads(issue_json)
            issue = Issue.from_dict(issue_data)
        except (json.JSONDecodeError, Exception) as e:
            return json.dumps({
                "completeness_score": 0,
                "completeness_verdict": "error",
                "error": f"Failed to parse issue JSON: {e}"
            })

        # Fetch the article
        article = self.article_fetcher.fetch(article_url)
        if not article.is_valid:
            return json.dumps({
                "completeness_score": 0,
                "has_prerequisites": False,
                "has_step_by_step": False,
                "missing_elements": ["Article could not be fetched"],
                "completeness_verdict": "severely_lacking",
                "fetch_error": article.fetch_error
            })

        user_message = f"""Evaluate the completeness of this article for solving the customer's issue.

## Customer Issue Context
- Product: {issue.product}
- Issue Type: {issue.issue_type}
- Symptoms: {', '.join(issue.symptoms[:5])}

## Article Information
**Title:** {article.title}
**Type:** {article.article_type}
**Has Prerequisites Section:** {bool(article.prerequisites)}
**Number of Steps:** {len(article.steps)}

## Article Content
{article.content[:8000]}

Evaluate completeness and respond with JSON only."""

        try:
            response = self._call_llm(self.prompts.COMPLETENESS_AGENT, user_message)
            return response
        except Exception as e:
            return json.dumps({
                "completeness_score": 40,
                "has_prerequisites": False,
                "has_step_by_step": False,
                "missing_elements": ["Evaluation failed"],
                "completeness_verdict": "incomplete",
                "error": str(e)
            })

    @kernel_function(
        name="evaluate_validity",
        description="Evaluate if an article's solution would actually work for a customer issue. Returns a score from 0-100."
    )
    def evaluate_validity(
        self,
        issue_json: Annotated[str, "JSON string of parsed issue (from parse_issue)"],
        article_url: Annotated[str, "URL of the article to evaluate"]
    ) -> Annotated[str, "JSON string with validity score and verdict"]:
        """
        Evaluate whether an article's solution would actually work.

        Args:
            issue_json: JSON string of parsed issue data
            article_url: URL of the article to evaluate

        Returns:
            JSON string with validity_score (0-100), addresses_root_cause,
            is_current_solution, potential_issues, and validity_verdict
        """
        try:
            issue_data = json.loads(issue_json)
            issue = Issue.from_dict(issue_data)
            issue.raw_description = issue_data.get("raw_description", "")
        except (json.JSONDecodeError, Exception) as e:
            return json.dumps({
                "validity_score": 0,
                "validity_verdict": "error",
                "error": f"Failed to parse issue JSON: {e}"
            })

        # Fetch the article
        article = self.article_fetcher.fetch(article_url)
        if not article.is_valid:
            return json.dumps({
                "validity_score": 0,
                "addresses_root_cause": False,
                "is_current_solution": False,
                "potential_issues": ["Article could not be fetched"],
                "validity_verdict": "invalid",
                "fetch_error": article.fetch_error
            })

        user_message = f"""Evaluate whether this article's solution would actually solve the customer's problem.

## Customer Issue
**Product:** {issue.product}
**Version:** {issue.version or "Not specified"}
**Issue Type:** {issue.issue_type}
**Error Codes:** {', '.join(issue.error_codes) if issue.error_codes else "None"}
**Symptoms:** {', '.join(issue.symptoms[:5])}
**Environment:** {json.dumps(issue.environment) if issue.environment else "Not specified"}

**Original Description:**
{issue.raw_description[:1000]}

## Article Solution
**Title:** {article.title}
**Last Updated:** {article.last_updated or "Unknown"}

**Content:**
{article.content[:8000]}

Evaluate validity and respond with JSON only."""

        try:
            response = self._call_llm(self.prompts.VALIDITY_AGENT, user_message)
            return response
        except Exception as e:
            return json.dumps({
                "validity_score": 50,
                "addresses_root_cause": False,
                "is_current_solution": True,
                "potential_issues": ["Evaluation failed"],
                "validity_verdict": "uncertain",
                "error": str(e)
            })

    @kernel_function(
        name="search_articles",
        description="Generate optimized search queries to find relevant Microsoft support articles for a customer issue."
    )
    def search_articles(
        self,
        issue_json: Annotated[str, "JSON string of parsed issue (from parse_issue)"]
    ) -> Annotated[str, "JSON string with search queries and recommended search URLs"]:
        """
        Generate search queries for finding relevant articles.

        Args:
            issue_json: JSON string of parsed issue data

        Returns:
            JSON string with search_queries, recommended_search_urls,
            and suggested_domains
        """
        try:
            issue_data = json.loads(issue_json)
            issue = Issue.from_dict(issue_data)
            issue.raw_description = issue_data.get("raw_description", "")
        except (json.JSONDecodeError, Exception) as e:
            return json.dumps({
                "search_queries": [],
                "error": f"Failed to parse issue JSON: {e}"
            })

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
            response = self._call_llm(self.prompts.SEARCH_AGENT, user_message)
            parsed = self._parse_json_response(response)

            # Add search URLs
            queries = parsed.get("search_queries", [])
            search_urls = {
                "support.microsoft.com": [
                    f"https://support.microsoft.com/search/results?query={q.replace(' ', '+')}"
                    for q in queries[:5]
                ],
                "learn.microsoft.com": [
                    f"https://learn.microsoft.com/search/?terms={q.replace(' ', '+')}"
                    for q in queries[:5]
                ]
            }
            parsed["recommended_search_urls"] = search_urls

            return json.dumps(parsed)
        except Exception as e:
            # Generate fallback queries
            fallback_queries = [
                f"{issue.product} {issue.issue_type}",
                f"{issue.product} {issue.symptoms[0][:50]}" if issue.symptoms else f"{issue.product} help"
            ]
            if issue.error_codes:
                fallback_queries.insert(0, f"{issue.product} {issue.error_codes[0]}")

            return json.dumps({
                "search_queries": fallback_queries,
                "recommended_search_urls": {
                    "support.microsoft.com": [
                        f"https://support.microsoft.com/search/results?query={q.replace(' ', '+')}"
                        for q in fallback_queries
                    ]
                },
                "error": str(e)
            })

    @kernel_function(
        name="analyze_gaps",
        description="Identify documentation gaps and recommend content improvements based on evaluation results."
    )
    def analyze_gaps(
        self,
        issue_json: Annotated[str, "JSON string of parsed issue (from parse_issue)"],
        relevance_json: Annotated[str, "JSON string from evaluate_relevance (optional)"] = "{}",
        completeness_json: Annotated[str, "JSON string from evaluate_completeness (optional)"] = "{}",
        validity_json: Annotated[str, "JSON string from evaluate_validity (optional)"] = "{}"
    ) -> Annotated[str, "JSON string with documentation gaps and recommendations"]:
        """
        Analyze documentation gaps based on evaluation results.

        Args:
            issue_json: JSON string of parsed issue data
            relevance_json: Optional JSON string from relevance evaluation
            completeness_json: Optional JSON string from completeness evaluation
            validity_json: Optional JSON string from validity evaluation

        Returns:
            JSON string with documentation_gaps, suggested_content_outline,
            priority, and recommendation
        """
        try:
            issue_data = json.loads(issue_json)
            issue = Issue.from_dict(issue_data)
            issue.raw_description = issue_data.get("raw_description", "")
        except (json.JSONDecodeError, Exception) as e:
            return json.dumps({
                "documentation_gaps": [],
                "error": f"Failed to parse issue JSON: {e}"
            })

        # Parse evaluation results
        try:
            relevance = json.loads(relevance_json) if relevance_json else {}
            completeness = json.loads(completeness_json) if completeness_json else {}
            validity = json.loads(validity_json) if validity_json else {}
        except json.JSONDecodeError:
            relevance, completeness, validity = {}, {}, {}

        # Build evaluation context
        eval_context_parts = []
        if relevance and relevance.get("relevance_score"):
            eval_context_parts.append(f"""**Relevance Evaluation:**
- Score: {relevance.get('relevance_score', 0)}/100
- Verdict: {relevance.get('relevance_verdict', 'unknown')}
- Unmatched aspects: {', '.join(relevance.get('unmatched_aspects', [])) or 'None'}""")

        if completeness and completeness.get("completeness_score"):
            eval_context_parts.append(f"""**Completeness Evaluation:**
- Score: {completeness.get('completeness_score', 0)}/100
- Verdict: {completeness.get('completeness_verdict', 'unknown')}
- Missing elements: {', '.join(completeness.get('missing_elements', [])) or 'None'}""")

        if validity and validity.get("validity_score"):
            eval_context_parts.append(f"""**Validity Evaluation:**
- Score: {validity.get('validity_score', 0)}/100
- Verdict: {validity.get('validity_verdict', 'unknown')}
- Potential issues: {', '.join(validity.get('potential_issues', [])) or 'None'}""")

        evaluation_context = "\n\n".join(eval_context_parts) or "No article evaluation available"

        user_message = f"""Analyze documentation gaps for this customer issue.

## Customer Issue
**Product:** {issue.product}
**Version:** {issue.version or "Not specified"}
**Issue Type:** {issue.issue_type}
**Error Codes:** {', '.join(issue.error_codes) if issue.error_codes else "None"}
**Symptoms:** {', '.join(issue.symptoms[:5])}

**Original Description:**
{issue.raw_description[:1500]}

## Current Article Evaluation Results
{evaluation_context}

Identify gaps and recommend documentation improvements."""

        try:
            response = self._call_llm(self.prompts.GAP_ANALYSIS_AGENT, user_message)
            return response
        except Exception as e:
            # Generate basic gap analysis from evaluation data
            gaps = []
            if relevance:
                gaps.extend(relevance.get("unmatched_aspects", []))
            if completeness:
                gaps.extend(completeness.get("missing_elements", []))
            if validity:
                gaps.extend(validity.get("potential_issues", []))

            return json.dumps({
                "documentation_gaps": gaps[:10],
                "suggested_content_outline": [
                    "Overview of the issue",
                    "Prerequisites and requirements",
                    "Step-by-step resolution",
                    "Verification steps",
                    "Troubleshooting common problems"
                ],
                "priority": "medium",
                "recommendation": "augment_existing",
                "error": str(e)
            })

    @kernel_function(
        name="evaluate_article",
        description="Perform a full evaluation of an article against a customer issue, including relevance, completeness, validity, and recommendations."
    )
    def evaluate_article(
        self,
        customer_issue: Annotated[str, "The customer's issue description"],
        article_url: Annotated[str, "URL of the article to evaluate"]
    ) -> Annotated[str, "JSON string with complete evaluation results"]:
        """
        Perform complete article evaluation with all metrics.

        This is the main orchestrated evaluation that combines all other
        kernel functions into a single comprehensive evaluation.

        Args:
            customer_issue: Raw customer issue description
            article_url: URL of the article to evaluate

        Returns:
            JSON string with complete evaluation including scores,
            verdicts, recommendations, and potential alternatives
        """
        # Step 1: Parse the issue
        issue_json = self.parse_issue(customer_issue)
        issue_data = json.loads(issue_json)

        # Step 2: Fetch and check article
        article = self.article_fetcher.fetch(article_url)
        if not article.is_valid:
            # Search for alternatives if article can't be fetched
            search_json = self.search_articles(issue_json)
            search_data = json.loads(search_json)

            return json.dumps({
                "issue_summary": issue_data,
                "article_url": article_url,
                "fetch_error": article.fetch_error,
                "overall_score": 0,
                "verdict": "article_unavailable",
                "action_required": "find_article",
                "search_suggestions": search_data.get("search_queries", []),
                "search_urls": search_data.get("recommended_search_urls", {})
            })

        # Step 3: Run evaluations
        relevance_json = self.evaluate_relevance(issue_json, article_url)
        completeness_json = self.evaluate_completeness(issue_json, article_url)
        validity_json = self.evaluate_validity(issue_json, article_url)

        # Parse results
        try:
            relevance = json.loads(relevance_json)
            completeness = json.loads(completeness_json)
            validity = json.loads(validity_json)
        except json.JSONDecodeError:
            relevance, completeness, validity = {}, {}, {}

        # Step 4: Calculate overall score
        relevance_score = relevance.get("relevance_score", 0)
        completeness_score = completeness.get("completeness_score", 0)
        validity_score = validity.get("validity_score", 0)

        overall_score = ScoringUtils.calculate_overall_score(
            relevance_score, completeness_score, validity_score
        )

        # Step 5: Determine verdict and action
        verdict = ScoringUtils.get_overall_verdict(
            overall_score,
            relevance.get("relevance_verdict", "poor"),
            has_article=True
        )

        # Step 6: Search for alternatives if score is low
        search_data = {}
        if overall_score < 70:
            search_json = self.search_articles(issue_json)
            search_data = json.loads(search_json)

        # Step 7: Gap analysis if score is very low
        gap_data = {}
        if overall_score < 60:
            gap_json = self.analyze_gaps(
                issue_json, relevance_json, completeness_json, validity_json
            )
            gap_data = json.loads(gap_json)

        # Step 8: Determine action required
        action_required = ScoringUtils.get_action_required(
            verdict,
            has_better_alternative=bool(search_data.get("search_queries"))
        )

        # Build final result
        result = {
            "issue_summary": issue_data,
            "current_article_evaluation": {
                "url": article_url,
                "title": article.title,
                "relevance": relevance,
                "completeness": completeness,
                "validity": validity
            },
            "overall_score": overall_score,
            "verdict": verdict,
            "action_required": action_required,
            "final_recommendation": self._generate_recommendation(
                issue_data, verdict, overall_score, relevance, search_data
            )
        }

        if search_data:
            result["recommended_articles"] = search_data.get("search_queries", [])
            result["search_urls"] = search_data.get("recommended_search_urls", {})

        if gap_data:
            result["content_gaps"] = gap_data

        return json.dumps(result)

    def _generate_recommendation(
        self,
        issue: dict,
        verdict: str,
        score: int,
        relevance: dict,
        search_data: dict
    ) -> str:
        """Generate human-readable recommendation."""
        product = issue.get("product", "the product")

        if verdict == "adequate":
            return (
                f"The provided article adequately addresses the {product} issue. "
                f"Overall score: {score}/100. The article is relevant and provides "
                f"sufficient information for resolution."
            )
        elif verdict == "needs_supplementation":
            return (
                f"The article partially addresses the issue (score: {score}/100) but needs "
                f"supplementation. Consider providing additional resources or context."
            )
        elif verdict == "inadequate":
            unmatched = relevance.get("unmatched_aspects", [])[:3]
            unmatched_str = ", ".join(unmatched) if unmatched else "key aspects of the issue"
            recommendation = (
                f"The article does not adequately address the issue (score: {score}/100). "
                f"Not covered: {unmatched_str}. "
            )
            if search_data and search_data.get("search_queries"):
                recommendation += f"Suggested search: '{search_data['search_queries'][0]}'"
            return recommendation
        else:
            return (
                f"Evaluation could not be completed. "
                f"Search for relevant documentation for {product}."
            )
