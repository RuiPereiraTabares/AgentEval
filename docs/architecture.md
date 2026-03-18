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
    relevance_agent.py # RelevanceAgent
    completeness_agent.py
    validity_agent.py
    search_agent.py
    gap_agent.py
    description_quality_agent.py
    transfer_reason_agent.py
  models/
    __init__.py
    issue.py           # Issue dataclass
    article.py         # Article dataclass
    evaluation.py      # All result dataclasses + label maps
  config/
    __init__.py
    settings.py        # Thresholds, weights, Settings dataclass
  utils/
    __init__.py
    article_fetcher.py # HTTP fetch + HTML parsing + cache
    scoring.py         # ScoringUtils (score formulas, verdict logic)
    prompts.py         # All LLM system prompts (AgentPrompts)
    mwai_client.py     # MWAI API client + token management
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
  +-- TransferReasonResult
  |
  v
EvaluationResult.to_dict()
  |
  v
write_results_json() / write_results_csv() / write_results_csv_summary()
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
| RelevanceAgent | Returns score 30 (poor) |
| CompletenessAgent | Keyword-based section detection |
| ValidityAgent | Returns score 50 (uncertain) |
| SearchAgent | Constructs queries from issue keywords |
| GapAnalysisAgent | Derives gaps from upstream result objects |
| DescriptionQualityAgent | KT dimension heuristics via keyword detection |
| TransferReasonAgent | Classification proceeds without LLM escalation detection |

### Score Normalization

LLM responses are unpredictable — scores may come as integers, percentages, fractions, or qualitative labels. The `_extract_score()` function in `models/evaluation.py` handles all cases:

1. Direct numeric value from expected key
2. Numeric string parsing (`"70"`, `"70%"`, `"7/10"`, `"7 out of 10"`)
3. Label map lookup (100+ synonyms per dimension)
4. Last-resort: scan all values in the flat dict for any recognizable score
