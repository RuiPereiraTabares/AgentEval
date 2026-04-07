"""
Data models for the article evaluation system.
"""

from .issue import Issue
from .article import Article
from .evaluation import (
    DescriptionQualityResult,
    RelevanceResult,
    CompletenessResult,
    ValidityResult,
    SearchResult,
    GapAnalysisResult,
    CitationQualityResult,
    ResponseQualityResult,
    EvaluationResult
)

__all__ = [
    'Issue',
    'Article',
    'DescriptionQualityResult',
    'RelevanceResult',
    'CompletenessResult',
    'ValidityResult',
    'SearchResult',
    'GapAnalysisResult',
    'CitationQualityResult',
    'ResponseQualityResult',
    'EvaluationResult'
]
