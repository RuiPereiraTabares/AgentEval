# Agentic Insight Engine

A multi-agent AI system that evaluates whether Microsoft support articles adequately address customer support issues. Produces structured scores, gap analysis, trend clusters, and PM action recommendations.

## Overview

Each support case is processed through a pipeline of specialized agents:

1. **IssueParserAgent** — parses raw issue text into a structured `Issue` object
2. **AreaClassificationAgent** — classifies the issue into a product area (e.g., "Teams Meetings")
3. **DescriptionQualityAgent** — scores issue quality across three dimensions (product clarity, symptom specificity, operational context)
4. **RelevanceAgent / CompletenessAgent / ValidityAgent** — evaluate the linked support article
5. **SearchAgent / GapAnalysisAgent** — triggered when article score is low
6. **CitationQualityAgent / ResponseQualityAgent** — used in `--mweaeval` mode for AI response analysis
7. **TransferReasonAgent** — classifies why the case was transferred (8 categories)
8. **TrendSynthesizer** — optional batch clustering with PM action recommendations and citation overlap detection

## Requirements

- Python 3.12+
- MWAI API access (Microsoft internal — gpt-4o)

```bash
pip install -r requirements.txt
```

Dependencies: `requests`, `beautifulsoup4`, `python-dotenv`, `msal`, `json-repair`

## Setup

Copy `.env.example` to `.env` and add your MWAI credentials, or use `--token` / `--new-token` at runtime for interactive MSAL authentication.

## Usage

```bash
# Evaluate first 50 cases (default)
python run_evaluation.py

# Evaluate all cases
python run_evaluation.py --all

# Limit to N cases from a specific input file
python run_evaluation.py -n 20 -i my_cases.csv

# Evaluate a single case
python run_evaluation.py --case 2508270010003948

# Parallel mode — 3 concurrent cases (2–4× throughput)
python run_evaluation.py --workers 3 -n 100

# Batch mode with resume support
python run_evaluation.py --batch-size 50 -i input.csv
python run_evaluation.py --batch-size 50 --continue -i input.csv

# Citation quality evaluation mode (requires AiResponse + Citations columns)
python run_evaluation.py --mweaeval -i mweaeval_format.csv

# Generate trend report
python run_evaluation.py --all --trend-report

# Regenerate trends from existing results (no re-evaluation)
python run_evaluation.py --trends-only --from-results evaluation_results_*.csv

# Verbose / debug output (sequential mode only)
python run_evaluation.py -v
python run_evaluation.py --debug

# Disable caches for a guaranteed-fresh run
python run_evaluation.py --no-llm-cache --no-article-cache
```

### Key Arguments

| Argument | Description |
|---|---|
| `-i FILE` | Input CSV (default: `merged_output.csv`) |
| `-n N` | Process at most N cases (default: 50) |
| `--all` | Process all cases |
| `--case ID` | Process a single case number |
| `--skip N` | Skip first N cases |
| `--workers N` | Parallel worker count (default: 1). Start at 3–4; share one rate-limiter token bucket across all threads |
| `--mweaeval` | Citation quality + AI response evaluation mode |
| `--trend-report` | Generate trend cluster report after evaluation |
| `--trends-only` | Skip evaluation; regenerate trends from `--from-results` CSVs |
| `--batch-size N` | Enable batch mode (use `--continue` to resume) |
| `--model MODEL` | LLM model override (default: `gpt-4o`) |
| `--token TOKEN` | MWAI bearer token |
| `--new-token` | Force re-authentication |
| `--no-llm-cache` | Disable LLM response dedup cache for this run |
| `--no-article-cache` | Disable persistent article cache for this run |
| `-v` / `--debug` | Verbose / debug logging (sequential mode only) |

## Output Files

| File | Contents |
|---|---|
| `evaluation_results_<ts>.csv` | Per-case detailed evaluation (all agent outputs) |
| `evaluation_summary_<ts>.csv` | Summary with key metrics only |
| `trend_report_<ts>.csv` | Clustered trend analysis with PM actions |
| `citation_overlaps_<ts>.csv` | Duplicate and cross-coverage citation flags |

## Project Structure

```
AgentEval/
├── run_evaluation.py                    # CLI entry point
├── article_evaluation_system/
│   ├── __init__.py                      # ArticleEvaluator public API
│   ├── main.py                          # CSV I/O utilities
│   ├── agents/                          # 11 specialized agents + Orchestrator
│   ├── models/                          # Issue, EvaluationResult, TrendCluster, CitationOverlap
│   ├── config/
│   │   ├── settings.py                  # Thresholds and weights
│   │   └── area_definitions.py          # Product area taxonomies
│   ├── utils/                           # MWAI client, article fetcher, LLM cache, prompts, scoring
│   └── synthesis/
│       └── trend_synthesis.py           # Semantic clustering + citation overlap detection
├── dashboard/
│   └── index.html                       # Web UI for result visualization
├── docs/                                # Full documentation (13 markdown files + HTML)
└── requirements.txt
```

## Scoring

Article scores are computed as a weighted average:

```
score = Relevance × 0.4 + Completeness × 0.3 + Validity × 0.3
```

| Score | Verdict |
|---|---|
| ≥ 80 | Adequate |
| 60–79 | Needs Improvement |
| < 60 | Inadequate → triggers SearchAgent + GapAnalysisAgent |

## Area Classification

Issues are automatically classified into product-specific areas using taxonomies defined in `config/area_definitions.py`. Teams has 17 areas defined. To add a new product, add an entry to `PRODUCT_AREA_DEFINITIONS`.

## Documentation

Full documentation lives in [`docs/`](docs/):

- [`docs/index.md`](docs/index.md) — Overview and quick start
- [`docs/architecture.md`](docs/architecture.md) — System design and agent interaction
- [`docs/agents.md`](docs/agents.md) — Agent reference
- [`docs/pipeline.md`](docs/pipeline.md) — Step-by-step workflow
- [`docs/scoring.md`](docs/scoring.md) — Score formulas and verdict logic
- [`docs/configuration.md`](docs/configuration.md) — Settings reference
- [`docs/api-reference.md`](docs/api-reference.md) — ArticleEvaluator API and CSV formats
