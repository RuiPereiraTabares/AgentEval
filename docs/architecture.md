# Architecture

## Multi-Agent Pattern

The system uses a **coordinator-specialist** pattern where a central `Orchestrator` drives a pipeline of specialized agents. Each agent handles one evaluation dimension, communicates via structured data models, and is independently testable.

```
article_evaluation_system/
  __init__.py          # ArticleEvaluator (public entry point)
  main.py              # CSV I/O, CLI via argparse
  agents/
    __init__.py        # BaseAgent ABC
    orchestrator.py    # Coordinates all agents
    issue_parser.py    # IssueParserAgent
    area_classification_agent.py  # AreaClassificationAgent (Step 1a)
    relevance_agent.py # RelevanceAgent
    completeness_agent.py
    validity_agent.py
    search_agent.py
    gap_agent.py
    description_quality_agent.py
    transfer_reason_agent.py
    citation_quality_agent.py
    response_quality_agent.py
  models/
    __init__.py
    issue.py           # Issue dataclass (+ area_path, area_path_confidence)
    article.py         # Article dataclass
    evaluation.py      # All result dataclasses + label maps (incl. TrendCluster, CitationOverlap)
  config/
    __init__.py
    settings.py        # Thresholds, weights, Settings dataclass
    area_definitions.py  # Product area taxonomies (Teams: 17 areas; extensible)
  utils/
    __init__.py
    article_fetcher.py # HTTP fetch + HTML parsing + cache
    scoring.py         # ScoringUtils (score formulas, verdict logic)
    prompts.py         # All LLM system prompts (AgentPrompts, incl. TREND_SYNTHESIS)
    citation_parser.py # Citation URL extraction and parsing
    mwai_client.py     # MWAI API client + token management
  synthesis/
    trend_synthesis.py # TrendSynthesizer — semantic clustering + citation overlap detection
run_evaluation.py      # Primary CLI runner
```

## BaseAgent Class

All agents inherit from `BaseAgent` (`agents/__init__.py`):

```python
class BaseAgent(ABC):
    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai")

    @abstractmethod
    def evaluate(self, **kwargs) -> dict

    def _call_llm(self, system_prompt: str, user_message: str) -> str
    def _parse_json_response(self, response: str) -> dict
    def set_llm_callable(self, callable_fn)
```

**`_call_llm()`** calls the MWAI API via `client.chat_completion(system_prompt, user_message)`. If an injected callable is set via `set_llm_callable()`, it is used instead.

**`set_llm_callable()`** allows injecting an alternative LLM implementation without modifying agent logic.

## Agent Interaction Sequence

```
Orchestrator.evaluate()
    |
    |-- IssueParserAgent.evaluate(customer_issue)
    |       -> Issue
    |
    |-- AreaClassificationAgent.classify(issue)          [Step 1a]
    |       -> sets issue.area_path, issue.area_path_confidence
    |
    |-- DescriptionQualityAgent.evaluate(issue)
    |       -> DescriptionQualityResult
    |
    |-- [for each URL]:
    |       |-- ArticleFetcher.fetch(url)
    |       |       -> Article
    |       |-- RelevanceAgent.evaluate(issue, article)
    |       |       -> RelevanceResult
    |       |-- CompletenessAgent.evaluate(issue, article)
    |       |       -> CompletenessResult
    |       |-- ValidityAgent.evaluate(issue, article)
    |       |       -> ValidityResult
    |       |-- ScoringUtils.calculate_overall_score()
    |       |       -> int (0-100)
    |
    |-- [if best_score < 70]:
    |       SearchAgent.evaluate(issue, best_score)
    |           -> SearchResult
    |
    |-- [if best_score < 60]:
    |       GapAnalysisAgent.evaluate(issue, relevance, completeness, validity)
    |           -> GapAnalysisResult
    |
    |-- TransferReasonAgent.evaluate(issue, description_quality, scores, ...)
    |       -> TransferReasonResult
    |
    |-- Orchestrator._build_final_result(...)
            -> EvaluationResult.to_dict()
```

## Citation Quality Interaction Sequence (mweaeval)

```
Orchestrator.evaluate_with_citations()
    |
    |-- IssueParserAgent.evaluate(customer_issue)
    |       -> Issue
    |
    |-- AreaClassificationAgent.classify(issue)          [Step 1a]
    |       -> sets issue.area_path, issue.area_path_confidence
    |
    |-- DescriptionQualityAgent.evaluate(issue)
    |       -> DescriptionQualityResult
    |
    |-- CitationQualityAgent.evaluate(ai_response, citation_urls, article_fetcher)
    |       |-- [for each citation URL]:
    |       |       ArticleFetcher.fetch(url)
    |       |       LLM evaluate citation support
    |       -> CitationQualityResult
    |
    |-- [R/C/V on best-grounding citation]:
    |       |-- RelevanceAgent.evaluate(issue, best_article)
    |       |       -> RelevanceResult
    |       |-- CompletenessAgent.evaluate(issue, best_article)
    |       |       -> CompletenessResult
    |       |-- ValidityAgent.evaluate(issue, best_article)
    |       |       -> ValidityResult
    |
    |-- ResponseQualityAgent.evaluate(issue, ai_response, citation_quality_result)
    |       -> ResponseQualityResult
    |
    |-- TransferReasonAgent.evaluate(issue, description_quality, scores, ...)
    |       -> TransferReasonResult
    |
    |-- Orchestrator._build_final_result(...)
            -> EvaluationResult.to_dict()
```

## Data Flow

```
CSV File
  |
  v
read_csv_cases()  -->  dict per row (case_number, title, issue_description, urls, ...)
  |
  v
ArticleEvaluator.evaluate()
  |
  v
Orchestrator.evaluate()
  |
  +-- Issue (parsed from description)
  +-- Article (fetched from URL)
  +-- RelevanceResult, CompletenessResult, ValidityResult
  +-- SearchResult (conditional)
  +-- GapAnalysisResult (conditional)
  +-- DescriptionQualityResult
  +-- CitationQualityResult (mweaeval mode)
  +-- ResponseQualityResult (mweaeval mode)
  +-- TransferReasonResult
  |
  v
EvaluationResult.to_dict()
  |
  v
write_results_json() / write_results_csv() / write_results_csv_summary()

  --- Batch trend analysis (opt-in: --trend-report) ---

  list[EvaluationResult dicts]
    |
    v
  TrendSynthesizer.synthesize_trends()
    |
    +-- _build_case_summaries()        # compact each result + issue_description
    +-- _build_citation_overlaps()     # detect shared URLs; Jaccard similarity
    +-- LLM clustering (or _deterministic_fallback with Jaccard ≥ 0.15 guard)
    |
    v
  { clusters: list[TrendCluster], executive_summary, citation_overlaps: list[CitationOverlap] }
    |
    v
  write_trend_report_csv() / write_citation_overlaps_csv()
```

## Error Handling Strategy

### 3-Stage JSON Parsing (`_parse_json_response`)

1. **Markdown extraction** — regex for `` ```json ... ``` `` blocks
2. **Direct parse** — `json.loads()` on extracted or raw text
3. **Regex fallback** — find first `{ ... }` in the response and parse it

If all stages fail, a `ValueError` is raised and the calling agent uses its **heuristic fallback**.

### Heuristic Fallbacks

Every agent has a fallback path when the LLM call fails:

| Agent | Fallback Strategy |
|-------|-------------------|
| IssueParserAgent | Keyword extraction from raw text |
| AreaClassificationAgent | Returns `None` — issue continues without area_path |
| RelevanceAgent | Returns score 30 (poor) |
| CompletenessAgent | Keyword-based section detection |
| ValidityAgent | Returns score 50 (uncertain) |
| SearchAgent | Constructs queries from issue keywords |
| GapAnalysisAgent | Derives gaps from upstream result objects |
| DescriptionQualityAgent | KT dimension heuristics via keyword detection |
| TransferReasonAgent | Classification proceeds without LLM escalation detection |
| CitationQualityAgent | Returns score 0 (bad) for unfetchable citations |
| ResponseQualityAgent | Returns groundedness-only score from CitationQualityAgent |

### Score Normalization

LLM responses are unpredictable — scores may come as integers, percentages, fractions, or qualitative labels. The `_extract_score()` function in `models/evaluation.py` handles all cases:

1. Direct numeric value from expected key
2. Numeric string parsing (`"70"`, `"70%"`, `"7/10"`, `"7 out of 10"`)
3. Label map lookup (100+ synonyms per dimension)
4. Last-resort: scan all values in the flat dict for any recognizable score
