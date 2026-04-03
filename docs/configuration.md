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

| Setting | Default | Description |
|---------|---------|-------------|
| `requests_per_minute` | 50 | Max LLM API calls per minute |
| `article_fetch_delay` | 0.5s | Delay between HTTP article fetches |
| `cache_enabled` | `True` | Enable in-memory article cache |
| `cache_ttl` | 3600s (1 hour) | Cache time-to-live |
| `MWAI_REQUEST_DELAY` | 2s | Delay between MWAI API calls (hardcoded in `mwai_client.py`) |

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
| `--verbose`, `-v` | -- | Show per-agent scores and verdict reasoning |
| `--debug` | -- | Show raw LLM prompts, responses, and API details |
| `--token` | -- | MWAI bearer token |
| `--new-token` | -- | Force re-prompt for new MWAI token |
| `--mweaeval` | -- | Enable citation quality + response quality evaluation mode |
| `--batch-size` | -- | Number of cases per batch (enables batch mode with state persistence via `.batch_state.json`) |
| `--continue` | -- | Continue from where the last batch left off (requires `--batch-size`) |

**`article_evaluation_system/main.py`** (alternative CLI):

| Argument | Default | Description |
|----------|---------|-------------|
| `input_file` (positional) | -- | Path to input CSV file |
| `-o`, `--output` | `evaluation_results.json` | Output file path |
| `--format` | `json` | Output format |
| `-n`, `--limit` | -- | Max cases to process |
| `--skip` | `0` | Skip first N cases |
| `-v`, `--verbose` | -- | Verbose output |
