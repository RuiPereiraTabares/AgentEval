# Data Models Reference

All data models are defined as Python dataclasses in the `article_evaluation_system/models/` package.

## Type Aliases

Defined in `models/evaluation.py`:

```python
IssueType = Literal["configuration", "error", "how-to", "troubleshooting", "performance", "unknown"]
Severity = Literal["low", "medium", "high", "critical"]
ArticleType = Literal["troubleshooting", "how-to", "reference", "tutorial", "unknown"]

RelevanceVerdict = Literal["excellent", "good", "partial", "poor", "irrelevant"]
CompletenessVerdict = Literal["complete", "mostly_complete", "incomplete", "severely_lacking"]
ValidityVerdict = Literal["valid", "likely_valid", "uncertain", "likely_invalid", "invalid"]
ConfidenceLevel = Literal["high", "medium", "low"]
DescriptionQualityVerdict = Literal["well_defined", "mostly_defined", "partially_defined", "poorly_defined"]

TransferReason = Literal[
    "poor_description", "poor_description_bad_citation", "no_citation_found",
    "bad_citation_match", "inadequate_article", "customer_escalation",
    "not_transferred", "unknown"
]

CitationSupportVerdict = Literal["good", "partial", "bad"]
CitationGroundingVerdict = Literal["well_grounded", "partially_grounded", "poorly_grounded", "ungrounded"]
ResponseQualityVerdict = Literal["excellent", "good", "fair", "poor"]

OverallVerdict = Literal["adequate", "needs_supplementation", "inadequate", "no_citation_provided"]
ActionRequired = Literal["none", "add_context", "find_better_article", "create_content"]
GapPriority = Literal["high", "medium", "low"]
GapEffort = Literal["small", "medium", "large"]
GapRecommendation = Literal["augment_existing", "create_new", "combine_multiple"]
```

## Issue

**File:** `models/issue.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `product` | `str` | — | Product name (e.g., "Excel", "Azure") |
| `symptoms` | `list[str]` | — | Observed symptoms |
| `keywords` | `list[str]` | — | Search keywords extracted from description |
| `issue_type` | `IssueType` | — | Classification of the issue |
| `version` | `str \| None` | — | Product version if mentioned |
| `error_codes` | `list[str]` | — | Extracted error codes |
| `environment` | `dict` | — | OS, browser, hardware context |
| `severity` | `Severity` | — | Business impact level |
| `raw_description` | `str` | — | Original customer description |
| `transferred` | `bool \| None` | — | Whether the case was transferred (from CSV) |
| `sr_status` | `str` | — | Service request status (from CSV) |
| `reopened` | `bool \| None` | — | Whether the case was reopened (from CSV) |
| `area_path` | `str \| None` | `None` | Classified area path (e.g. "Teams Meetings") — set by AreaClassificationAgent |
| `area_path_confidence` | `int` | `0` | Confidence score 0-100 for the area classification |

**Methods:** `to_dict()`, `from_dict(dict)`, `get_search_query() -> str`

## Article

**File:** `models/article.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | — | Article URL |
| `title` | `str` | — | Article title |
| `content` | `str` | — | Full article content |
| `last_updated` | `str \| None` | — | Last updated date |
| `applies_to` | `list[str]` | — | Products/versions it applies to |
| `prerequisites` | `list[str]` | — | Prerequisites from article |
| `steps` | `list[str]` | — | Numbered steps from article |
| `article_type` | `ArticleType` | — | Classification of the article |
| `fetch_error` | `str \| None` | — | Error message if fetch failed |

**Properties:** `is_valid: bool` (fetch succeeded), `is_microsoft_article: bool` (from Microsoft domains)

**Methods:** `to_dict()`, `from_dict(dict)`, `get_content_summary(max_length: int) -> str`

## RelevanceResult

**File:** `models/evaluation.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `relevance_score` | `int` | — | 0-100 score |
| `matched_aspects` | `list[str]` | `[]` | Aspects that match the issue |
| `unmatched_aspects` | `list[str]` | `[]` | Aspects not covered |
| `version_match` | `bool` | `True` | Version appropriate? |
| `product_match` | `bool` | `True` | Correct product? |
| `is_outdated` | `bool` | `False` | Outdated solution? |
| `relevance_verdict` | `RelevanceVerdict` | `"partial"` | Verdict label |

## CompletenessResult

**File:** `models/evaluation.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `completeness_score` | `int` | — | 0-100 score |
| `has_prerequisites` | `bool` | `False` | Has prerequisites section? |
| `has_step_by_step` | `bool` | `False` | Has step-by-step instructions? |
| `has_examples` | `bool` | `False` | Has examples/screenshots? |
| `has_troubleshooting` | `bool` | `False` | Has troubleshooting guidance? |
| `has_success_criteria` | `bool` | `False` | Has verification steps? |
| `missing_elements` | `list[str]` | `[]` | Missing sections |
| `completeness_verdict` | `CompletenessVerdict` | `"incomplete"` | Verdict label |

## ValidityResult

**File:** `models/evaluation.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `validity_score` | `int` | — | 0-100 score |
| `addresses_root_cause` | `bool` | `False` | Addresses root cause? |
| `is_current_solution` | `bool` | `True` | Not deprecated? |
| `environment_compatible` | `bool` | `True` | Compatible with environment? |
| `potential_issues` | `list[str]` | `[]` | Caveats or risks |
| `confidence_level` | `ConfidenceLevel` | `"medium"` | Agent confidence |
| `validity_verdict` | `ValidityVerdict` | `"uncertain"` | Verdict label |

## DescriptionQualityResult

**File:** `models/evaluation.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `identity_score` | `int` | `0` | WHAT dimension (0-100) |
| `location_score` | `int` | `0` | WHERE dimension (0-100) |
| `timing_score` | `int` | `0` | WHEN dimension (0-100) |
| `magnitude_score` | `int` | `0` | EXTENT dimension (0-100) |
| `identity_analysis` | `str` | `""` | WHAT analysis text |
| `location_analysis` | `str` | `""` | WHERE analysis text |
| `timing_analysis` | `str` | `""` | WHEN analysis text |
| `magnitude_analysis` | `str` | `""` | EXTENT analysis text |
| `description_quality_score` | `int` | `0` | Weighted overall score (0-100) |
| `description_quality_verdict` | `DescriptionQualityVerdict` | `"poorly_defined"` | Verdict label |
| `missing_kt_elements` | `list[str]` | `[]` | Missing KT elements |
| `improvement_suggestions` | `list[str]` | `[]` | Suggestions for improvement |

## SearchResult

**File:** `models/evaluation.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `recommended_articles` | `list[RecommendedArticle]` | `[]` | Recommended articles |
| `search_terms_used` | `list[str]` | `[]` | Search queries generated |
| `better_alternative_found` | `bool` | `False` | Found a better article? |

### RecommendedArticle

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | — | Article URL |
| `title` | `str` | — | Article title |
| `relevance_reason` | `str` | — | Why this article is relevant |
| `estimated_match_score` | `int` | — | Estimated relevance score |
| `last_updated` | `str \| None` | `None` | Last updated date |
| `article_type` | `str` | `"unknown"` | Article type |

## GapAnalysisResult

**File:** `models/evaluation.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `documentation_gaps` | `list[str]` | `[]` | Identified gaps |
| `suggested_content_outline` | `list[str]` | `[]` | Suggested new content |
| `required_expertise` | `list[str]` | `[]` | Expertise needed to fill gaps |
| `priority` | `GapPriority` | `"medium"` | Priority level |
| `estimated_effort` | `GapEffort` | `"medium"` | Effort estimate |
| `recommendation` | `GapRecommendation` | `"augment_existing"` | Recommended action |

## TransferReasonResult

**File:** `models/evaluation.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `transfer_reason` | `TransferReason` | `"unknown"` | Classification result |
| `confidence` | `ConfidenceLevel` | `"medium"` | Classification confidence |
| `transferred` | `bool \| None` | `None` | Whether case was transferred |
| `sr_status` | `str` | `""` | Service request status |
| `reopened` | `bool \| None` | `None` | Whether case was reopened |
| `contributing_factors` | `list[str]` | `[]` | Factors leading to this classification |
| `description_quality_score` | `int` | `0` | Snapshot of upstream DQ score |
| `overall_article_score` | `int` | `0` | Snapshot of upstream overall score |
| `relevance_score` | `int` | `0` | Snapshot of upstream relevance score |
| `contains_citations` | `bool` | `False` | Whether case had citations |
| `escalation_signals_detected` | `list[str]` | `[]` | Detected escalation signals |
| `narrative` | `str` | `""` | Human-readable explanation |

## PerCitationResult

**File:** `models/evaluation.py`

Result for a single citation evaluated by CitationQualityAgent.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | — | Citation URL |
| `support_score` | `int` | `0` | 0-100 score for how well this citation supports the AI response |
| `support_verdict` | `CitationSupportVerdict` | `"bad"` | Verdict label |
| `support_analysis` | `str` | `""` | Analysis text |
| `fetch_success` | `bool` | `False` | Whether the article was successfully fetched |

## CitationQualityResult

**File:** `models/evaluation.py`

Aggregated result from CitationQualityAgent across all citations.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `per_citation_results` | `list[PerCitationResult]` | `[]` | Individual results per citation |
| `best_citation_url` | `str` | `""` | URL of the citation with the highest support score |
| `best_citation_score` | `int` | `0` | Highest support score across all citations |
| `grounding_score` | `int` | `0` | Overall grounding score (0-100) |
| `grounding_verdict` | `CitationGroundingVerdict` | `"ungrounded"` | Overall grounding verdict |

## ResponseQualityResult

**File:** `models/evaluation.py`

Result from ResponseQualityAgent combining response quality, groundedness, and issue resolution.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `response_quality_score` | `int` | `0` | Response quality dimension score (0-100) |
| `response_quality_analysis` | `str` | `""` | Response quality analysis text |
| `groundedness_score` | `int` | `0` | Groundedness dimension score (0-100) |
| `groundedness_analysis` | `str` | `""` | Groundedness analysis text |
| `issue_resolution_score` | `int` | `0` | Issue resolution dimension score (0-100) |
| `issue_resolution_analysis` | `str` | `""` | Issue resolution analysis text |
| `ai_response_quality_score` | `int` | `0` | Weighted overall score (0-100) |
| `ai_response_quality_verdict` | `ResponseQualityVerdict` | `"poor"` | Overall verdict label |
| `quality_weaknesses` | `list[str]` | `[]` | Identified weaknesses in the AI response |
| `improvement_suggestions` | `list[str]` | `[]` | Suggestions for improving the AI response |

## EvaluationResult

**File:** `models/evaluation.py`

The final output model returned by the Orchestrator.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `issue_summary` | `dict` | `{}` | Parsed issue data (`Issue.to_dict()`) |
| `current_article_evaluation` | `dict` | `{}` | URL, title, relevance, completeness, validity |
| `overall_score` | `int` | `0` | Weighted overall score (0-100) |
| `verdict` | `OverallVerdict` | `"inadequate"` | Final verdict |
| `action_required` | `ActionRequired` | `"find_better_article"` | Recommended next step |
| `recommended_articles` | `list[dict]` | `[]` | From SearchAgent |
| `content_gaps` | `dict` | `{}` | From GapAnalysisAgent |
| `final_recommendation` | `str` | `""` | Human-readable summary |
| `description_quality` | `dict` | `{}` | From DescriptionQualityAgent |
| `evaluation_reliability_warning` | `bool` | `False` | Low confidence flag |
| `transfer_analysis` | `dict` | `{}` | From TransferReasonAgent |
| `response_quality` | `dict` | `{}` | From ResponseQualityAgent (mweaeval mode only) |

## TrendCluster

**File:** `models/evaluation.py`

Output model from `TrendSynthesizer.synthesize_trends()`. Represents one cluster of semantically-similar cases that can be addressed by a single PM action.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cluster_name` | `str` | `""` | Short descriptive name for this trend pattern |
| `case_count` | `int` | `0` | Number of cases in this cluster |
| `case_numbers` | `list[str]` | `[]` | Case identifiers included |
| `root_cause_pattern` | `str` | `""` | Common root cause across these cases |
| `products_affected` | `list[str]` | `[]` | Distinct products in this cluster |
| `unified_pm_action` | `str` | `""` | ONE specific, actionable recommendation |
| `estimated_impact` | `str` | `""` | Human-readable impact estimate |
| `priority` | `str` | `""` | `"red"`, `"yellow"`, or `"green"` |
| `supporting_evidence` | `list[str]` | `[]` | Key findings from individual cases |
| `area_path` | `str` | `""` | Primary area path that defines this cluster |

**Methods:** `to_dict()`, `from_dict(dict)`

---

## CitationOverlap

**File:** `models/evaluation.py`

Output model from `TrendSynthesizer._build_citation_overlaps()`. Identifies article URLs cited by multiple cases, flagging hidden cross-coverage risks and potential duplicate cases.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | `""` | The shared article URL |
| `overlap_type` | `str` | `""` | `"duplicate_issues"` (Jaccard ≥ 0.35) or `"cross_coverage"` (< 0.35) |
| `case_count` | `int` | `0` | Number of cases citing this URL |
| `case_numbers` | `list[str]` | `[]` | Case identifiers that cite this URL |
| `similarity_score` | `float` | `0.0` | Average pairwise Jaccard similarity between issue descriptions |
| `issue_snippets` | `list[str]` | `[]` | First 150 chars of each case's issue description |
| `flag_reason` | `str` | `""` | Why this overlap was flagged |
| `recommendation` | `str` | `""` | Suggested action for the PM |

**Similarity thresholds:**

| Score | `overlap_type` | Meaning |
|-------|----------------|---------|
| ≥ 0.35 | `duplicate_issues` | Same problem described repeatedly — consolidation candidate |
| < 0.35 | `cross_coverage` | Different problems share one article — changes have hidden impact |
| < 0.15 | *(not grouped)* | Too dissimilar for deterministic fallback clustering |

**Methods:** `to_dict()`, `from_dict(dict)`

---

## Label Normalization Maps

LLMs return unpredictable label variants. Four label maps in `models/evaluation.py` normalize them to numeric scores:

- **`_RELEVANCE_LABEL_MAP`** — ~40 entries mapping labels like `"excellent"` -> 95, `"tangential"` -> 25, `"irrelevant"` -> 5
- **`_COMPLETENESS_LABEL_MAP`** — ~40 entries mapping labels like `"comprehensive"` -> 95, `"limited"` -> 40, `"empty"` -> 0
- **`_VALIDITY_LABEL_MAP`** — ~40 entries mapping labels like `"confirmed"` -> 90, `"questionable"` -> 45, `"ineffective"` -> 10
- **`_DESCRIPTION_QUALITY_LABEL_MAP`** — ~30 entries mapping labels like `"thorough"` -> 85, `"vague"` -> 20, `"missing"` -> 0
- **`_RESPONSE_QUALITY_LABEL_MAP`** — maps labels for AI response quality verdicts (e.g., `"excellent"` -> 90, `"good"` -> 70, `"fair"` -> 50, `"poor"` -> 20)
- **`_CITATION_SUPPORT_LABEL_MAP`** — maps labels for citation support verdicts (e.g., `"good"` -> 80, `"partial"` -> 55, `"bad"` -> 15)

## Score Parsing Helpers

**`_parse_numeric_string(val: str) -> int | None`** handles:

| Input | Output |
|-------|--------|
| `"70"` | `70` |
| `"70%"` | `70` |
| `"7/10"` | `70` |
| `"7 out of 10"` | `70` |

**`_extract_score(flat, score_key, label_keys, label_map, default)`** tries in order:

1. Direct numeric value from the expected key
2. Generic `"score"` key
3. Label map lookup across multiple alternative key names
4. Last-resort scan of all values in the flattened dict

**`_collect_all_values(data: dict) -> dict`** recursively flattens nested dicts with lowercase keys, enabling resilient field extraction regardless of LLM response structure.
