# AgentsArticleReviewer

A multi-agent AI system that evaluates whether Microsoft support articles adequately address customer issues. Built for automated quality assurance of support case article citations.

## How It Works

The system reads support cases from a CSV file, parses each customer issue, fetches the cited article, and runs 8 specialized AI agents to evaluate relevance, completeness, validity, description quality (Kepner-Tregoe framework), and transfer reason classification. Each case receives an overall score (0-100), a verdict, and an actionable recommendation.

## Prerequisites

- **Python 3.12** or later
- **pip** (comes with Python)
- An API key for at least one LLM provider:
  - [OpenAI](https://platform.openai.com/api-keys) (API key)
  - [Anthropic](https://console.anthropic.com/settings/keys) (API key)
  - MWAI (Microsoft internal — JWT bearer token)
- An input CSV file with support case data (see [Input Format](#input-csv-format))

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd AgentsArticleReviewer
```

### 2. Create a Virtual Environment

```bash
# Create
python -m venv .venv

# Activate (pick your shell):
# Windows (Command Prompt)
.venv\Scripts\activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Windows (Git Bash / MSYS2)
source .venv/Scripts/activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

If you also need Semantic Kernel support (optional):

```bash
pip install -r requirements-sk.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
# ---- Pick ONE provider ----

# Option A: OpenAI
OPENAI_API_KEY=sk-proj-...

# Option B: Anthropic / Claude
# ANTHROPIC_API_KEY=sk-ant-api03-...

# Option C: MWAI (Microsoft internal)
# MWAI_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGciOi...
```

Alternatively, export the variable directly in your shell:

```bash
# bash / zsh
export OPENAI_API_KEY="sk-proj-..."

# PowerShell
$env:OPENAI_API_KEY = "sk-proj-..."

# Command Prompt
set OPENAI_API_KEY=sk-proj-...
```

### 5. Verify Installation

```bash
python -c "from article_evaluation_system import ArticleEvaluator; print('OK')"
```

## Quick Start

```bash
# Evaluate first 5 cases (quick test)
python run_evaluation.py -n 5

# Evaluate all cases
python run_evaluation.py --all

# Evaluate a specific case
python run_evaluation.py --case 2508270010003948

# Verbose output (shows per-agent score breakdowns)
python run_evaluation.py -n 5 -v

# Use Anthropic instead of OpenAI
python run_evaluation.py --provider anthropic --model claude-sonnet-4-20250514 -n 5

# Use MWAI (will prompt for token if not cached)
python run_evaluation.py --provider mwai -n 5

# Output as CSV instead of JSON
python run_evaluation.py -n 5 --format csv
```

### Output

Each run produces two files:

| File | Description |
|------|-------------|
| `evaluation_results_{timestamp}.json` | Full evaluation results (or `.csv` with `--format csv`) |
| `evaluation_summary_{timestamp}.csv` | Summary with key scores and reasons only |

## Input CSV Format

The input CSV needs at minimum these columns:

| Column | Required | Description |
|--------|----------|-------------|
| `Case Number` | Yes | Unique case identifier |
| `IssueDescription` | Yes | Customer issue text |
| `Title_mwai` | No | Case title (prepended to description) |
| `ContainsCitations` | No | `TRUE` / `FALSE` — whether URLs were cited |
| `Urls` | No | Comma-separated article URLs |
| `Transferred` | No | `TRUE` / `FALSE` — whether case was transferred |
| `SRStatus` | No | Service request status |
| `Reopened` | No | `TRUE` / `FALSE` — whether case was reopened |
| `SapProductName` | No | Product name from SAP taxonomy |

See [docs/api-reference.md](docs/api-reference.md#csv-input-format) for the full column list.

## Project Structure

```
AgentsArticleReviewer/
  run_evaluation.py              # Main CLI runner (multi-provider)
  run_evaluation_sk.py           # Semantic Kernel CLI runner
  requirements.txt               # Python dependencies
  requirements-sk.txt            # Optional SK dependencies
  .env                           # API keys (create this yourself)
  article_evaluation_system/     # Main package
    __init__.py                  #   ArticleEvaluator entry point
    main.py                      #   CSV I/O and alternative CLI
    agents/                      #   All 9 agents
    models/                      #   Data models (Issue, Article, results)
    config/                      #   Settings, thresholds, weights
    utils/                       #   Article fetcher, scoring, prompts, MWAI client
    sk/                          #   Optional Semantic Kernel integration
  docs/                          #   Developer documentation
```

## Documentation

| Document | What's Inside |
|----------|---------------|
| [docs/index.md](docs/index.md) | Overview, architecture diagram, quick start, glossary |
| [docs/architecture.md](docs/architecture.md) | System design, module tree, error handling |
| [docs/agents.md](docs/agents.md) | All 9 agents — role, inputs, outputs, fallbacks |
| [docs/pipeline.md](docs/pipeline.md) | Step-by-step evaluation workflow with flowchart |
| [docs/data-models.md](docs/data-models.md) | All dataclasses, type aliases, label maps |
| [docs/scoring.md](docs/scoring.md) | Score formula, verdict logic, threshold tables |
| [docs/configuration.md](docs/configuration.md) | Env vars, Settings, CLI arguments |
| [docs/api-reference.md](docs/api-reference.md) | Programmatic API, CLI usage, CSV/JSON formats |
| [docs/kt-framework.md](docs/kt-framework.md) | Kepner-Tregoe description quality analysis |
| [docs/transfer-analysis.md](docs/transfer-analysis.md) | Transfer reason classification decision tree |
| [docs/providers.md](docs/providers.md) | LLM provider setup (OpenAI, Anthropic, MWAI, SK) |
| [docs/contributing.md](docs/contributing.md) | Adding agents, providers, models; testing patterns |

## Troubleshooting

### `ModuleNotFoundError: No module named 'openai'`

You haven't installed dependencies. Run:

```bash
pip install -r requirements.txt
```

### `ERROR: No API key provided`

Set the API key for your chosen provider. See [Configure Environment Variables](#4-configure-environment-variables).

### `UnicodeDecodeError` when reading CSV

The system auto-detects UTF-8 (with BOM) and CP1252 encoding. If your CSV uses a different encoding, convert it to UTF-8 first:

```bash
# PowerShell
Get-Content input.csv -Encoding Default | Set-Content -Encoding UTF8 input_utf8.csv
```

### `Failed to fetch article: ...`

The article URL may be behind authentication or no longer available. The system handles fetch failures gracefully — that article will receive a score of 0 and the other agents will still run.

### MWAI token expired

Re-run with `--new-token` to get a fresh token:

```bash
python run_evaluation.py --provider mwai --new-token
```
