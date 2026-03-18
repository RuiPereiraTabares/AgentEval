# AgentsArticleReviewer

A multi-agent AI system that evaluates whether Microsoft support articles adequately address customer issues. Built for automated quality assurance of support case article citations.

## Architecture at a Glance

```
                         Customer Issue (CSV row)
                                  |
                          +--------------+
                          | Orchestrator |
                          +--------------+
                                  |
              +-------------------+-------------------+
              |                                       |
     +------------------+                   +---------------------+
     | IssueParserAgent |                   | DescriptionQuality  |
     | (parse issue)    |                   | Agent (KT framework)|
     +------------------+                   +---------------------+
              |                                       |
              v                                       v
        +-----------+     +-----------------+   +-----------+
        | Relevance |     | Completeness    |   | Validity  |
        | Agent     |     | Agent           |   | Agent     |
        +-----------+     +-----------------+   +-----------+
              \                 |                     /
               +----------------+--------------------+
               |          Overall Score               |
               |   (R*0.4 + C*0.3 + V*0.3)          |
               +--------------------------------------+
                      |                    |
              (score < 70)          (score < 60)
                      |                    |
              +-------------+     +-----------------+
              | SearchAgent |     | GapAnalysis     |
              | (find alt.) |     | Agent           |
              +-------------+     +-----------------+
                      \                /
                       +----+----+----+
                            |
                  +---------------------+
                  | TransferReasonAgent |
                  | (classify WHY)      |
                  +---------------------+
                            |
                     EvaluationResult
```

## Quick Start

### Prerequisites

- Python 3.12+
- An MWAI bearer token (Microsoft internal — JWT)
- Input CSV file with support case data

### Install

```bash
pip install -r requirements.txt
```

### Configure

Create a `.env` file in the project root:

```env
MWAI_TOKEN=eyJ0eX...
```

### First Run

```bash
# Evaluate first 5 cases (test mode)
python run_evaluation.py -n 5

# Evaluate all cases
python run_evaluation.py --all

# Evaluate a specific case with verbose output
python run_evaluation.py --case 2508270010003948 -v
```

### Input / Output

**Input:** CSV file with columns `Case Number`, `Title_mwai`, `IssueDescription`, `Urls`, `ContainsCitations`, `Transferred`, `SRStatus`, `Reopened`, plus SAP product metadata.

**Output:** JSON or CSV with per-case evaluation results containing overall score (0-100), verdict, per-agent breakdowns, description quality analysis, transfer reason classification, and recommendations.

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Verdict** | Final article assessment: `adequate`, `needs_supplementation`, `inadequate`, or `no_citation_provided` |
| **Overall Score** | Weighted composite: Relevance (40%) + Completeness (30%) + Validity (30%) |
| **KT Framework** | Kepner-Tregoe analysis of issue description quality across 4 dimensions (WHAT, WHERE, WHEN, EXTENT) |
| **Transfer Analysis** | Root-cause classification for why a support case was transferred (8 categories) |
| **Action Required** | Recommended next step: `none`, `add_context`, `find_better_article`, or `create_content` |
| **Reliability Warning** | Flag set when description quality score < 40, indicating low confidence in the evaluation |

## Documentation Map

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | System design, agent interaction patterns, module structure |
| [Agents](agents.md) | Complete reference for all 9 agents (role, inputs, outputs, fallbacks) |
| [Pipeline](pipeline.md) | Step-by-step evaluation workflow with flowchart |
| [Data Models](data-models.md) | All dataclasses, type aliases, and label normalization maps |
| [Scoring](scoring.md) | Score formula, verdict logic, threshold tables |
| [Configuration](configuration.md) | Environment variables, Settings dataclass, threshold dictionaries |
| [API Reference](api-reference.md) | `ArticleEvaluator` API, CLI usage, CSV/JSON formats |
| [KT Framework](kt-framework.md) | Kepner-Tregoe description quality analysis |
| [Transfer Analysis](transfer-analysis.md) | Transfer reason classification decision tree |
| [Providers](providers.md) | MWAI provider setup |
| [Contributing](contributing.md) | Adding agents, models, and modifying the system |
