# Copilot Instructions — Agentic Insight Engine

## Project overview

**Agentic Insight Engine** (`AgentEval`) is a multi-agent AI system that evaluates whether Microsoft support articles adequately address customer support cases. It reads cases from CSV files, fetches the cited articles, runs up to 9 specialised AI agents, and produces a scored verdict with actionable recommendations.

- Language: **Python 3.12**
- AI provider: **MWAI** (Microsoft internal API, OpenAI-compatible endpoint)
- Default model: `gpt-4o`
- Entry point: `run_evaluation.py`
- Main package: `article_evaluation_system/`

---

## Repository layout

```
AgentEval/
├── run_evaluation.py                 # CLI runner — argparse entrypoint
├── requirements.txt
├── .env                              # MWAI_TOKEN (not committed)
├── merged_output.csv                 # Default input CSV
├── evaluation_results_<ts>.csv       # Output: full results
├── evaluation_summary_<ts>.csv       # Output: summary
├── trend_report_<ts>.csv             # Output: trend clusters (opt-in: --trend-report)
├── citation_overlaps_<ts>.csv        # Output: citation overlap analysis (auto with trend report)
├── article_evaluation_system/        # Main package
│   ├── __init__.py                   # ArticleEvaluator (public API)
│   ├── main.py                       # CSV I/O helpers + alternative CLI
│   ├── agents/
│   │   ├── __init__.py               # BaseAgent abstract class
│   │   ├── orchestrator.py           # Orchestrator — coordinates all agents
│   │   ├── issue_parser.py           # IssueParserAgent
│   │   ├── relevance_agent.py        # RelevanceAgent
│   │   ├── completeness_agent.py     # CompletenessAgent
│   │   ├── validity_agent.py         # ValidityAgent
│   │   ├── search_agent.py           # SearchAgent
│   │   ├── gap_agent.py              # GapAnalysisAgent
│   │   ├── description_quality_agent.py  # DescriptionQualityAgent (KT framework)
│   │   ├── citation_quality_agent.py # CitationQualityAgent
│   │   ├── response_quality_agent.py # ResponseQualityAgent
│   │   └── transfer_reason_agent.py  # TransferReasonAgent (standalone)
│   ├── models/
│   │   ├── issue.py                  # Issue dataclass (+ area_path, area_path_confidence)
│   │   ├── article.py                # Article dataclass
│   │   └── evaluation.py             # EvaluationResult + all result dataclasses (incl. TrendCluster, CitationOverlap)
│   ├── config/
│   │   ├── settings.py               # THRESHOLDS, KT_DIMENSION_WEIGHTS, SCORE_WEIGHTS, Settings
│   │   └── area_definitions.py       # PRODUCT_AREA_DEFINITIONS (Teams: 17 areas; extensible)
│   ├── utils/
│   │   ├── mwai_client.py            # MwaiClient + resolve_mwai_token()
│   │   ├── article_fetcher.py        # ArticleFetcher (HTTP fetch + HTML→text)
│   │   ├── citation_parser.py        # CitationParser (parse [N] markers)
│   │   ├── prompts.py                # AgentPrompts (all system prompts, incl. TREND_SYNTHESIS)
│   │   └── scoring.py                # ScoringUtils (score math + verdicts)
│   └── synthesis/
│       └── trend_synthesis.py        # TrendSynthesizer (semantic clustering + citation overlap detection)
├── dashboard/
│   └── index.html                    # Local evaluation dashboard (vanilla JS)
└── docs/                             # Developer documentation
```

---

## Public API

```python
from article_evaluation_system import ArticleEvaluator

evaluator = ArticleEvaluator(model="gpt-4o", provider="mwai")

# Standard mode — evaluate one article against a customer issue
result = evaluator.evaluate(
    customer_issue="User cannot sign in to Teams on Mac",
    recommended_article="https://support.microsoft.com/...",
    product_info={"sap_product_name": "Microsoft Teams", "sap_path": "..."}
)

# mweaeval mode — evaluate AI response grounding + citation quality
result = evaluator.evaluate_with_citations(
    customer_issue="...",
    ai_response="The issue is caused by... [1] [2]",
    citation_urls=["https://...", "https://..."],
)

# Batch
results = evaluator.evaluate_batch(
    cases=[{"issue": "...", "article_url": "https://..."}]
)
```

`ArticleEvaluator` is a thin wrapper over `Orchestrator`. Always use `ArticleEvaluator` from outside the package.

---

## Agents

All agents extend `BaseAgent` (`agents/__init__.py`) and implement:
```python
def evaluate(self, *args, **kwargs) -> SomeResultDataclass:
    ...
```

| Agent | Class | Role |
|-------|-------|------|
| `IssueParserAgent` | issue_parser.py | Extracts product, type, severity, keywords, symptoms, error codes from raw issue text |
| `AreaClassificationAgent` | area_classification_agent.py | Classifies issue into product-specific area path (e.g. "Teams Meetings") |
| `DescriptionQualityAgent` | description_quality_agent.py | KT framework score: identity/location/timing/magnitude (0-100 each) |
| `RelevanceAgent` | relevance_agent.py | Is the article relevant to this issue? Score + product_match/version_match/is_outdated flags |
| `CompletenessAgent` | completeness_agent.py | Does the article fully cover the issue? Checks prereqs, steps, examples, troubleshooting |
| `ValidityAgent` | validity_agent.py | Is the article a valid solution? Checks root cause, currency, env compatibility |
| `SearchAgent` | search_agent.py | Finds alternative articles when score < 70 |
| `GapAnalysisAgent` | gap_agent.py | Identifies documentation gaps when score < 60 |
| `CitationQualityAgent` | citation_quality_agent.py | Checks grounding of AI response against cited articles (per-citation: support_score, verdict) |
| `ResponseQualityAgent` | response_quality_agent.py | Composite AI response quality (response_quality + groundedness + issue_resolution) |
| `Orchestrator` | orchestrator.py | Coordinates all agents, calls LLM synthesis, builds `EvaluationResult` |
| `TrendSynthesizer` | synthesis/trend_synthesis.py | Semantic clustering of batch results into 3-7 PM action groups + citation overlap detection |

### Adding a new agent

1. Create `agents/my_agent.py` — extend `BaseAgent`, implement `evaluate()`, return a dataclass.
2. Add the result dataclass to `models/evaluation.py`.
3. Add the system prompt to `utils/prompts.py` as `AgentPrompts.MY_AGENT`.
4. Import and wire in `agents/orchestrator.py` — instantiate in `__init__`, call in `evaluate()` or `evaluate_with_citations()`.
5. Expose output fields in `EvaluationResult.to_dict()`.

---

## Evaluation pipeline (standard mode)

```
CSV row
  └─ IssueParserAgent          → Issue
  └─ DescriptionQualityAgent   → KT score (flags low-confidence if < 40)
  └─ For each cited URL:
       └─ ArticleFetcher        → Article
       └─ RelevanceAgent        → RelevanceResult   (weight 0.40)
       └─ CompletenessAgent     → CompletenessResult (weight 0.30)
       └─ ValidityAgent         → ValidityResult    (weight 0.30)
       └─ ScoringUtils.calculate_overall_score()
  └─ If best_score < 70 → SearchAgent
  └─ If best_score < 60 → GapAnalysisAgent
  └─ Orchestrator._synthesize_recommendation()  → LLM synthesis
  └─ EvaluationResult
```

**mweaeval mode** replaces R/C/V with CitationQualityAgent + ResponseQualityAgent on the best citation.

---

## Scoring & verdicts

### Overall score
```
overall_score = relevance * 0.40 + completeness * 0.30 + validity * 0.30
```
Defined in `config/settings.py → SCORE_WEIGHTS` and computed by `ScoringUtils.calculate_overall_score()`.

### Verdict logic (`ScoringUtils.get_overall_verdict`)
| Condition | Verdict |
|-----------|---------|
| `overall_score >= 70` AND relevance in {excellent, good} | `adequate` |
| `overall_score >= 70` AND relevance NOT in {excellent, good} | `needs_supplementation` |
| `50 <= overall_score < 70` | `needs_supplementation` |
| `overall_score < 50` | `inadequate` |
| No article provided | `no_citation_provided` |

### Synthesis priority
| Score / verdict | Priority |
|-----------------|----------|
| score < 40 or inadequate/no_citation | `red` |
| score < 70 or needs_supplementation | `yellow` |
| adequate | `green` |

### Response quality composite (mweaeval mode)
```
ai_response_quality_score =
  response_quality * 0.40 +
  groundedness     * 0.30 +
  issue_resolution * 0.30
```
Weights in `config/settings.py → RESPONSE_QUALITY_WEIGHTS`.

---

## Data models

Key dataclasses live in `models/evaluation.py`:

- `RelevanceResult` — relevance_score, relevance_verdict, product_match, version_match, is_outdated, matched_aspects, unmatched_aspects
- `CompletenessResult` — completeness_score, completeness_verdict, has_prerequisites, has_step_by_step, has_examples, has_troubleshooting, missing_elements
- `ValidityResult` — validity_score, validity_verdict, addresses_root_cause, is_current_solution, environment_compatible, confidence_level, potential_issues
- `DescriptionQualityResult` — description_quality_score, description_quality_verdict, identity_score, location_score, timing_score, magnitude_score, missing_kt_elements
- `CitationQualityResult` — overall_grounding_score, overall_verdict, citations_good/partial/bad/total, uncited_percentage, per_citation_results
- `ResponseQualityResult` — ai_response_quality_score, ai_response_quality_verdict, response_quality_score, groundedness_score, issue_resolution_score, quality_weaknesses, improvement_suggestions
- `EvaluationResult` — top-level result; all agent outputs + synthesis fields (synthesis_priority, synthesis_priority_reason, synthesis_pm_actions, synthesis_root_cause_category)
- `TrendCluster` — cluster_name, area_path, priority, case_count, unified_pm_action, estimated_impact, root_cause_pattern, supporting_evidence
- `CitationOverlap` — url, overlap_type (`duplicate_issues` | `cross_coverage`), case_count, similarity_score, case_numbers, issue_snippets, flag_reason, recommendation

All dataclasses implement `.to_dict()`. Never return raw dataclass objects from agent `evaluate()` methods — always call `.to_dict()` before crossing the module boundary.

---

## Configuration

All thresholds and weights are in `article_evaluation_system/config/settings.py`.

| Constant | Purpose |
|----------|---------|
| `THRESHOLDS` | Verdict cutoffs for relevance, completeness, validity, overall |
| `SCORE_WEIGHTS` | Weights for R/C/V in overall score |
| `KT_DIMENSION_WEIGHTS` | KT dimension weights (identity 0.35, location 0.25, timing 0.20, magnitude 0.20) |
| `RESPONSE_QUALITY_WEIGHTS` | Weights for mweaeval composite score |

Environment variables:
- `MWAI_TOKEN` — MWAI bearer JWT (required)
- `MWAI_MODEL` — override default model (optional, default `gpt-4o`)
- `VERBOSE` — set to `true` for INFO logging

---

## MwaiClient

`utils/mwai_client.py` wraps the MWAI API (OpenAI-compatible). Use it via `BaseAgent._call_llm(system_prompt, user_message)`. Never call `MwaiClient` directly from outside `BaseAgent` subclasses.

`resolve_mwai_token(token=None, force_new=False)` — resolves token from argument → env → cached file → interactive prompt.

---

## CSV formats

### Standard input (`merged_output.csv` / `mwai_client.csv`)
Required: `Case Number`, `IssueDescription`
Optional: `Title_mwai`, `ContainsCitations`, `Urls`, `Transferred`, `SRStatus`, `Reopened`, `SapProductName`, `SapPath_mwai`/`SapPath`/`SapPath1`

### mweaeval input
Additional required: `AiResponse`, `Citations` (comma-separated URLs)

### Standard output
- `evaluation_results_<ts>.csv` — one row per case, all agent scores flattened (incl. `area_path`, `area_path_confidence`)
- `evaluation_summary_<ts>.csv` — key columns only (case_number, overall_score, verdict, recommendation)
- `trend_report_<ts>.csv` — one row per cluster (requires `--trend-report`)
- `citation_overlaps_<ts>.csv` — one row per overlapping article URL (auto-generated alongside trend report)

---

## CLI reference

```bash
# Quick test
python run_evaluation.py -n 5 -v

# All cases
python run_evaluation.py --all

# Specific case
python run_evaluation.py --case 2508270010003948

# mweaeval (AI response + citation grounding)
python run_evaluation.py -n 5 --mweaeval -i mweaeval_input.csv

# Batch with resume
python run_evaluation.py --batch-size 50 -i merged_output.csv
python run_evaluation.py --batch-size 50 --continue -i merged_output.csv

# Trend report + citation overlap analysis (requires >= 2 cases)
python run_evaluation.py --all --trend-report

# Token management
python run_evaluation.py --new-token     # force re-prompt
python run_evaluation.py --token eyJ0eX...  # explicit token
```

---

## Coding conventions

- Python 3.12+: use `str | None` union syntax, `list[str]` generics (no `Optional`, no `List`).
- All agents return a typed dataclass, never a raw dict.
- All system prompts live in `utils/prompts.py → AgentPrompts`. Never embed prompts inline in agent files.
- LLM responses are always JSON. Parse with `BaseAgent._parse_json_response()` — it handles markdown fences and partial JSON gracefully.
- Fallback logic: every agent must degrade gracefully when the LLM response is malformed. Return a zero-scored result, never raise.
- Label maps (e.g. `_RELEVANCE_LABEL_MAP` in `models/evaluation.py`) normalise qualitative LLM labels to numeric scores. Keep them exhaustive.
- Internal dict keys prefixed with `_` (e.g. `_relevance_obj`) are stripped before serialisation. Never surface `_`-prefixed keys in output.
- Logging: use `logger = logging.getLogger(__name__)` per module. INFO for milestones, WARNING for degraded paths, DEBUG for raw LLM I/O.

---

## Dashboard

`dashboard/index.html` is a standalone single-file vanilla JS dashboard. It reads CSV files via a file picker (drag-and-drop supported), parses them in-browser, and renders charts with cross-filtering. No build step. No backend. Open directly in a browser or serve with any static server.

Three upload cards:
1. **Evaluation Results CSV** (`evaluation_results_*.csv`) → SPM Actions + Evaluation Report tabs
2. **Trend Report CSV** (`trend_report_*.csv`) → Trend Report tab
3. **Citation Overlaps CSV** (`citation_overlaps_*.csv`) → Citation Overlaps tab (cross-coverage and duplicate flags with similarity bars)

---

## Common tasks

### Run a quick sanity check
```bash
python run_evaluation.py -n 3 -v
```

### Add a new scoring dimension to an existing agent
1. Add the field to the agent's result dataclass in `models/evaluation.py`.
2. Update the agent's `evaluate()` to populate the field.
3. Update `to_dict()` on the result dataclass.
4. If it affects the overall score, update `SCORE_WEIGHTS` in `config/settings.py` and `ScoringUtils`.

### Change verdict thresholds
Edit `THRESHOLDS` in `config/settings.py`. The values are consumed by `ScoringUtils` and `Orchestrator`.

### Add a column to the output CSV
Edit `write_results_csv()` in `article_evaluation_system/main.py`. The function flattens the nested evaluation dict into CSV columns.

### Debug LLM responses
```bash
python run_evaluation.py -n 1 --debug
```
`--debug` sets logging to DEBUG and prints raw prompts, responses, and API payloads.
