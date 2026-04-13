# Agent Reference

The system contains 13 agent classes: 1 base class, 1 orchestrator, and 11 specialized evaluation agents. All inherit from `BaseAgent` and follow the same evaluate/fallback pattern. `TrendSynthesizer` is an additional non-pipeline class that clusters batch results.

## BaseAgent

**File:** `agents/__init__.py`

Abstract base class for all agents.

```python
class BaseAgent(ABC):
    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai")
    def evaluate(self, **kwargs) -> dict           # Abstract
    def _call_llm(self, system_prompt, user_message) -> str
    def _parse_json_response(self, response) -> dict
    def set_llm_callable(self, callable_fn)        # Inject custom LLM
```

See [Architecture > BaseAgent](architecture.md#baseagent-class) for details on `_call_llm()` and `_parse_json_response()` 3-stage parsing.

---

## IssueParserAgent

**File:** `agents/issue_parser.py`
**Role:** Parse raw customer issue text into a structured `Issue` object.
**LLM Prompt:** `AgentPrompts.ISSUE_PARSER`

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue_description` | `str` | Raw customer issue text |
| `product_info` | `dict \| None` | SAP product metadata from CSV |

**Output:** `Issue` dataclass

**Extracted fields:** product, version, error_codes, symptoms, issue_type, keywords (5-10 search terms), environment, severity

**Fallback:** On LLM failure, uses `_extract_fallback_keywords()` for keyword extraction and `_guess_product()` for product detection via regex matching.

---

## AreaClassificationAgent

**File:** `agents/area_classification_agent.py`
**Role:** Classify a parsed issue into a product-specific area path (e.g., "Teams Meetings", "Teams Calling (PSTN)"). Runs immediately after `IssueParserAgent`, before `DescriptionQualityAgent`.
**LLM Prompt:** Dynamic — built at runtime from the product's area taxonomy in `config/area_definitions.py`.

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue` | `Issue` | Parsed issue object — must have `product` and `raw_description` set |

**Output:** `dict` with `area_path`, `area_confidence`, `area_reasoning` — or `None` if no area definitions are configured for the detected product.

**Area taxonomy:** Defined in `config/area_definitions.py` under `PRODUCT_AREA_DEFINITIONS`. Each product family maps to a list of named areas with descriptions. Product matching uses case-insensitive substring matching via `_PRODUCT_ALIASES`.

**Teams areas (17):** Teams Admin · Teams and Channels · Teams and Copilot · Teams Apps and Connectors · Teams Calling (PSTN) · Teams Chat (Messaging) · Teams Clients · Teams Devices · Teams EDU · Teams External and Guest Access · Teams Files · Teams Hybrid and Migration · Teams Identity and Authentication · Teams Meetings · Teams Media · Teams People & Presence · Teams Security and Compliance

**Extending to new products:** Add a new key to `PRODUCT_AREA_DEFINITIONS` and a matching alias in `_PRODUCT_ALIASES` in `area_definitions.py`. No agent code changes required.

**Fallback:** Returns `None` on LLM failure or unknown area name. The issue proceeds without an area path — no pipeline step is blocked.

**Result stored on:** `issue.area_path` (str | None) and `issue.area_path_confidence` (int 0-100).

---

## DescriptionQualityAgent

**File:** `agents/description_quality_agent.py`
**Role:** Evaluate issue description quality using the Kepner-Tregoe framework.
**LLM Prompt:** `AgentPrompts.DESCRIPTION_QUALITY_AGENT`

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue` | `Issue` | Parsed customer issue |

**Output:** `DescriptionQualityResult`

**Scoring:** Weighted across 4 KT dimensions — Identity/WHAT (35%), Location/WHERE (25%), Timing/WHEN (20%), Magnitude/EXTENT (20%).

**Verdict thresholds:** well_defined (80+), mostly_defined (60-79), partially_defined (40-59), poorly_defined (<40)

**Fallback:** Heuristic keyword detection for location (server, tenant, region), timing (date patterns, temporal words), and magnitude (user counts, percentages).

See [KT Framework](kt-framework.md) for the full scoring guide.

---

## RelevanceAgent

**File:** `agents/relevance_agent.py`
**Role:** Evaluate how well an article matches the customer's issue.
**LLM Prompt:** `AgentPrompts.RELEVANCE_AGENT`

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue` | `Issue` | Parsed customer issue |
| `article` | `Article` | Fetched article content |

**Output:** `RelevanceResult`

**Evaluates:** Product match, version match, error code match, symptom match, recency.

**Scoring guide:**
- 90-100: Excellent — directly addresses the exact issue
- 70-89: Good — most aspects covered
- 50-69: Partial — related but with gaps
- 30-49: Poor — tangentially related
- 0-29: Irrelevant — does not match

**Fallback:** Returns score 30 (poor) with empty matched/unmatched aspects.

---

## CompletenessAgent

**File:** `agents/completeness_agent.py`
**Role:** Check whether an article provides complete information to resolve the issue.
**LLM Prompt:** `AgentPrompts.COMPLETENESS_AGENT`

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue` | `Issue` | Parsed customer issue |
| `article` | `Article` | Fetched article content |

**Output:** `CompletenessResult`

**Checks for:** Prerequisites section, step-by-step instructions, examples/screenshots, troubleshooting guidance, success criteria/verification steps.

**Scoring guide:**
- 90-100: Complete — all sections present
- 70-89: Mostly complete — minor gaps
- 50-69: Incomplete — significant gaps
- 0-49: Severely lacking — insufficient content

**Fallback:** Keyword-based section detection (scans article content for section headers and instruction patterns).

---

## ValidityAgent

**File:** `agents/validity_agent.py`
**Role:** Determine whether the article's solution would actually work for the customer's issue.
**LLM Prompt:** `AgentPrompts.VALIDITY_AGENT`

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue` | `Issue` | Parsed customer issue |
| `article` | `Article` | Fetched article content |

**Output:** `ValidityResult`

**Evaluates:** Root cause vs. symptom treatment, solution currency (not deprecated), environment compatibility, potential issues/caveats.

**Scoring guide:**
- 80-100: Valid — solution is correct and current
- 60-79: Likely valid — probably works
- 40-59: Uncertain — questionable effectiveness
- 20-39: Likely invalid — probably does not work
- 0-19: Invalid — incorrect or deprecated

**Fallback:** Returns score 50 (uncertain) with confidence "low".

---

## SearchAgent

**File:** `agents/search_agent.py`
**Role:** Generate optimized search queries to find alternative articles when the current one is insufficient.
**LLM Prompt:** `AgentPrompts.SEARCH_AGENT`

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue` | `Issue` | Parsed customer issue |
| `current_score` | `int` | Current best article score (0-100) |

**Output:** `SearchResult`

**Triggered when:** `best_score < 70`

**Generates:** 3-5 optimized search queries with reasoning, recommended search domains (support.microsoft.com, learn.microsoft.com).

**Key methods:**
- `_extract_queries_from_text()` — parse plain-text LLM responses
- `_generate_fallback_searches()` — heuristic query construction from issue data
- `generate_search_urls()` — build full search URLs from queries

**Fallback:** Constructs queries from issue product, keywords, and error codes.

---

## GapAnalysisAgent

**File:** `agents/gap_agent.py`
**Role:** Identify documentation gaps when no adequate article exists.
**LLM Prompt:** `AgentPrompts.GAP_ANALYSIS_AGENT`

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue` | `Issue` | Parsed customer issue |
| `relevance_result` | `RelevanceResult \| None` | From RelevanceAgent |
| `completeness_result` | `CompletenessResult \| None` | From CompletenessAgent |
| `validity_result` | `ValidityResult \| None` | From ValidityAgent |

**Output:** `GapAnalysisResult`

**Triggered when:** `best_score < 60`

**Produces:** Documentation gaps list, suggested content outline, required expertise, priority, effort estimate, and recommendation (augment existing / create new / combine multiple).

**Fallback:** Derives gap analysis from upstream evaluation results (missing elements from completeness, unmatched aspects from relevance).

---

## TransferReasonAgent

**File:** `agents/transfer_reason_agent.py`
**Role:** Classify the root cause of why a support case was transferred. Runs **last** in the pipeline.
**LLM Prompt:** `AgentPrompts.TRANSFER_REASON_ESCALATION_DETECTION` (for escalation detection only)

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue` | `Issue` | Parsed issue (with transfer metadata) |
| `description_quality_result` | `DescriptionQualityResult \| None` | From DescriptionQualityAgent |
| `overall_score` | `int` | Overall article evaluation score |
| `relevance_score` | `int` | From RelevanceAgent |
| `contains_citations` | `bool` | Whether case had article citations |
| `verdict` | `str` | Overall verdict from orchestrator |

**Output:** `TransferReasonResult`

**Classification:** 8 categories via a cascading decision tree. See [Transfer Analysis](transfer-analysis.md) for the full decision tree, escalation detection patterns, and narrative templates.

---

## CitationQualityAgent

**File:** `agents/citation_quality_agent.py`
**Role:** Evaluate whether cited articles support the claims made in the AI response.
**LLM Prompt:** `AgentPrompts.CITATION_QUALITY_AGENT`

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `ai_response` | `str` | The AI-generated response text |
| `citation_urls` | `list[str]` | List of citation URLs from the response |
| `article_fetcher` | `ArticleFetcher` | Fetcher instance for retrieving citation content |

**Output:** `CitationQualityResult`

**Evaluation flow:** One LLM call per unique citation URL. Each citation is fetched and evaluated against the AI response claims it is supposed to support.

**Scoring:**
- 70+: `good` — citation strongly supports the claims
- 40-69: `partial` — citation partially supports the claims
- 0-39: `bad` — citation does not support the claims

**Fallback:** Returns score 0 (`bad`) for citations that fail to fetch or when the LLM call fails.

---

## ResponseQualityAgent

**File:** `agents/response_quality_agent.py`
**Role:** Multi-dimensional AI response quality evaluation combining response quality, groundedness, and issue resolution.
**LLM Prompt:** `AgentPrompts.RESPONSE_QUALITY_AGENT`

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue` | `Issue` | Parsed customer issue |
| `ai_response` | `str` | The AI-generated response text |
| `citation_quality_result` | `CitationQualityResult` | Result from CitationQualityAgent |

**Output:** `ResponseQualityResult`

**LLM calls:** 1 LLM call evaluating Response Quality + Issue Resolution together. Groundedness is reused from CitationQualityAgent (free — no additional LLM call).

**Scoring weights:**

| Dimension | Weight | Description |
|-----------|--------|-------------|
| `response_quality` | 0.40 | Clarity, completeness, and usefulness of the response |
| `groundedness` | 0.30 | How well the response is supported by cited sources |
| `issue_resolution` | 0.30 | How effectively the response addresses the customer's issue |

**Verdict thresholds:**
- 80+: `excellent`
- 60-79: `good`
- 40-59: `fair`
- <40: `poor`

**Fallback:** Returns groundedness-only score when the LLM call fails.

---

## Orchestrator

**File:** `agents/orchestrator.py`
**Role:** Coordinate all agents, manage the evaluation pipeline, and produce the final result.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `customer_issue` | `str` | Raw issue description |
| `article_url` | `str \| None` | Single article URL |
| `article_urls` | `list[str] \| None` | Multiple article URLs |
| `product_info` | `dict \| None` | SAP product metadata |
| `transfer_metadata` | `dict \| None` | transferred, sr_status, reopened |

**Output:** `dict` (serialized `EvaluationResult`)

**Coordination logic:**

1. Initializes all 11 agents with the same client/model/provider
2. Parses issue via IssueParserAgent
3. Classifies into area path via AreaClassificationAgent (result stored on `issue.area_path`)
4. Runs DescriptionQualityAgent, checks reliability threshold
4. For multi-URL cases, evaluates each article and keeps the **best score**
5. Conditionally triggers SearchAgent and GapAnalysisAgent
6. Runs TransferReasonAgent last (needs all upstream scores)
7. Builds final result with `_build_final_result()` or `_handle_no_citation()`

**Citation quality path (`evaluate_with_citations()`):** When running in `--mweaeval` mode, the orchestrator uses `evaluate_with_citations()` which coordinates the CitationQualityAgent and ResponseQualityAgent in addition to the standard pipeline agents.

**No-citation path:** When no URLs are provided, the orchestrator calls `_handle_no_citation()` which runs SearchAgent and GapAnalysisAgent immediately, then TransferReasonAgent with `contains_citations=False`.

See [Pipeline](pipeline.md) for the complete step-by-step flowchart.

---

## TrendSynthesizer

**File:** `synthesis/trend_synthesis.py`
**Role:** Post-processing batch analysis. Clusters evaluated cases by semantic pattern and produces 3-7 unified PM actions. Also detects citation overlaps across cases.

**Usage:** Called from `run_evaluation.py` when `--trend-report` is passed. Not part of the per-case evaluation pipeline.

```python
synthesizer = TrendSynthesizer(client=..., model=..., provider=...)
result = synthesizer.synthesize_trends(results)
# result = { "clusters": [...], "executive_summary": "...", "citation_overlaps": [...] }
```

**Key methods:**

| Method | Description |
|--------|-------------|
| `synthesize_trends(results)` | Main entry point. Calls LLM for clustering, then runs overlap detection. |
| `_build_case_summaries(results)` | Compacts each result to ~200 tokens including `issue_description` (first 300 chars) |
| `_build_citation_overlaps(results, summaries)` | Finds URLs cited by ≥2 cases; computes pairwise Jaccard similarity to classify as `duplicate_issues` or `cross_coverage` |
| `_jaccard(text_a, text_b)` | Token-set Jaccard similarity (tokens > 2 chars only) |
| `_extract_urls(result)` | Extracts all article URLs from a case result (primary + per-citation) |
| `_deterministic_fallback(summaries)` | Groups by area+root_cause when LLM fails; applies Jaccard ≥ 0.15 guard to avoid lumping dissimilar cases |
| `_synthesize_chunk(summaries)` | Single LLM call for ≤100 cases |
| `_merge_clusters(clusters)` | Second LLM pass to reduce >7 clusters from chunked processing |

**Prompt:** `AgentPrompts.TREND_SYNTHESIS` — includes rule 8 requiring semantic similarity within an area group before merging cases.

**Output:** Adds `"citation_overlaps"` key to the returned dict alongside `"clusters"` and `"executive_summary"`. Overlap list is sorted: `cross_coverage` first, then by `case_count` descending.

**Fallback:** `_deterministic_fallback()` — groups by area_path + root_cause_category with Jaccard ≥ 0.15 centroid check. Returns `citation_overlaps: []` (overlap detection requires raw results which the fallback receives).

> **Note:** `TrendSynthesizer` inherits `BaseAgent` for LLM access but does not implement `evaluate()` — call `synthesize_trends()` directly.
