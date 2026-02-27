"""
Multi-Agent Article Evaluation System

Evaluates whether Microsoft support articles adequately solve customer issues.
"""

from .agents.orchestrator import Orchestrator
from .models.issue import Issue
from .models.article import Article
from .models.evaluation import EvaluationResult

# Conditional Semantic Kernel imports
try:
    from .sk import SemanticKernelEvaluator, ArticleEvaluationPlugin
    SK_AVAILABLE = True
except ImportError:
    SK_AVAILABLE = False
    SemanticKernelEvaluator = None
    ArticleEvaluationPlugin = None


class ArticleEvaluator:
    """Main entry point for the article evaluation system."""

    def __init__(
        self,
        api_key: str = None,
        model: str = "gpt-4o",
        provider: str = "openai",
        base_url: str = None,
        mwai_token: str = None
    ):
        """
        Initialize the ArticleEvaluator.

        Args:
            api_key: API key (OpenAI or Anthropic). Not needed for "mwai" provider.
            model: Model to use for evaluations
            provider: API provider ("openai", "anthropic", or "mwai")
            base_url: Custom base URL for API (for proxies/custom endpoints)
            mwai_token: MWAI bearer token (required when provider is "mwai")
        """
        self.orchestrator = Orchestrator(
            api_key=api_key,
            model=model,
            provider=provider,
            base_url=base_url,
            mwai_token=mwai_token
        )

    def evaluate(
        self,
        customer_issue: str,
        recommended_article: str | None = None,
        product_info: dict | None = None,
        transfer_metadata: dict | None = None,
    ) -> dict:
        """
        Evaluate whether an article adequately addresses a customer issue.

        Args:
            customer_issue: The customer's issue description
            recommended_article: URL of the recommended article (optional)
            product_info: SAP product metadata from CSV (optional)
            transfer_metadata: Dict with 'transferred', 'sr_status', 'reopened' from CSV

        Returns:
            Comprehensive evaluation result dictionary
        """
        return self.orchestrator.evaluate(
            customer_issue=customer_issue,
            article_url=recommended_article,
            product_info=product_info,
            transfer_metadata=transfer_metadata,
        )

    def evaluate_batch(
        self,
        cases: list[dict],
        progress_callback: callable = None
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


__all__ = [
    'ArticleEvaluator',
    'Issue',
    'Article',
    'EvaluationResult',
    'SK_AVAILABLE',
    'SemanticKernelEvaluator',
    'ArticleEvaluationPlugin'
]
