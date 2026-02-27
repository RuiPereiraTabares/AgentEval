# Kepner-Tregoe Framework

The system uses the **Kepner-Tregoe (KT) Problem Analysis** framework to evaluate the quality of customer issue descriptions. A well-structured problem description enables better article matching; a vague one undermines the entire evaluation pipeline.

## What Is KT and Why It Applies

Kepner-Tregoe is a structured problem-solving methodology that breaks any problem into four dimensions: **Identity** (what), **Location** (where), **Timing** (when), and **Magnitude** (extent). In support case triage, these same dimensions determine whether the LLM can accurately match issues to articles:

- **Specific descriptions** (high KT score) lead to precise article matching
- **Vague descriptions** (low KT score) lead to irrelevant matches or no matches at all
- The KT score serves as a confidence measure for the entire evaluation

## Four Dimensions

| Dimension | KT Question | Weight | What It Measures |
|-----------|-------------|--------|------------------|
| **Identity (WHAT)** | What is the problem? | **35%** | Specific product, feature, error code, symptom. The most critical dimension for article matching. |
| **Location (WHERE)** | Where is it observed? | **25%** | Environment, URL, server, region, module, tenant. |
| **Timing (WHEN)** | When did it start? | **20%** | Start date, pattern (continuous, intermittent, triggered), frequency. |
| **Magnitude (EXTENT)** | How many are affected? | **20%** | Number of users, business impact, trend, scope. |

Weights are defined in `config/settings.py`:

```python
KT_DIMENSION_WEIGHTS = {
    "identity": 0.35,
    "location": 0.25,
    "timing": 0.20,
    "magnitude": 0.20
}
```

## Per-Dimension Scoring Guide

Each dimension is scored 0-100 by the LLM:

### Identity (WHAT) — 35%

| Score | Description |
|-------|-------------|
| 80-100 | Specific product, version, error code, and exact symptom mentioned |
| 60-79 | Product named, symptom described, but error codes or version missing |
| 40-59 | General product area mentioned, vague symptom description |
| 0-39 | No product identified, generic complaint |

### Location (WHERE) — 25%

| Score | Description |
|-------|-------------|
| 80-100 | Specific server, tenant, URL, region, or module identified |
| 60-79 | General environment described (OS, browser) |
| 40-59 | Partial environment info |
| 0-39 | No environment or location context |

### Timing (WHEN) — 20%

| Score | Description |
|-------|-------------|
| 80-100 | Exact start date, pattern (continuous/intermittent), trigger event |
| 60-79 | Approximate timeframe, some pattern info |
| 40-59 | "Recently" or "sometimes" — vague temporal reference |
| 0-39 | No timing information at all |

### Magnitude (EXTENT) — 20%

| Score | Description |
|-------|-------------|
| 80-100 | Exact user count, business impact quantified, trend described |
| 60-79 | Approximate scope ("team of 50", "several users") |
| 40-59 | General impact mentioned ("some users affected") |
| 0-39 | No scope or impact information |

## Overall Score Calculation

```
description_quality_score =
    identity_score  * 0.35 +
    location_score  * 0.25 +
    timing_score    * 0.20 +
    magnitude_score * 0.20
```

## Verdict Thresholds

| Score Range | Verdict | Meaning |
|-------------|---------|---------|
| 80-100 | `well_defined` | Description is clear and specific |
| 60-79 | `mostly_defined` | Adequate with minor gaps |
| 40-59 | `partially_defined` | Missing key information |
| 0-39 | `poorly_defined` | Vague or incomplete |

## Reliability Threshold and Downstream Impact

**Threshold: 40** (configurable via `THRESHOLDS["description_quality_reliability"]`)

When `description_quality_score < 40`:

1. `evaluation_reliability_warning` is set to `True` on the `EvaluationResult`
2. The final recommendation is prefixed with: `"[LOW CONFIDENCE] The customer's issue description is vague or incomplete, reducing confidence in this evaluation."`
3. Consumers of the evaluation should treat scores and verdicts as less reliable

## Worked Examples

### Well-Defined Description (Score ~85)

> "Users in the EMEA tenant (tenant ID: abc123) are unable to access SharePoint Online since January 15th, 2025. The error 'Sorry, something went wrong (0x80004005)' appears when navigating to https://contoso.sharepoint.com/sites/finance. Approximately 200 users across 3 offices are affected. The issue is intermittent — works in the morning, fails after 2 PM GMT."

- **Identity:** 95 — Product (SharePoint Online), error code (0x80004005), specific URL
- **Location:** 90 — Tenant ID, specific site URL, EMEA region
- **Timing:** 85 — Exact start date, intermittent pattern with trigger time
- **Magnitude:** 80 — 200 users, 3 offices, trend described

### Poorly-Defined Description (Score ~20)

> "SharePoint is not working for some users. They get an error. Please help."

- **Identity:** 30 — Product named but no error code, version, or specific symptom
- **Location:** 10 — No environment info at all
- **Timing:** 0 — No temporal information
- **Magnitude:** 15 — "Some users" is vague

## Heuristic Fallback

When the LLM call fails, the DescriptionQualityAgent falls back to keyword-based scoring:

**Location keywords detected:** server, region, tenant, environment, URL, machine, datacenter, office, building, network, subnet, cluster, zone

**Timing patterns matched:** date regexes (YYYY-MM-DD, MM/DD/YYYY), temporal keywords (since, started, began, yesterday, last week, intermittent, continuous, every time)

**Magnitude indicators:** user counts (`\d+ users`), percentages (`\d+%`), impact keywords (all users, entire department, company-wide, business critical)

The heuristic scores are typically more conservative than LLM scores but ensure the pipeline always produces a result.
