"""
Semantic Kernel integration for the Article Evaluation System.

This module provides SK-compatible wrappers and plugins for article evaluation,
enabling integration with Azure OpenAI, Anthropic/Claude, and other SK-supported providers.
"""

from .evaluator import SemanticKernelEvaluator
from .plugin import ArticleEvaluationPlugin
from .llm_adapter import SKChatCompletionAdapter, SKAgentWrapper
from .anthropic_connector import AnthropicChatCompletion

__all__ = [
    'SemanticKernelEvaluator',
    'ArticleEvaluationPlugin',
    'SKChatCompletionAdapter',
    'SKAgentWrapper',
    'AnthropicChatCompletion'
]
