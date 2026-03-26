# Scoring System

All scoring logic lives in `utils/scoring.py` (formulas and verdict determination) and `config/settings.py` (thresholds and weights).

## Overall Score Formula

```
overall_score = relevance * 0.40 + completeness * 0.30 + validity * 0.30
```

Defined in `config/settings.py`:

```python
SCORE_WEIGHTS = {
    "relevance": 0.40,
    "completeness": 0.30,
    "validity": 0.30
}
```

All component scores are integers in the range 0-100. The overall score is rounded to the nearest integer.

## Response Quality Score Formula (mweaeval)

```
ai_response_quality_score = response_quality * 0.40 + groundedness * 0.30 + issue_resolution * 0.30
```

Defined in `config/settings.py`:

```python
RESPONSE_QUALITY_WEIGHTS = {
    "response_quality": 0.40,
    "groundedness": 0.30,
    "issue_resolution": 0.30
}
```

The groundedness dimension is derived from CitationQualityAgent results (no additional LLM call). Response quality and issue resolution are evaluated together in a single LLM call by ResponseQualityAgent.

## Verdict Determination

The overall verdict is determined by `ScoringUtils.get_overall_verdict()`:

| Condition | Verdict |
|-----------|---------|
| No article provided | `no_citation_provided` |
| `overall_score >= 70` AND `relevance_verdict` in `[excellent, good]` | `adequate` |
| `overall_score >= 70` AND `relevance_verdict` not in `[excellent, good]` | `needs_supplementation` |
| `50 <= overall_score < 70` | `needs_supplementation` |
| `overall_score < 50` | `inadequate` |

## Action Required

Determined by `ScoringUtils.get_action_required()`:

| Verdict | Better Alternative Found? | Action |
|---------|--------------------------|--------|
| `adequate` | — | `none` |
| `needs_supplementation` | No | `add_context` |
| `needs_supplementation` | Yes | `find_better_article` |
| `inadequate` | No | `create_content` |
| `inadequate` | Yes | `find_better_article` |
| `no_citation_provided` | — | `find_better_article` |

## Per-Agent Threshold Tables

### Relevance Thresholds

| Score Range | Verdict | Description |
|-------------|---------|-------------|
| 85-100 | `excellent` | Directly addresses the exact issue |
| 70-84 | `good` | Most aspects covered |
| 50-69 | `partial` | Related but with gaps |
| 30-49 | `poor` | Tangentially related |
| 0-29 | `irrelevant` | Does not match the issue |

### Completeness Thresholds

| Score Range | Verdict | Description |
|-------------|---------|-------------|
| 90-100 | `complete` | All sections present |
| 70-89 | `mostly_complete` | Minor gaps |
| 50-69 | `incomplete` | Significant gaps |
| 0-49 | `severely_lacking` | Insufficient content |

### Validity Thresholds

| Score Range | Verdict | Description |
|-------------|---------|-------------|
| 80-100 | `valid` | Solution is correct and current |
| 60-79 | `likely_valid` | Probably works |
| 40-59 | `uncertain` | Questionable effectiveness |
| 20-39 | `likely_invalid` | Probably does not work |
| 0-19 | `invalid` | Incorrect or deprecated |

### Description Quality Thresholds

| Score Range | Verdict | Description |
|-------------|---------|-------------|
| 80-100 | `well_defined` | Clear, specific description |
| 60-79 | `mostly_defined` | Adequate with minor gaps |
| 40-59 | `partially_defined` | Missing key information |
| 0-39 | `poorly_defined` | Vague or incomplete |

**Reliability threshold:** `40` — if description quality score falls below this, `evaluation_reliability_warning` is set to `True` and the recommendation is prefixed with a LOW CONFIDENCE notice.

### Response Quality Thresholds

| Score Range | Verdict | Description |
|-------------|---------|-------------|
| 80-100 | `excellent` | High-quality, well-grounded, issue-resolving response |
| 60-79 | `good` | Adequate response with minor gaps |
| 40-59 | `fair` | Response has notable weaknesses |
| 0-39 | `poor` | Inadequate or unsupported response |

### Citation Grounding Thresholds

| Score Range | Verdict | Description |
|-------------|---------|-------------|
| 70-100 | `well_grounded` | Claims are strongly supported by citations |
| 50-69 | `partially_grounded` | Some claims supported, others not |
| 25-49 | `poorly_grounded` | Weak citation support |
| 0-24 | `ungrounded` | Citations do not support the response |

## Conditional Agent Triggers

| Condition | Agent Triggered |
|-----------|----------------|
| `best_score < 70` | SearchAgent (find alternative articles) |
| `best_score < 60` | GapAnalysisAgent (identify documentation gaps) |

## LLM Response Normalization

When a score cannot be extracted from the expected JSON field, the system cascades through multiple extraction strategies:

1. **Direct key lookup** — check `relevance_score`, `score`, etc.
2. **Numeric string parsing** — handles `"70"`, `"70%"`, `"7/10"`, `"7 out of 10"`
3. **Label map lookup** — maps qualitative labels (e.g., `"excellent"` -> 95) across ~40 synonyms per dimension
4. **Last-resort scan** — checks all values in the flattened dict for any recognizable numeric or label match

See [Data Models > Label Normalization Maps](data-models.md#label-normalization-maps) for the full label maps.
