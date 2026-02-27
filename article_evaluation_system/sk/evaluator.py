"""
Semantic Kernel-based Article Evaluator.

Provides a drop-in replacement for ArticleEvaluator that uses Semantic Kernel
for LLM interactions, enabling support for Azure OpenAI and other SK providers.
"""

import json
from typing import Optional, Callable

from semantic_kernel import Kernel

from .plugin import ArticleEvaluationPlugin
from .llm_adapter import create_openai_kernel, create_azure_openai_kernel, create_anthropic_kernel


class SemanticKernelEvaluator:
    """
    Drop-in replacement for ArticleEvaluator using Semantic Kernel.

    This evaluator provides the same API as ArticleEvaluator but uses
    Semantic Kernel for LLM interactions, enabling:
    - OpenAI support (via SK)
    - Azure OpenAI support
    - Anthropic/Claude support
    - Custom SK configurations
    - Plugin-based architecture

    Usage:
        # OpenAI
        evaluator = SemanticKernelEvaluator(
            api_key="sk-...",
            model="gpt-4o",
            provider="openai"
        )

        # Azure OpenAI
        evaluator = SemanticKernelEvaluator(
            api_key="azure-key",
            provider="azure",
            azure_endpoint="https://your-resource.openai.azure.com",
            azure_deployment="gpt-4"
        )

        # Anthropic/Claude
        evaluator = SemanticKernelEvaluator(
            api_key="your-anthropic-key",
            model="claude-sonnet-4-20250514",
            provider="anthropic"
        )

        # Pre-configured kernel
        evaluator = SemanticKernelEvaluator(kernel=my_kernel)

        # Same API as ArticleEvaluator
        result = evaluator.evaluate(customer_issue, article_url)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        provider: str = "openai",
        azure_endpoint: Optional[str] = None,
        azure_deployment: Optional[str] = None,
        azure_api_version: str = "2024-02-15-preview",
        base_url: Optional[str] = None,
        kernel: Optional[Kernel] = None,
        service_id: str = "default"
    ):
        """
        Initialize the SemanticKernelEvaluator.

        Args:
            api_key: API key (OpenAI, Azure OpenAI, or Anthropic)
            model: Model name (e.g., "gpt-4o", "claude-sonnet-4-20250514")
            provider: Provider type ("openai", "azure", or "anthropic")
            azure_endpoint: Azure OpenAI endpoint URL (required for Azure)
            azure_deployment: Azure OpenAI deployment name (required for Azure)
            azure_api_version: Azure OpenAI API version
            base_url: Optional custom base URL for the API
            kernel: Pre-configured Semantic Kernel instance (optional)
            service_id: Service ID for the chat completion service
        """
        self.service_id = service_id

        # Use provided kernel or create one based on provider
        if kernel is not None:
            self.kernel = kernel
        elif provider == "azure":
            if not azure_endpoint or not azure_deployment:
                raise ValueError(
                    "Azure provider requires azure_endpoint and azure_deployment"
                )
            if not api_key:
                import os
                api_key = os.environ.get("AZURE_OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "API key required. Set api_key parameter or AZURE_OPENAI_API_KEY environment variable."
                )

            self.kernel = create_azure_openai_kernel(
                api_key=api_key,
                endpoint=azure_endpoint,
                deployment_name=azure_deployment,
                api_version=azure_api_version,
                service_id=service_id
            )
        elif provider == "anthropic":
            if not api_key:
                import os
                api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "API key required. Set api_key parameter or ANTHROPIC_API_KEY environment variable."
                )

            # Default to claude-sonnet-4-20250514 if model looks like an OpenAI model
            if model.startswith("gpt"):
                model = "claude-sonnet-4-20250514"

            self.kernel = create_anthropic_kernel(
                api_key=api_key,
                model=model,
                service_id=service_id,
                base_url=base_url
            )
        else:  # openai
            if not api_key:
                import os
                api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "API key required. Set api_key parameter or OPENAI_API_KEY environment variable."
                )

            self.kernel = create_openai_kernel(
                api_key=api_key,
                model=model,
                service_id=service_id
            )

        # Initialize the plugin
        self.plugin = ArticleEvaluationPlugin(self.kernel, service_id)

        # Register plugin with kernel for planner use
        self.kernel.add_plugin(self.plugin, plugin_name="ArticleEvaluation")

    def evaluate(
        self,
        customer_issue: str,
        recommended_article: Optional[str] = None,
        product_info: Optional[dict] = None,
    ) -> dict:
        """
        Evaluate whether an article adequately addresses a customer issue.

        Args:
            customer_issue: The customer's issue description
            recommended_article: URL of the recommended article (optional)
            product_info: SAP product metadata from CSV (optional)

        Returns:
            Comprehensive evaluation result dictionary
        """
        # Enrich the issue text with known product context if available
        enriched_issue = customer_issue
        if product_info and (product_info.get('sap_product_name') or product_info.get('sap_name')):
            product_context = (
                f"\n\n[Known Product: {product_info.get('sap_name', '')} "
                f"({product_info.get('sap_product_family', '')}), "
                f"Path: {product_info.get('sap_path', '')}]"
            )
            enriched_issue = customer_issue + product_context

        if not recommended_article:
            # No article provided - return search suggestions
            issue_json = self.plugin.parse_issue(enriched_issue)
            search_json = self.plugin.search_articles(issue_json)
            gap_json = self.plugin.analyze_gaps(issue_json)

            issue_data = json.loads(issue_json)
            search_data = json.loads(search_json)
            gap_data = json.loads(gap_json)

            # Override product with CSV value if available
            known_product = (
                product_info.get('sap_name')
                or product_info.get('sap_product_name')
                or product_info.get('sap_product_family')
            ) if product_info else None
            if known_product:
                issue_data['product'] = known_product

            return {
                "issue_summary": issue_data,
                "current_article_evaluation": {},
                "overall_score": 0,
                "verdict": "no_citation_provided",
                "action_required": "find_better_article",
                "recommended_articles": search_data.get("search_queries", []),
                "search_urls": search_data.get("recommended_search_urls", {}),
                "content_gaps": gap_data,
                "final_recommendation": (
                    f"No article citation was provided for this {issue_data.get('product', 'product')} "
                    f"{issue_data.get('issue_type', 'issue')}. "
                    f"Consider searching support.microsoft.com and learn.microsoft.com for relevant documentation."
                )
            }

        # Full evaluation with article
        result_json = self.plugin.evaluate_article(enriched_issue, recommended_article)
        result = json.loads(result_json)

        # Override product in issue_summary with CSV value if available
        known_product = (
            product_info.get('sap_name')
            or product_info.get('sap_product_name')
            or product_info.get('sap_product_family')
        ) if product_info else None
        if known_product and 'issue_summary' in result:
            result['issue_summary']['product'] = known_product

        return result

    def evaluate_batch(
        self,
        cases: list[dict],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> list[dict]:
        """
        Evaluate multiple cases.

        Args:
            cases: List of dicts with 'issue' and 'article_url' keys
            progress_callback: Optional callback for progress updates

        Returns:
            List of evaluation results
        """
        results = []
        for i, case in enumerate(cases):
            result = self.evaluate(
                customer_issue=case.get('issue', ''),
                recommended_article=case.get('article_url')
            )
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, len(cases))

        return results

    def get_plugin(self) -> ArticleEvaluationPlugin:
        """
        Get the underlying ArticleEvaluationPlugin.

        Useful for accessing individual kernel functions directly.

        Returns:
            The ArticleEvaluationPlugin instance
        """
        return self.plugin

    def get_kernel(self) -> Kernel:
        """
        Get the underlying Semantic Kernel instance.

        Useful for advanced scenarios like using SK planners.

        Returns:
            The Kernel instance
        """
        return self.kernel

    # Convenience methods for individual evaluations

    def parse_issue(self, issue_description: str) -> dict:
        """
        Parse a customer issue description.

        Args:
            issue_description: Raw customer issue text

        Returns:
            Parsed issue dictionary
        """
        return json.loads(self.plugin.parse_issue(issue_description))

    def evaluate_relevance(self, issue: dict | str, article_url: str) -> dict:
        """
        Evaluate article relevance.

        Args:
            issue: Parsed issue dict or JSON string
            article_url: URL of the article

        Returns:
            Relevance evaluation dictionary
        """
        issue_json = issue if isinstance(issue, str) else json.dumps(issue)
        return json.loads(self.plugin.evaluate_relevance(issue_json, article_url))

    def evaluate_completeness(self, issue: dict | str, article_url: str) -> dict:
        """
        Evaluate article completeness.

        Args:
            issue: Parsed issue dict or JSON string
            article_url: URL of the article

        Returns:
            Completeness evaluation dictionary
        """
        issue_json = issue if isinstance(issue, str) else json.dumps(issue)
        return json.loads(self.plugin.evaluate_completeness(issue_json, article_url))

    def evaluate_validity(self, issue: dict | str, article_url: str) -> dict:
        """
        Evaluate solution validity.

        Args:
            issue: Parsed issue dict or JSON string
            article_url: URL of the article

        Returns:
            Validity evaluation dictionary
        """
        issue_json = issue if isinstance(issue, str) else json.dumps(issue)
        return json.loads(self.plugin.evaluate_validity(issue_json, article_url))

    def search_articles(self, issue: dict | str) -> dict:
        """
        Generate search queries for finding articles.

        Args:
            issue: Parsed issue dict or JSON string

        Returns:
            Search results dictionary with queries and URLs
        """
        issue_json = issue if isinstance(issue, str) else json.dumps(issue)
        return json.loads(self.plugin.search_articles(issue_json))

    def analyze_gaps(
        self,
        issue: dict | str,
        relevance: Optional[dict] = None,
        completeness: Optional[dict] = None,
        validity: Optional[dict] = None
    ) -> dict:
        """
        Analyze documentation gaps.

        Args:
            issue: Parsed issue dict or JSON string
            relevance: Optional relevance evaluation results
            completeness: Optional completeness evaluation results
            validity: Optional validity evaluation results

        Returns:
            Gap analysis dictionary
        """
        issue_json = issue if isinstance(issue, str) else json.dumps(issue)
        relevance_json = json.dumps(relevance) if relevance else "{}"
        completeness_json = json.dumps(completeness) if completeness else "{}"
        validity_json = json.dumps(validity) if validity else "{}"

        return json.loads(self.plugin.analyze_gaps(
            issue_json, relevance_json, completeness_json, validity_json
        ))
