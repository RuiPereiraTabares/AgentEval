# Configuration Reference

## Environment Variables

| Variable | Description |
|----------|-------------|
| `MWAI_TOKEN` | MWAI bearer token (JWT) |
| `VERBOSE` | Set to `"true"` for verbose logging |

## `.env` Example

Create a `.env` file in the project root (loaded by `python-dotenv`):

```env
# MWAI
MWAI_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIs...
```

## Settings Dataclass

**File:** `config/settings.py`

```python
@dataclass
class Settings:
    model: str                    # default: server-side (MWAI)
    requests_per_minute: int      # default: 50
    article_fetch_delay: float    # default: 0.5 (seconds)
    cache_enabled: bool           # default: True
    cache_ttl: int                # default: 3600 (seconds)
    thresholds: dict              # default: THRESHOLDS (see below)
    score_weights: dict           # default: SCORE_WEIGHTS (see below)
    max_search_results: int       # default: 5
    search_domains: list[str]     # default: ["support.microsoft.com", "learn.microsoft.com"]
    output_format: str            # default: "csv"
    verbose: bool                 # default: False
```

**Factory method:** `Settings.from_env()` reads `MWAI_TOKEN` and `VERBOSE` from environment variables.

## Scoring Thresholds

**`THRESHOLDS`** dict (`config/settings.py`):

```python
THRESHOLDS = {
    "relevance": {
        "excellent": 85,
        "good": 70,
        "partial": 50,
        "poor": 30
    },
    "completeness": {
        "complete": 90,
        "mostly_complete": 70,
        "incomplete": 50
    },
    "validity": {
        "valid": 80,
        "likely_valid": 60,
        "uncertain": 40
    },
    "overall_adequate": 70,
    "description_quality": {
        "well_defined": 80,
        "mostly_defined": 60,
        "partially_defined": 40
    },
    "description_quality_reliability": 40
}
```

## Transfer Classification Thresholds

**`TRANSFER_CLASSIFICATION_THRESHOLDS`** dict (`config/settings.py`):

```python
TRANSFER_CLASSIFICATION_THRESHOLDS = {
    "poor_description_ceiling": 40,          # Below -> description is root cause
    "bad_citation_relevance_ceiling": 50,    # Below -> citation match is poor
    "inadequate_article_overall_ceiling": 60  # Below -> article doesn't solve it
}
```

## Score Weights

**`SCORE_WEIGHTS`** dict (`config/settings.py`):

```python
SCORE_WEIGHTS = {
    "relevance": 0.40,
    "completeness": 0.30,
    "validity": 0.30
}
```

## KT Dimension Weights

**`KT_DIMENSION_WEIGHTS`** dict (`config/settings.py`):

```python
KT_DIMENSION_WEIGHTS = {
    "identity": 0.35,   # WHAT
    "location": 0.25,   # WHERE
    "timing": 0.20,     # WHEN
    "magnitude": 0.20   # EXTENT
}
```

## Response Quality Weights

**`RESPONSE_QUALITY_WEIGHTS`** dict (`config/settings.py`):

```python
RESPONSE_QUALITY_WEIGHTS = {
    "response_quality": 0.40,
    "groundedness": 0.30,
    "issue_resolution": 0.30
}
```

## Rate Limiting and Caching

### MWAI Rate Limiter

MWAI calls are governed by a **token-bucket rate limiter** (`_rate_limiter` in `utils/mwai_client.py`), shared across all worker threads. The bucket refills at `MWAI_MAX_RPS` tokens/second:

```python
# utils/mwai_client.py
MWAI_MAX_RPS = 3.33   # ≈ 200 RPM — increase if your MWAI quota allows more
MWAI_REQUEST_DELAY = 1.0 / MWAI_MAX_RPS  # backward-compat constant; not used for sleep
```

`MWAI_REQUEST_DELAY` is kept for backward compatibility (external code that imports it will not break), but the actual rate control is the token bucket.

### Article Cache

| Setting | Value | Description |
|---------|-------|-------------|
| `requests_per_minute` (Settings) | 50 | Informational — actual limit is MWAI_MAX_RPS |
| `article_fetch_delay` (Settings) | 0.5s | Delay between live HTTP article fetches |
| `cache_enabled` (Settings) | `True` | Enable in-memory L1 article cache |
| `cache_ttl` (Settings) | 3600s | In-memory L1 TTL |
| `_ARTICLE_CACHE_DB` | `~/.article_cache.db` | SQLite L2 persistent cache path (hardcoded) |
| `_ARTICLE_CACHE_TTL` | 86400s (24h) | SQLite L2 TTL |

Disable the SQLite L2 cache for a run with `--no-article-cache`.

### LLM Response Cache

Successful LLM responses are cached in SQLite to avoid redundant API calls on re-runs or for cases with identical prompts.

| Setting | Value | Description |
|---------|-------|-------------|
| `_LLM_CACHE_DB` | `~/.llm_response_cache.db` | SQLite cache path (hardcoded in `utils/llm_cache.py`) |
| `_LLM_CACHE_TTL` | 604800s (7 days) | Cache TTL |
| `_LLM_CACHE_ENABLED` | `True` | Module flag in `agents/__init__.py`; set to `False` to disable globally |

Disable for a run with `--no-llm-cache`.

## LLM Parameters

LLM parameters are set in `BaseAgent._call_llm()`:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `temperature` | `0.1` | Low temperature for deterministic outputs |
| `max_tokens` | `4096` | Maximum response tokens |

MWAI additionally uses `response_format: {"type": "json_object"}`.

## CLI Arguments

**`run_evaluation.py`:**

| Argument | Default | Description |
|----------|---------|-------------|
| `--input`, `-i` | `merged_output.csv` | Input CSV file |
| `--output`, `-o` | `evaluation_results_{timestamp}.{format}` | Output file |
| `--limit`, `-n` | `50` | Number of cases to process |
| `--all` | -- | Process all cases |
| `--case` | -- | Process a specific case number |
| `--skip` | `0` | Skip first N cases |
| `--format` | `csv` | Output format (`json` or `csv`) |
| `--mweaeval` | -- | Enable citation quality + response quality evaluation mode |
| `--verbose`, `-v` | -- | Show per-agent scores and verdict reasoning (sequential mode only) |
| `--debug` | -- | Show raw LLM prompts, responses, and API details (sequential mode only) |
| `--token` | -- | MWAI bearer token |
| `--new-token` | -- | Force re-prompt for new MWAI token |
| `--workers` | `1` | Parallel case workers. Each thread gets its own Orchestrator; all share one MwaiClient and rate-limiter. Verbose/debug suppressed when > 1. |
| `--batch-size` | -- | Number of cases per batch (enables batch mode with state persistence via `.batch_state.json`) |
| `--continue` | -- | Continue from where the last batch left off (requires `--batch-size`) |
| `--no-llm-cache` | -- | Disable LLM response dedup cache for this run (forces fresh API calls) |
| `--no-article-cache` | -- | Disable persistent SQLite article cache for this run (forces re-fetch of all URLs) |

**`article_evaluation_system/main.py`** (alternative CLI):

| Argument | Default | Description |
|----------|---------|-------------|
| `input_file` (positional) | -- | Path to input CSV file |
| `-o`, `--output` | `evaluation_results.json` | Output file path |
| `--format` | `json` | Output format |
| `-n`, `--limit` | -- | Max cases to process |
| `--skip` | `0` | Skip first N cases |
| `-v`, `--verbose` | -- | Verbose output |
