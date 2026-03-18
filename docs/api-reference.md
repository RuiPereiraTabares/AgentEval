# API & CLI Reference

## Programmatic API

### ArticleEvaluator

**File:** `article_evaluation_system/__init__.py`

The main entry point for the evaluation system.

```python
from article_evaluation_system import ArticleEvaluator

evaluator = ArticleEvaluator(
    mwai_token=None            # MWAI bearer token (or set MWAI_TOKEN env var)
)
```

#### `evaluate()`

```python
result = evaluator.evaluate(
    customer_issue="Users cannot access SharePoint...",
    recommended_article="https://support.microsoft.com/...",  # optional
    product_info={                                             # optional
        "sap_product_name": "SharePoint Online",
        "sap_product_family": "Microsoft 365",
        "sap_path": "M365/SharePoint",
        "sap_name": "SharePoint",
    },
    transfer_metadata={                                        # optional
        "transferred": True,
        "sr_status": "Active",
        "reopened": False,
    },
)
```

**Returns:** `dict` — serialized `EvaluationResult`. See [Return Value Structure](#return-value-structure) below.

#### `evaluate_batch()`

```python
results = evaluator.evaluate_batch(
    cases=[
        {"issue": "Error in Teams...", "article_url": "https://..."},
        {"issue": "Azure VM won't start...", "article_url": None},
    ],
    progress_callback=lambda done, total: print(f"{done}/{total}")
)
```

**Returns:** `list[dict]` — list of evaluation results.

### Return Value Structure

The `evaluate()` method returns a dict with this shape:

```json
{
    "issue_summary": {
        "product": "SharePoint Online",
        "symptoms": ["cannot access site", "error 0x80004005"],
        "keywords": ["sharepoint", "access denied", "0x80004005"],
        "issue_type": "error",
        "version": "Microsoft 365",
        "error_codes": ["0x80004005"],
        "environment": {"os": "Windows 11", "browser": "Edge"},
        "severity": "high",
        "raw_description": "...",
        "transferred": true,
        "sr_status": "Active",
        "reopened": false
    },
    "current_article_evaluation": {
        "url": "https://support.microsoft.com/...",
        "title": "Fix SharePoint access issues",
        "relevance": {
            "relevance_score": 75,
            "matched_aspects": ["product", "error code"],
            "unmatched_aspects": ["specific tenant config"],
            "version_match": true,
            "product_match": true,
            "is_outdated": false,
            "relevance_verdict": "good"
        },
        "completeness": {
            "completeness_score": 65,
            "has_prerequisites": true,
            "has_step_by_step": true,
            "has_examples": false,
            "has_troubleshooting": true,
            "has_success_criteria": false,
            "missing_elements": ["screenshots", "verification steps"],
            "completeness_verdict": "incomplete"
        },
        "validity": {
            "validity_score": 70,
            "addresses_root_cause": true,
            "is_current_solution": true,
            "environment_compatible": true,
            "potential_issues": ["may not apply to hybrid setups"],
            "confidence_level": "medium",
            "validity_verdict": "likely_valid"
        },
        "all_articles": null
    },
    "overall_score": 70,
    "verdict": "needs_supplementation",
    "action_required": "add_context",
    "recommended_articles": [],
    "content_gaps": {},
    "final_recommendation": "The article partially addresses the issue...",
    "description_quality": {
        "identity_score": 80,
        "location_score": 60,
        "timing_score": 40,
        "magnitude_score": 50,
        "identity_analysis": "Product and error code clearly identified",
        "location_analysis": "General environment mentioned",
        "timing_analysis": "No specific start date",
        "magnitude_analysis": "Some users mentioned",
        "description_quality_score": 61,
        "description_quality_verdict": "mostly_defined",
        "missing_kt_elements": ["start date", "user count"],
        "improvement_suggestions": ["Add specific date", "Quantify affected users"]
    },
    "evaluation_reliability_warning": false,
    "transfer_analysis": {
        "transfer_reason": "inadequate_article",
        "confidence": "medium",
        "transferred": true,
        "sr_status": "Active",
        "reopened": false,
        "contributing_factors": ["Description quality adequate...", "Citation is relevant but..."],
        "description_quality_score": 61,
        "overall_article_score": 70,
        "relevance_score": 75,
        "contains_citations": true,
        "escalation_signals_detected": [],
        "narrative": "The description was adequate..."
    }
}
```

## CLI: `run_evaluation.py`

The primary CLI runner. Uses MWAI as the LLM provider.

### Usage

```bash
# Test mode (first 50 cases)
python run_evaluation.py

# Process all cases
python run_evaluation.py --all

# First N cases
python run_evaluation.py -n 10

# Specific case
python run_evaluation.py --case 2508270010003948

# Skip first N, then process M
python run_evaluation.py --skip 100 -n 50

# Custom input file
python run_evaluation.py -i my_cases.csv

# Verbose output (per-agent breakdowns)
python run_evaluation.py -v

# Debug output (raw LLM prompts and responses)
python run_evaluation.py --debug

# CSV output
python run_evaluation.py --format csv
```

### MWAI Authentication Examples

```bash
# Interactive token prompt (default):
python run_evaluation.py

# Explicit token:
python run_evaluation.py --token eyJ0eX...

# Force new token:
python run_evaluation.py --new-token
```

### Output File Naming

When `--output` is not specified, files are auto-named with a timestamp:

- **Detailed:** `evaluation_results_{YYYYMMDD_HHMMSS}.{json|csv}`
- **Summary:** `evaluation_summary_{YYYYMMDD_HHMMSS}.csv` (always produced)

### Full Argument Reference

See [Configuration > CLI Arguments](configuration.md#cli-arguments).

## CSV Input Format

**File:** CSV with header row. Encoding: UTF-8 (with BOM) or CP1252 (auto-detected).

### Required Columns

| Column | Description |
|--------|-------------|
| `Case Number` (or `CaseNumber`) | Unique case identifier |
| `IssueDescription` | Customer issue text |

### Optional Columns

| Column | Description |
|--------|-------------|
| `Title_mwai` (or `Title`) | Case title (prepended to description) |
| `Language` | Language code (default: `en-US`) |
| `EmailType` | Email type classification |
| `ContainsCitations` | `TRUE`/`FALSE` — whether URLs were cited |
| `Urls` | Comma-separated article URLs |
| `UngroundedPercentage` | Percentage of ungrounded content |
| `ErrorType` | Error type classification |
| `DateTime` | Case datetime |
| `SapProductName` | Product name from SAP taxonomy |
| `SapProductFamily` | Product family from SAP taxonomy |
| `SapPath_mwai` (or `SapPath`) | SAP path |
| `SapName` | SAP short name |
| `Transferred` | `TRUE`/`FALSE` — whether case was transferred |
| `SRStatus` (or `SR Status`) | Service request status |
| `Reopened` | `TRUE`/`FALSE` — whether case was reopened |

## CSV Output Format

### Detailed CSV (~45 columns)

Produced by `write_results_csv()`. Contains every field from the evaluation:

**Core:** `case_number`, `issue_product`, `issue_type`, `article_url`, `overall_score`, `verdict`, `action_required`

**Relevance:** `relevance_score`, `relevance_verdict`, `relevance_matched_aspects`, `relevance_unmatched_aspects`, `relevance_product_match`, `relevance_version_match`, `relevance_is_outdated`

**Completeness:** `completeness_score`, `completeness_verdict`, `completeness_missing_elements`, `completeness_has_prerequisites`, `completeness_has_step_by_step`, `completeness_has_examples`, `completeness_has_troubleshooting`, `completeness_has_success_criteria`

**Validity:** `validity_score`, `validity_verdict`, `validity_potential_issues`, `validity_addresses_root_cause`, `validity_is_current_solution`, `validity_environment_compatible`, `validity_confidence_level`

**Description Quality:** `description_quality_score`, `description_quality_verdict`, `kt_identity_score`, `kt_location_score`, `kt_timing_score`, `kt_magnitude_score`, `kt_identity_analysis`, `kt_location_analysis`, `kt_timing_analysis`, `kt_magnitude_analysis`, `kt_missing_elements`, `kt_improvement_suggestions`, `evaluation_reliability_warning`

**Transfer:** `transfer_reason`, `transfer_confidence`, `transferred`, `sr_status`, `reopened`, `transfer_contributing_factors`, `transfer_escalation_signals`, `transfer_narrative`

**Summary:** `final_recommendation`, `processing_time_ms`, `error`

List fields use `; ` as separator.

### Summary CSV (21 columns)

Produced by `write_results_csv_summary()`. Key scores and reasons only:

`case_number`, `overall_score`, `verdict`, `relevance_score`, `relevance_verdict`, `relevance_matched`, `relevance_unmatched`, `completeness_score`, `completeness_verdict`, `completeness_missing`, `validity_score`, `validity_verdict`, `validity_issues`, `description_quality_score`, `description_quality_verdict`, `description_missing`, `description_improvements`, `transfer_reason`, `transfer_narrative`, `final_recommendation`, `error`

## JSON Output Format

Produced by `write_results_json()`. Array of result objects:

```json
[
    {
        "case_number": "2508270010003948",
        "evaluation": { /* full EvaluationResult.to_dict() */ },
        "processing_time_seconds": 12.5,
        "error": null
    }
]
```
