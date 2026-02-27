# Contributing / Extending the System

This guide covers how to add new agents, providers, data models, and modify the scoring system.

## Adding a New Agent

### Step 1: Create the Agent File

Create `agents/my_new_agent.py`:

```python
"""
My New Agent — brief description of what it does.
"""

import logging

from . import BaseAgent
from ..models.issue import Issue
from ..models.article import Article
from ..models.evaluation import MyNewResult  # create this first
from ..utils.prompts import AgentPrompts

logger = logging.getLogger(__name__)


class MyNewAgent(BaseAgent):
    """Description of the agent's purpose."""

    def evaluate(self, issue: Issue, article: Article = None, **kwargs) -> MyNewResult:
        """
        Perform the evaluation.

        Args:
            issue: Parsed customer issue
            article: Fetched article (if applicable)

        Returns:
            MyNewResult with evaluation data
        """
        try:
            # Build the user message from inputs
            user_message = f"Issue: {issue.to_dict()}"
            if article:
                user_message += f"\n\nArticle: {article.get_content_summary(8000)}"

            # Call the LLM
            response = self._call_claude(
                system_prompt=AgentPrompts.MY_NEW_AGENT,
                user_message=user_message,
            )

            # Parse the response
            data = self._parse_json_response(response)
            return MyNewResult.from_dict(data)

        except Exception as e:
            logger.warning(f"[MyNewAgent] LLM call failed: {e}, using fallback")
            return self._fallback(issue, article)

    def _fallback(self, issue: Issue, article: Article = None) -> MyNewResult:
        """Heuristic fallback when LLM fails."""
        return MyNewResult(
            # ... sensible defaults
        )
```

### Step 2: Add the Data Model

Add a dataclass to `models/evaluation.py`:

```python
@dataclass
class MyNewResult:
    score: int = 0
    details: str = ""

    def to_dict(self) -> dict:
        return {"score": self.score, "details": self.details}

    @classmethod
    def from_dict(cls, data: dict) -> "MyNewResult":
        flat = _collect_all_values(data)
        score = _extract_score(flat, "score", ["score", "my_score"], _MY_LABEL_MAP)
        return cls(score=score, details=flat.get("details", ""))
```

### Step 3: Add the System Prompt

Add to `utils/prompts.py`:

```python
class AgentPrompts:
    # ... existing prompts ...

    MY_NEW_AGENT = """You are an expert at evaluating...

Respond ONLY with valid JSON in this exact format:
{
    "score": <integer 0-100>,
    "details": "explanation string"
}"""
```

### Step 4: Register in `agents/__init__.py`

```python
from .my_new_agent import MyNewAgent

__all__ = [
    # ... existing exports ...
    'MyNewAgent',
]
```

### Step 5: Wire into the Orchestrator

In `agents/orchestrator.py`:

```python
def __init__(self, ...):
    # ... existing agents ...
    self.my_new_agent = MyNewAgent(client, model, provider)

def evaluate(self, ...):
    # ... at the appropriate point in the pipeline ...
    my_result = self.my_new_agent.evaluate(issue, article)
```

## Adding a New LLM Provider

### Step 1: Update `BaseAgent._call_claude()`

In `agents/__init__.py`, add a new branch:

```python
def _call_claude(self, system_prompt: str, user_message: str) -> str:
    # ... existing provider checks ...
    elif self.provider == "my_provider":
        response = self.client.my_api_call(system_prompt, user_message)
        return response
```

### Step 2: Update the Orchestrator Client Initialization

In `agents/orchestrator.py`, handle the new provider in `__init__()`:

```python
if provider == "my_provider":
    from my_provider_sdk import MyClient
    client = MyClient(api_key=api_key)
```

### Step 3: Update CLI Arguments

In `run_evaluation.py`, add the new provider to the `--provider` choices:

```python
parser.add_argument('--provider', choices=['openai', 'anthropic', 'mwai', 'my_provider'], ...)
```

## Adding New Data Models

Follow the existing pattern in `models/evaluation.py`:

1. **Define the dataclass** with typed fields and defaults
2. **Add `to_dict()`** for serialization
3. **Add `from_dict(cls, data)`** using the resilient parsing helpers:
   - `_collect_all_values(data)` to flatten nested dicts
   - `_extract_score()` with a label map for numeric fields
   - `_extract_bool()`, `_extract_list()`, `_extract_str()` for other types
4. **Create a label map** if the field can be returned as a qualitative label

## Modifying Scoring Weights and Thresholds

All weights and thresholds are centralized in `config/settings.py`:

### Change Overall Score Weights

```python
# config/settings.py
SCORE_WEIGHTS = {
    "relevance": 0.40,      # Adjust these (must sum to 1.0)
    "completeness": 0.30,
    "validity": 0.30
}
```

### Change Verdict Thresholds

```python
# config/settings.py
THRESHOLDS = {
    "overall_adequate": 70,  # Minimum score for "adequate" verdict
    "relevance": {
        "excellent": 85,     # Adjust per-agent thresholds
        # ...
    },
    "description_quality_reliability": 40,  # Low-confidence threshold
}
```

### Change KT Dimension Weights

```python
# config/settings.py
KT_DIMENSION_WEIGHTS = {
    "identity": 0.35,   # Must sum to 1.0
    "location": 0.25,
    "timing": 0.20,
    "magnitude": 0.20
}
```

### Change Transfer Classification Thresholds

```python
# config/settings.py
TRANSFER_CLASSIFICATION_THRESHOLDS = {
    "poor_description_ceiling": 40,
    "bad_citation_relevance_ceiling": 50,
    "inadequate_article_overall_ceiling": 60,
}
```

## Modifying Prompts

All LLM system prompts are in `utils/prompts.py` as class attributes on `AgentPrompts`.

When modifying prompts:

- Keep the JSON output format specification — agents depend on specific field names
- Test with multiple providers (LLMs respond differently to the same prompt)
- Verify that `_parse_json_response()` can handle the expected output
- If adding new fields, update the corresponding `from_dict()` in the data model

## Adding to the SK Plugin

Semantic Kernel functions are defined in `sk/plugin.py`. To add a new function:

1. Add a native function to the plugin class
2. Register it in the plugin's function list
3. Update `sk/evaluator.py` to call it at the right pipeline stage

## Testing Patterns

### Mock LLM via `set_llm_callable()`

Every agent supports injecting a mock LLM callable:

```python
from article_evaluation_system.agents import RelevanceAgent

agent = RelevanceAgent(client=None, model="test", provider="openai")

# Inject a mock LLM that returns a fixed response
agent.set_llm_callable(lambda system, user: json.dumps({
    "relevance_score": 85,
    "matched_aspects": ["product", "error code"],
    "unmatched_aspects": [],
    "version_match": True,
    "product_match": True,
    "is_outdated": False,
    "relevance_verdict": "excellent"
}))

result = agent.evaluate(issue=test_issue, article=test_article)
assert result.relevance_score == 85
```

### Test Fallback Paths

Inject a callable that raises an exception to test heuristic fallbacks:

```python
agent.set_llm_callable(lambda s, u: (_ for _ in ()).throw(RuntimeError("LLM down")))
result = agent.evaluate(issue=test_issue, article=test_article)
# Result should use heuristic fallback values
```

## Coding Conventions

- **Python 3.12+** — use modern type hints (`str | None`, `list[str]`)
- **Dataclasses** — all data models use `@dataclass` with `field(default_factory=...)` for mutable defaults
- **Logging** — use `logging.getLogger(__name__)` per module, `INFO` for milestones, `DEBUG` for raw LLM I/O, `WARNING` for fallbacks
- **Fallbacks** — every agent must have a heuristic fallback path when the LLM fails
- **Provider agnostic** — all agent logic works identically across providers; use `_call_claude()` for all LLM calls
- **No external state** — agents are stateless; all data flows through method parameters and return values
