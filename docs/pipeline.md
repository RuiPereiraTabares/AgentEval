# Pipeline / Workflow

The evaluation pipeline is orchestrated by `Orchestrator.evaluate()` in `agents/orchestrator.py`. The pipeline has two main paths: the **citation path** (article URLs provided) and the **no-citation path**.

## Complete Pipeline Flowchart

```
                    START: Orchestrator.evaluate()
                              |
                    +---------+---------+
                    |                   |
              [Step 1]            [Step 1b]
         IssueParserAgent    DescriptionQualityAgent
         (parse issue)        (KT framework)
                    |                   |
                    +----->  dq_score < 40?
                              |        |
                             YES       NO
                              |        |
                    set reliability    (ok)
                    warning = True
                              |
                    +---------+---------+
                    |                   |
               Has URLs?          No URLs
                    |                   |
               [Step 2]          [No-Citation Path]
          for each URL:           SearchAgent
           |                      GapAnalysisAgent
           +-- ArticleFetcher     TransferReasonAgent
           |     .fetch(url)       -> EvaluationResult
           |          |                (verdict: no_citation_provided)
           |   [Step 2a]
           |   RelevanceAgent
           |     -> RelevanceResult
           |
           |   [Step 2b]
           |   CompletenessAgent
           |     -> CompletenessResult
           |
           |   [Step 2c]
           |   ValidityAgent
           |     -> ValidityResult
           |
           |   [Step 2d]
           |   ScoringUtils.calculate_overall_score()
           |     -> R*0.4 + C*0.3 + V*0.3
           |
           +-- keep best_score across all URLs
                    |
              [Step 3]
         best_score < 70?
              |        |
             YES       NO
              |        |
         SearchAgent   |
         (find alts)   |
              |        |
              +--------+
              |
              [Step 4]
         best_score < 60?
              |        |
             YES       NO
              |        |
         GapAnalysis   |
         Agent         |
              |        |
              +--------+
              |
              [Step 5]
         TransferReasonAgent
         (classify why transferred)
              |
              [Step 6]
         _build_final_result()
              |
         EvaluationResult.to_dict()
              |
             END
```

## Step-by-Step Breakdown

### Step 1: Parse the Customer Issue

**Agent:** IssueParserAgent
**Input:** Raw customer issue text + optional SAP product metadata
**Output:** `Issue` dataclass with product, symptoms, keywords, type, severity, etc.
**LLM calls:** 1

Transfer metadata (`transferred`, `sr_status`, `reopened`) is injected from CSV into the Issue object after parsing.

### Step 1b: Evaluate Description Quality

**Agent:** DescriptionQualityAgent
**Input:** Parsed `Issue`
**Output:** `DescriptionQualityResult` with KT dimension scores
**LLM calls:** 1

If `description_quality_score < 40` (the reliability threshold), the `evaluation_reliability_warning` flag is set. This flag propagates to the final recommendation.

### Step 2: Fetch and Evaluate Articles

For each URL in `article_urls` (or the single `article_url`):

1. **Fetch:** `ArticleFetcher.fetch(url)` downloads and parses the HTML
2. **Relevance:** `RelevanceAgent.evaluate(issue, article)` — 1 LLM call
3. **Completeness:** `CompletenessAgent.evaluate(issue, article)` — 1 LLM call
4. **Validity:** `ValidityAgent.evaluate(issue, article)` — 1 LLM call
5. **Score:** `ScoringUtils.calculate_overall_score(R, C, V)` — pure computation

The evaluation with the **highest overall score** is selected as the primary result.

### Step 3: Conditional Search (score < 70)

**Agent:** SearchAgent
**Trigger:** `best_score < THRESHOLDS["overall_adequate"]` (70)
**LLM calls:** 1

Generates optimized search queries for finding better articles. The `better_alternative_found` flag from the result influences the `action_required` determination.

### Step 4: Conditional Gap Analysis (score < 60)

**Agent:** GapAnalysisAgent
**Trigger:** `best_score < 60`
**LLM calls:** 1

Receives upstream results (relevance, completeness, validity) to identify documentation gaps and suggest content improvements.

### Step 5: Transfer Reason Classification (always, last)

**Agent:** TransferReasonAgent
**Trigger:** Always runs (uses decision tree, not just LLM)
**LLM calls:** 0-1 (LLM escalation detection is conditional)

Synthesizes all upstream scores plus CSV metadata to classify transfer reason. See [Transfer Analysis](transfer-analysis.md).

### Step 6: Build Final Result

The orchestrator assembles all results into an `EvaluationResult`:
- Determines verdict via `ScoringUtils.get_overall_verdict()`
- Determines action via `ScoringUtils.get_action_required()`
- Generates human-readable recommendation
- Returns `EvaluationResult.to_dict()`

## No-Citation Path

When no article URLs are provided, `_handle_no_citation()` runs a simplified pipeline:

1. IssueParserAgent (already complete)
2. DescriptionQualityAgent (already complete)
3. **SearchAgent** — find relevant articles (no current_score context)
4. **GapAnalysisAgent** — identify gaps without an existing article
5. **TransferReasonAgent** — classify with `contains_citations=False`, `overall_score=0`
6. Return `EvaluationResult` with `verdict="no_citation_provided"`, `action_required="find_better_article"`

## Multi-URL Evaluation

When multiple URLs are provided (`article_urls`):

- Each URL is evaluated independently (fetch + relevance + completeness + validity)
- The URL with the **highest overall score** is used as the primary evaluation
- All evaluations are stored in `current_article_evaluation.all_articles` (when > 1 URL)
- Conditional agents (search, gap) trigger based on the **best** score

## Reliability Warning Flow

```
description_quality_score < 40?
    |
   YES --> evaluation_reliability_warning = True
    |       |
    |       +--> "[LOW CONFIDENCE] ..." prefix on recommendation
    |       +--> Flag in EvaluationResult for consumers
    |
    NO --> evaluation_reliability_warning = False
```

## Citation Quality Pipeline (mweaeval)

When running with `--mweaeval`, the orchestrator uses `evaluate_with_citations()` to evaluate AI response quality and citation grounding. This pipeline extends the standard flow with CitationQualityAgent and ResponseQualityAgent.

```
                    START: Orchestrator.evaluate_with_citations()
                              |
                    [Step 1] IssueParserAgent
                         (1 LLM call)
                              |
                    [Step 2] DescriptionQualityAgent
                         (1 LLM call)
                              |
                    [Step 3] CitationQualityAgent
                         (N LLM calls — one per unique citation)
                              |
                         For each citation:
                           fetch article content
                           evaluate support for AI response claims
                              |
                    [Step 3b] R/C/V on best-grounding citation
                         RelevanceAgent  (1 LLM)
                         CompletenessAgent (1 LLM)
                         ValidityAgent  (1 LLM)
                              |
                    [Step 4] ResponseQualityAgent
                         (1 LLM call — evaluates Response Quality + Issue Resolution)
                         (groundedness reused from CitationQualityAgent — free)
                              |
                    [Step 5] TransferReasonAgent
                         (0-1 LLM calls — escalation detection conditional)
                              |
                         _build_final_result()
                              |
                             END
```

## Per-Case LLM Call Count

| Scenario | LLM Calls | Agents Used |
|----------|-----------|-------------|
| No citation | 3-4 | Parser, DQ, Search, Gap + optional escalation |
| Single URL, score >= 70 | 5 | Parser, DQ, Relevance, Completeness, Validity |
| Single URL, 60 <= score < 70 | 6 | Above + Search |
| Single URL, score < 60 | 7 | Above + Search + Gap |
| Multi-URL (N URLs) | 2 + 3N + 0-2 | Parser, DQ, (R+C+V)*N, +Search, +Gap |
| mweaeval, N citations | 5 + N + 0-1 | Parser, DQ, CitationQuality*N, R+C+V (best), ResponseQuality + optional escalation |

The TransferReasonAgent adds 0-1 LLM calls (only for escalation detection on longer texts).
