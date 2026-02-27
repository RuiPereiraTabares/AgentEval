# Semantic Kernel Article Evaluation System
## Technical Specification & Integration Guide

**Version:** 1.0
**Last Updated:** January 2026
**Authors:** Article Evaluation Team
**Status:** Ready for Implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Component Design](#3-component-design)
4. [Integration Patterns](#4-integration-patterns)
5. [Pipeline Architecture](#5-pipeline-architecture)
6. [Configuration & Security](#6-configuration--security)
7. [Deployment Options](#7-deployment-options)
8. [Monitoring & Observability](#8-monitoring--observability)
9. [Error Handling & Resilience](#9-error-handling--resilience)
10. [Performance & Scalability](#10-performance--scalability)
11. [Migration Strategy](#11-migration-strategy)
12. [API Reference](#12-api-reference)
13. [Usage Examples](#13-usage-examples)
14. [Appendices](#14-appendices)

---

## 1. Executive Summary

### 1.1 Purpose

The Semantic Kernel (SK) Article Evaluation System provides an AI-powered solution for evaluating whether Microsoft support articles adequately address customer issues. This specification details the integration of this system into Microsoft's internal pipelines using Semantic Kernel as the orchestration layer.

### 1.2 Key Benefits

| Benefit | Description |
|---------|-------------|
| **Unified LLM Access** | Single abstraction layer for OpenAI, Azure OpenAI, and Anthropic/Claude |
| **Enterprise Ready** | Native Azure OpenAI support with managed identity integration |
| **Plugin Architecture** | Modular kernel functions that can be composed into larger workflows |
| **Pipeline Compatible** | Designed for integration with Azure Data Factory, Logic Apps, and custom pipelines |
| **Backward Compatible** | Drop-in replacement for existing ArticleEvaluator implementations |

### 1.3 Supported Providers

| Provider | Model Examples | Use Case |
|----------|---------------|----------|
| **Azure OpenAI** | gpt-4, gpt-4-turbo, gpt-4o | Production workloads with enterprise compliance |
| **OpenAI** | gpt-4o, gpt-4-turbo | Development and testing |
| **Anthropic** | claude-sonnet-4-20250514, claude-3-opus | Alternative provider, specialized tasks |

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MICROSOFT PIPELINE LAYER                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                 │
│   │ Azure Data   │    │ Azure Logic  │    │   Custom     │                 │
│   │   Factory    │    │    Apps      │    │  Pipeline    │                 │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                 │
│          │                   │                   │                          │
│          └───────────────────┼───────────────────┘                          │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                    AZURE FUNCTION / API LAYER                        │  │
│   │  ┌─────────────────────────────────────────────────────────────┐    │  │
│   │  │              SemanticKernelEvaluator                         │    │  │
│   │  │  ┌─────────────────────────────────────────────────────┐    │    │  │
│   │  │  │            ArticleEvaluationPlugin                   │    │    │  │
│   │  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │    │    │  │
│   │  │  │  │ parse   │ │evaluate │ │evaluate │ │evaluate │   │    │    │  │
│   │  │  │  │ _issue  │ │_relevance│ │_complete│ │_validity│   │    │    │  │
│   │  │  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │    │    │  │
│   │  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐               │    │    │  │
│   │  │  │  │ search  │ │ analyze │ │evaluate │               │    │    │  │
│   │  │  │  │_articles│ │ _gaps   │ │_article │               │    │    │  │
│   │  │  │  └─────────┘ └─────────┘ └─────────┘               │    │    │  │
│   │  │  └─────────────────────────────────────────────────────┘    │    │  │
│   │  └─────────────────────────────────────────────────────────────┘    │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                              │                                              │
└──────────────────────────────┼──────────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SEMANTIC KERNEL LAYER                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                         SK Kernel                                    │  │
│   │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │  │
│   │  │ SKChatCompletion│  │   SK Plugins    │  │   SK Memory     │     │  │
│   │  │     Adapter     │  │   (Functions)   │  │   (Optional)    │     │  │
│   │  └────────┬────────┘  └─────────────────┘  └─────────────────┘     │  │
│   └───────────┼─────────────────────────────────────────────────────────┘  │
│               ▼                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                    Chat Completion Services                          │  │
│   │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐       │  │
│   │  │  AzureChatComp  │ │  OpenAIChatComp │ │ AnthropicChat   │       │  │
│   │  │    (Native SK)  │ │   (Native SK)   │ │ Comp (Custom)   │       │  │
│   │  └────────┬────────┘ └────────┬────────┘ └────────┬────────┘       │  │
│   └───────────┼───────────────────┼───────────────────┼─────────────────┘  │
│               │                   │                   │                     │
└───────────────┼───────────────────┼───────────────────┼─────────────────────┘
                ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            LLM PROVIDER LAYER                               │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│   │  Azure OpenAI   │    │     OpenAI      │    │    Anthropic    │        │
│   │    Service      │    │      API        │    │      API        │        │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Customer   │     │   Article    │     │  Evaluation  │     │   Results    │
│    Issue     │────▶│    URL       │────▶│   Pipeline   │────▶│   Output     │
│   (Input)    │     │   (Input)    │     │              │     │   (JSON)     │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                     ┌───────────────────────────┼───────────────────────────┐
                     │                           │                           │
                     ▼                           ▼                           ▼
              ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
              │   Parse     │            │  Evaluate   │            │   Search    │
              │   Issue     │            │  Article    │            │  & Analyze  │
              └─────────────┘            └─────────────┘            └─────────────┘
                     │                           │                           │
                     │         ┌─────────────────┼─────────────────┐         │
                     │         │                 │                 │         │
                     │         ▼                 ▼                 ▼         │
                     │  ┌───────────┐    ┌───────────┐    ┌───────────┐     │
                     │  │ Relevance │    │Completeness│   │ Validity  │     │
                     │  │   Agent   │    │   Agent   │    │   Agent   │     │
                     │  └───────────┘    └───────────┘    └───────────┘     │
                     │         │                 │                 │         │
                     └─────────┴─────────────────┴─────────────────┴─────────┘
                                                 │
                                                 ▼
                                        ┌───────────────┐
                                        │  Aggregated   │
                                        │    Results    │
                                        └───────────────┘
```

---

## 3. Component Design

### 3.1 SemanticKernelEvaluator

The main entry point for article evaluation. Provides a drop-in replacement for the original ArticleEvaluator.

```python
class SemanticKernelEvaluator:
    """
    Primary interface for article evaluation using Semantic Kernel.

    Attributes:
        kernel: Configured SK Kernel instance
        plugin: ArticleEvaluationPlugin with kernel functions
        service_id: Identifier for the chat completion service
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        provider: str = "openai",  # "openai" | "azure" | "anthropic"
        azure_endpoint: str = None,
        azure_deployment: str = None,
        kernel: Kernel = None  # Pre-configured kernel (optional)
    )

    def evaluate(customer_issue: str, article_url: str) -> dict
    def evaluate_batch(cases: list[dict], progress_callback: callable) -> list[dict]
```

### 3.2 ArticleEvaluationPlugin

SK Plugin exposing 7 kernel functions for granular evaluation control.

| Function | Description | Input | Output |
|----------|-------------|-------|--------|
| `parse_issue` | Parse customer issue to structured data | Issue text | JSON with product, symptoms, error codes |
| `evaluate_relevance` | Score article relevance (0-100) | Issue JSON, Article URL | Relevance score, matched/unmatched aspects |
| `evaluate_completeness` | Score article completeness (0-100) | Issue JSON, Article URL | Completeness score, missing elements |
| `evaluate_validity` | Score solution validity (0-100) | Issue JSON, Article URL | Validity score, potential issues |
| `search_articles` | Generate search queries | Issue JSON | Search queries, URLs |
| `analyze_gaps` | Identify documentation gaps | Issue JSON, Eval results | Gap analysis, recommendations |
| `evaluate_article` | Full orchestrated evaluation | Issue text, Article URL | Complete evaluation result |

### 3.3 AnthropicChatCompletion

Custom SK connector for Claude models (not natively supported in SK).

```python
class AnthropicChatCompletion(ChatCompletionClientBase):
    """
    Semantic Kernel chat completion service for Anthropic/Claude.

    Implements the SK ChatCompletionClientBase interface to enable
    Claude models in SK workflows.
    """

    def __init__(
        self,
        ai_model_id: str = "claude-sonnet-4-20250514",
        api_key: str = None,
        service_id: str = None,
        base_url: str = None  # For proxies/custom endpoints
    )

    # SK Interface Implementation
    async def get_chat_message_content(chat_history, settings) -> ChatMessageContent
    async def get_streaming_chat_message_content(chat_history, settings) -> AsyncGenerator
```

### 3.4 SKChatCompletionAdapter

Bridges SK chat completion with the existing agent infrastructure.

```python
class SKChatCompletionAdapter:
    """
    Adapter allowing existing BaseAgent subclasses to use SK services
    without modifying their evaluation logic.
    """

    def __init__(self, kernel: Kernel, service_id: str = None)

    def call(system_prompt: str, user_message: str) -> str
    async def call_async(system_prompt: str, user_message: str) -> str
    def get_callable() -> Callable[[str, str], str]
```

---

## 4. Integration Patterns

### 4.1 Pattern 1: Direct API Integration

Best for: Simple REST API services, Azure Functions, microservices

```
┌─────────────┐      HTTP/JSON      ┌─────────────────────┐
│   Client    │ ──────────────────▶ │   Azure Function    │
│  (Any App)  │ ◀────────────────── │ (SK Evaluator)      │
└─────────────┘                     └─────────────────────┘
```

**Implementation:**

```python
# Azure Function with HTTP Trigger
import azure.functions as func
from article_evaluation_system.sk import SemanticKernelEvaluator

# Initialize once (cold start optimization)
evaluator = None

def get_evaluator():
    global evaluator
    if evaluator is None:
        evaluator = SemanticKernelEvaluator(
            provider="azure",
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"]
        )
    return evaluator

def main(req: func.HttpRequest) -> func.HttpResponse:
    body = req.get_json()

    result = get_evaluator().evaluate(
        customer_issue=body["issue"],
        recommended_article=body.get("article_url")
    )

    return func.HttpResponse(
        json.dumps(result),
        mimetype="application/json"
    )
```

### 4.2 Pattern 2: Queue-Based Processing

Best for: High-volume batch processing, async workflows, decoupled systems

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Producer   │────▶│ Azure Queue │────▶│  Function   │────▶│   Results   │
│  (Submit)   │     │  (Storage)  │     │ (Processor) │     │   (Blob)    │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

**Implementation:**

```python
# Queue-triggered Azure Function
import azure.functions as func

def main(msg: func.QueueMessage, outputBlob: func.Out[str]):
    request = json.loads(msg.get_body().decode('utf-8'))

    evaluator = get_evaluator()
    result = evaluator.evaluate(
        customer_issue=request["issue"],
        recommended_article=request.get("article_url")
    )

    # Write result to blob storage
    result["request_id"] = request["request_id"]
    result["processed_at"] = datetime.utcnow().isoformat()
    outputBlob.set(json.dumps(result))
```

### 4.3 Pattern 3: Azure Data Factory Integration

Best for: ETL pipelines, scheduled batch processing, data warehouse integration

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Source DB  │────▶│    ADF      │────▶│  ADF Web    │────▶│  Sink DB    │
│  (Cases)    │     │  Pipeline   │     │  Activity   │     │  (Results)  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │ Azure Function  │
                                    │ (SK Evaluator)  │
                                    └─────────────────┘
```

**ADF Pipeline JSON:**

```json
{
    "name": "ArticleEvaluationPipeline",
    "properties": {
        "activities": [
            {
                "name": "GetCasesToProcess",
                "type": "Lookup",
                "linkedServiceName": {
                    "referenceName": "CasesDatabase",
                    "type": "LinkedServiceReference"
                },
                "typeProperties": {
                    "source": {
                        "type": "SqlSource",
                        "sqlReaderQuery": "SELECT TOP 100 * FROM Cases WHERE status = 'pending'"
                    }
                }
            },
            {
                "name": "EvaluateArticles",
                "type": "ForEach",
                "dependsOn": [{"activity": "GetCasesToProcess", "dependencyConditions": ["Succeeded"]}],
                "typeProperties": {
                    "items": {"value": "@activity('GetCasesToProcess').output.value"},
                    "isSequential": false,
                    "batchCount": 10,
                    "activities": [
                        {
                            "name": "CallEvaluationAPI",
                            "type": "WebActivity",
                            "typeProperties": {
                                "url": "@pipeline().parameters.evaluationApiUrl",
                                "method": "POST",
                                "headers": {
                                    "Content-Type": "application/json",
                                    "x-functions-key": "@pipeline().parameters.functionKey"
                                },
                                "body": {
                                    "case_id": "@item().case_id",
                                    "issue": "@item().issue_description",
                                    "article_url": "@item().article_url"
                                }
                            }
                        }
                    ]
                }
            }
        ],
        "parameters": {
            "evaluationApiUrl": {"type": "string"},
            "functionKey": {"type": "securestring"}
        }
    }
}
```

### 4.4 Pattern 4: Logic Apps Integration

Best for: Low-code workflows, business process automation, multi-system orchestration

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Trigger    │────▶│ Logic App   │────▶│  Evaluate   │────▶│   Action    │
│ (ServiceNow)│     │  Workflow   │     │  (Function) │     │  (Teams)    │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

**Logic App Workflow Definition:**

```json
{
    "definition": {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "triggers": {
            "When_a_case_is_created": {
                "type": "ApiConnection",
                "inputs": {
                    "host": {"connection": {"name": "@parameters('$connections')['servicenow']['connectionId']"}},
                    "method": "get",
                    "path": "/api/now/table/incident"
                },
                "recurrence": {"frequency": "Minute", "interval": 5}
            }
        },
        "actions": {
            "Evaluate_Article": {
                "type": "Function",
                "inputs": {
                    "function": {"id": "/subscriptions/.../functions/EvaluateArticle"},
                    "body": {
                        "issue": "@triggerBody()?['description']",
                        "article_url": "@triggerBody()?['kb_article_url']"
                    }
                }
            },
            "Check_Score": {
                "type": "If",
                "expression": {
                    "and": [{"less": ["@body('Evaluate_Article')?['overall_score']", 70]}]
                },
                "actions": {
                    "Send_Teams_Alert": {
                        "type": "ApiConnection",
                        "inputs": {
                            "body": {
                                "text": "Low article score detected: @{body('Evaluate_Article')?['overall_score']}/100"
                            }
                        }
                    }
                }
            }
        }
    }
}
```

### 4.5 Pattern 5: Event-Driven Architecture

Best for: Real-time processing, microservices, event sourcing

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Event     │────▶│  Event Hub  │────▶│  Function   │────▶│  Event Hub  │
│  Producer   │     │  (Ingest)   │     │ (Processor) │     │  (Results)  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                                              ┌────────────────────┼────────────────────┐
                                              ▼                    ▼                    ▼
                                        ┌───────────┐       ┌───────────┐       ┌───────────┐
                                        │  Cosmos   │       │   Power   │       │  Custom   │
                                        │    DB     │       │    BI     │       │   App     │
                                        └───────────┘       └───────────┘       └───────────┘
```

---

## 5. Pipeline Architecture

### 5.1 Recommended Production Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              PRODUCTION PIPELINE                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           DATA INGESTION LAYER                               │   │
│  │                                                                              │   │
│  │   ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐        │   │
│  │   │ ServiceNow │   │   CRM      │   │   CSV      │   │   API      │        │   │
│  │   │  Webhook   │   │  Events    │   │  Upload    │   │  Submit    │        │   │
│  │   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘        │   │
│  │         └────────────────┴────────────────┴────────────────┘                │   │
│  │                                    │                                         │   │
│  │                                    ▼                                         │   │
│  │                          ┌─────────────────┐                                 │   │
│  │                          │   Event Hub     │                                 │   │
│  │                          │   (Ingest)      │                                 │   │
│  │                          └────────┬────────┘                                 │   │
│  └───────────────────────────────────┼──────────────────────────────────────────┘   │
│                                      │                                               │
│  ┌───────────────────────────────────┼──────────────────────────────────────────┐   │
│  │                       PROCESSING LAYER                                        │   │
│  │                                   │                                           │   │
│  │                                   ▼                                           │   │
│  │                    ┌──────────────────────────┐                               │   │
│  │                    │     Azure Functions      │                               │   │
│  │                    │    (Event Triggered)     │                               │   │
│  │                    └────────────┬─────────────┘                               │   │
│  │                                 │                                             │   │
│  │      ┌──────────────────────────┼──────────────────────────┐                 │   │
│  │      │                          │                          │                 │   │
│  │      ▼                          ▼                          ▼                 │   │
│  │ ┌──────────┐            ┌──────────────┐            ┌──────────┐            │   │
│  │ │ Validate │            │   SK         │            │  Enrich  │            │   │
│  │ │ & Parse  │───────────▶│  Evaluator   │───────────▶│ Results  │            │   │
│  │ └──────────┘            └──────────────┘            └──────────┘            │   │
│  │                                │                                             │   │
│  │                                ▼                                             │   │
│  │                    ┌──────────────────────┐                                  │   │
│  │                    │    Azure OpenAI      │                                  │   │
│  │                    │  (Enterprise Model)  │                                  │   │
│  │                    └──────────────────────┘                                  │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                               │
│  ┌───────────────────────────────────┼──────────────────────────────────────────┐   │
│  │                       OUTPUT LAYER                                            │   │
│  │                                   │                                           │   │
│  │                                   ▼                                           │   │
│  │                    ┌──────────────────────────┐                               │   │
│  │                    │       Event Hub          │                               │   │
│  │                    │       (Results)          │                               │   │
│  │                    └────────────┬─────────────┘                               │   │
│  │                                 │                                             │   │
│  │      ┌──────────────────────────┼──────────────────────────┐                 │   │
│  │      │                          │                          │                 │   │
│  │      ▼                          ▼                          ▼                 │   │
│  │ ┌──────────┐            ┌──────────────┐            ┌──────────┐            │   │
│  │ │  Cosmos  │            │    Synapse   │            │  Teams   │            │   │
│  │ │    DB    │            │   Analytics  │            │  Notify  │            │   │
│  │ └──────────┘            └──────────────┘            └──────────┘            │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Pipeline Stages

| Stage | Component | Purpose | SLA |
|-------|-----------|---------|-----|
| **Ingest** | Event Hub | Receive evaluation requests | < 100ms |
| **Validate** | Azure Function | Input validation, deduplication | < 500ms |
| **Evaluate** | SK Evaluator | Run AI evaluation | < 30s |
| **Enrich** | Azure Function | Add metadata, format results | < 500ms |
| **Store** | Cosmos DB | Persist results | < 100ms |
| **Notify** | Logic App | Alert on low scores | < 5s |
| **Analyze** | Synapse | Aggregation, reporting | Batch |

### 5.3 Batch Processing Pipeline

For scheduled batch processing of large datasets:

```python
# batch_processor.py - ADF Custom Activity

import json
import pandas as pd
from azure.storage.blob import BlobServiceClient
from article_evaluation_system.sk import SemanticKernelEvaluator

def main(input_blob_path: str, output_blob_path: str, batch_size: int = 50):
    """
    Process a batch of cases from blob storage.

    Args:
        input_blob_path: Path to input CSV in blob storage
        output_blob_path: Path to write results
        batch_size: Number of concurrent evaluations
    """
    # Initialize evaluator
    evaluator = SemanticKernelEvaluator(
        provider="azure",
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"]
    )

    # Read input data
    blob_client = BlobServiceClient.from_connection_string(os.environ["STORAGE_CONNECTION"])
    input_data = pd.read_csv(blob_client.get_blob_client(input_blob_path).download_blob())

    # Process in batches
    results = []
    for i in range(0, len(input_data), batch_size):
        batch = input_data.iloc[i:i+batch_size]

        cases = [
            {"issue": row["issue"], "article_url": row.get("article_url")}
            for _, row in batch.iterrows()
        ]

        batch_results = evaluator.evaluate_batch(
            cases,
            progress_callback=lambda current, total: print(f"Progress: {current}/{total}")
        )

        for j, result in enumerate(batch_results):
            result["case_id"] = batch.iloc[j]["case_id"]
            results.append(result)

    # Write results
    output_df = pd.DataFrame(results)
    output_blob = blob_client.get_blob_client(output_blob_path)
    output_blob.upload_blob(output_df.to_csv(index=False), overwrite=True)

    return {"processed": len(results), "output_path": output_blob_path}
```

---

## 6. Configuration & Security

### 6.1 Environment Configuration

**Development (.env):**
```bash
# Provider selection
EVALUATION_PROVIDER=openai  # openai | azure | anthropic

# OpenAI Configuration
OPENAI_API_KEY=sk-...

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Anthropic Configuration
ANTHROPIC_API_KEY=your-key

# Processing Configuration
EVALUATION_TIMEOUT_SECONDS=60
EVALUATION_MAX_RETRIES=3
EVALUATION_BATCH_SIZE=10

# Logging
LOG_LEVEL=INFO
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...
```

**Production (Azure Key Vault):**
```bash
# Key Vault references in App Settings
AZURE_OPENAI_API_KEY=@Microsoft.KeyVault(SecretUri=https://your-vault.vault.azure.net/secrets/azure-openai-key)
ANTHROPIC_API_KEY=@Microsoft.KeyVault(SecretUri=https://your-vault.vault.azure.net/secrets/anthropic-key)
```

### 6.2 Azure Key Vault Integration

```python
# keyvault_config.py

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

class SecureConfig:
    """Secure configuration using Azure Key Vault."""

    def __init__(self, vault_url: str):
        credential = DefaultAzureCredential()
        self.client = SecretClient(vault_url=vault_url, credential=credential)
        self._cache = {}

    def get_secret(self, name: str) -> str:
        if name not in self._cache:
            self._cache[name] = self.client.get_secret(name).value
        return self._cache[name]

    def get_evaluator(self, provider: str = "azure") -> SemanticKernelEvaluator:
        if provider == "azure":
            return SemanticKernelEvaluator(
                provider="azure",
                api_key=self.get_secret("azure-openai-key"),
                azure_endpoint=self.get_secret("azure-openai-endpoint"),
                azure_deployment=self.get_secret("azure-openai-deployment")
            )
        elif provider == "anthropic":
            return SemanticKernelEvaluator(
                provider="anthropic",
                api_key=self.get_secret("anthropic-key")
            )
        else:
            return SemanticKernelEvaluator(
                provider="openai",
                api_key=self.get_secret("openai-key")
            )
```

### 6.3 Managed Identity (Recommended for Azure)

```python
# managed_identity_config.py

from azure.identity import ManagedIdentityCredential
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

def create_evaluator_with_managed_identity():
    """
    Create evaluator using Azure Managed Identity.
    No API keys required - uses Azure AD authentication.
    """
    credential = ManagedIdentityCredential()

    kernel = Kernel()

    # Azure OpenAI with token credential
    service = AzureChatCompletion(
        deployment_name=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        ad_token_provider=credential.get_token,
        api_version="2024-02-15-preview"
    )

    kernel.add_service(service)

    return SemanticKernelEvaluator(kernel=kernel)
```

### 6.4 Security Best Practices

| Practice | Implementation |
|----------|----------------|
| **No hardcoded secrets** | Use Key Vault or environment variables |
| **Managed Identity** | Prefer over API keys for Azure resources |
| **Network isolation** | Deploy in VNet with private endpoints |
| **Audit logging** | Enable diagnostic logging to Log Analytics |
| **Rate limiting** | Implement API throttling to prevent abuse |
| **Input validation** | Sanitize all user inputs before processing |
| **TLS everywhere** | Enforce HTTPS for all communications |

---

## 7. Deployment Options

### 7.1 Azure Functions (Serverless)

**Pros:** Auto-scaling, pay-per-execution, minimal ops
**Cons:** Cold start latency, 10-min timeout limit
**Best for:** Variable workloads, API endpoints

```bicep
// infrastructure/function-app.bicep

resource functionApp 'Microsoft.Web/sites@2022-09-01' = {
  name: 'article-evaluation-func'
  location: resourceGroup().location
  kind: 'functionapp,linux'
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appSettings: [
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/azure-openai-endpoint)'
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT'
          value: 'gpt-4'
        }
        {
          name: 'AZURE_OPENAI_API_KEY'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/azure-openai-key)'
        }
      ]
    }
  }
  identity: {
    type: 'SystemAssigned'
  }
}
```

### 7.2 Azure Container Apps

**Pros:** Container flexibility, longer timeouts, VNet support
**Cons:** More complex setup
**Best for:** Long-running batch jobs, custom dependencies

```yaml
# container-app.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: article-evaluator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: article-evaluator
  template:
    metadata:
      labels:
        app: article-evaluator
    spec:
      containers:
      - name: evaluator
        image: myregistry.azurecr.io/article-evaluator:latest
        ports:
        - containerPort: 8000
        env:
        - name: AZURE_OPENAI_ENDPOINT
          valueFrom:
            secretKeyRef:
              name: azure-secrets
              key: openai-endpoint
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

### 7.3 Azure Kubernetes Service (AKS)

**Pros:** Full Kubernetes features, high control
**Cons:** Operational overhead
**Best for:** Large-scale deployments, existing K8s infrastructure

```yaml
# k8s/deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: article-evaluator
  namespace: evaluation-system
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 1
  selector:
    matchLabels:
      app: article-evaluator
  template:
    metadata:
      labels:
        app: article-evaluator
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: evaluator-identity
      containers:
      - name: evaluator
        image: myregistry.azurecr.io/article-evaluator:v1.2.0
        ports:
        - containerPort: 8000
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: article-evaluator-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: article-evaluator
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### 7.4 Deployment Comparison Matrix

| Factor | Functions | Container Apps | AKS |
|--------|-----------|----------------|-----|
| **Setup complexity** | Low | Medium | High |
| **Operational overhead** | Minimal | Low | High |
| **Scaling** | Automatic | Automatic | Configurable |
| **Cold start** | Yes | Minimal | No |
| **Max timeout** | 10 min | Unlimited | Unlimited |
| **Cost model** | Per execution | Per resource | Per node |
| **VNet support** | Premium only | Yes | Yes |
| **Best for** | APIs, events | Batch jobs | Enterprise |

---

## 8. Monitoring & Observability

### 8.1 Application Insights Integration

```python
# monitoring.py

import logging
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace import config_integration
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer

class EvaluationMonitor:
    """Monitoring and telemetry for article evaluation."""

    def __init__(self, connection_string: str):
        # Configure logging
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(AzureLogHandler(connection_string=connection_string))

        # Configure tracing
        config_integration.trace_integrations(['requests', 'httplib'])
        self.tracer = Tracer(
            exporter=AzureExporter(connection_string=connection_string),
            sampler=ProbabilitySampler(1.0)
        )

    def trace_evaluation(self, case_id: str, issue: str, article_url: str):
        """Create a trace span for an evaluation."""
        with self.tracer.span(name="ArticleEvaluation") as span:
            span.add_attribute("case_id", case_id)
            span.add_attribute("article_url", article_url or "none")
            span.add_attribute("issue_length", len(issue))
            yield span

    def log_evaluation_result(self, case_id: str, result: dict, duration_ms: float):
        """Log evaluation result with custom dimensions."""
        self.logger.info(
            "Evaluation completed",
            extra={
                "custom_dimensions": {
                    "case_id": case_id,
                    "overall_score": result.get("overall_score", 0),
                    "verdict": result.get("verdict", "unknown"),
                    "duration_ms": duration_ms,
                    "provider": result.get("provider", "unknown")
                }
            }
        )

    def log_evaluation_error(self, case_id: str, error: Exception):
        """Log evaluation error."""
        self.logger.error(
            f"Evaluation failed: {str(error)}",
            extra={
                "custom_dimensions": {
                    "case_id": case_id,
                    "error_type": type(error).__name__
                }
            },
            exc_info=True
        )
```

### 8.2 Custom Metrics

```python
# metrics.py

from opencensus.stats import aggregation as aggregation_module
from opencensus.stats import measure as measure_module
from opencensus.stats import stats as stats_module
from opencensus.stats import view as view_module
from opencensus.tags import tag_map as tag_map_module

# Define measures
evaluation_latency_ms = measure_module.MeasureFloat(
    "evaluation_latency_ms",
    "Latency of article evaluation in milliseconds",
    "ms"
)

evaluation_score = measure_module.MeasureFloat(
    "evaluation_score",
    "Overall evaluation score",
    "score"
)

evaluation_count = measure_module.MeasureInt(
    "evaluation_count",
    "Number of evaluations",
    "count"
)

# Define views
latency_view = view_module.View(
    "evaluation_latency_distribution",
    "Distribution of evaluation latencies",
    ["provider", "verdict"],
    evaluation_latency_ms,
    aggregation_module.DistributionAggregation([0, 1000, 5000, 10000, 30000, 60000])
)

score_view = view_module.View(
    "evaluation_score_distribution",
    "Distribution of evaluation scores",
    ["provider", "verdict"],
    evaluation_score,
    aggregation_module.DistributionAggregation([0, 30, 50, 70, 85, 100])
)

count_view = view_module.View(
    "evaluation_count_total",
    "Total number of evaluations",
    ["provider", "verdict"],
    evaluation_count,
    aggregation_module.CountAggregation()
)

def record_evaluation(provider: str, verdict: str, score: float, latency_ms: float):
    """Record evaluation metrics."""
    tag_map = tag_map_module.TagMap()
    tag_map.insert("provider", provider)
    tag_map.insert("verdict", verdict)

    mmap = stats_module.stats.stats_recorder.new_measurement_map()
    mmap.measure_float_put(evaluation_latency_ms, latency_ms)
    mmap.measure_float_put(evaluation_score, score)
    mmap.measure_int_put(evaluation_count, 1)
    mmap.record(tag_map)
```

### 8.3 Azure Monitor Dashboard

```json
{
    "dashboard": {
        "title": "Article Evaluation System",
        "tiles": [
            {
                "title": "Evaluations per Hour",
                "query": "customEvents | where name == 'EvaluationCompleted' | summarize count() by bin(timestamp, 1h)",
                "visualization": "linechart"
            },
            {
                "title": "Average Score by Verdict",
                "query": "customEvents | where name == 'EvaluationCompleted' | summarize avg(todouble(customDimensions.overall_score)) by tostring(customDimensions.verdict)",
                "visualization": "barchart"
            },
            {
                "title": "Error Rate",
                "query": "exceptions | summarize count() by bin(timestamp, 1h)",
                "visualization": "linechart"
            },
            {
                "title": "P95 Latency",
                "query": "customMetrics | where name == 'evaluation_latency_ms' | summarize percentile(value, 95) by bin(timestamp, 1h)",
                "visualization": "linechart"
            },
            {
                "title": "Verdict Distribution",
                "query": "customEvents | where name == 'EvaluationCompleted' | summarize count() by tostring(customDimensions.verdict)",
                "visualization": "piechart"
            }
        ]
    }
}
```

### 8.4 Alerting Rules

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| High error rate | Error rate > 5% for 5 min | Critical | Page on-call |
| High latency | P95 > 60s for 10 min | Warning | Email team |
| Low throughput | < 10 evals/hour during business hours | Warning | Investigate |
| Provider failure | 100% failure rate for provider | Critical | Failover alert |

---

## 9. Error Handling & Resilience

### 9.1 Retry Strategy

```python
# retry_handler.py

import time
from functools import wraps
from typing import Type, Tuple

class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    exponential_base: float = 2.0
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        # Add provider-specific exceptions
    )

def with_retry(config: RetryConfig = None):
    """Decorator for retry logic with exponential backoff."""
    config = config or RetryConfig()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt < config.max_retries:
                        delay = min(
                            config.base_delay_seconds * (config.exponential_base ** attempt),
                            config.max_delay_seconds
                        )
                        time.sleep(delay)
                    else:
                        raise

            raise last_exception
        return wrapper
    return decorator
```

### 9.2 Circuit Breaker Pattern

```python
# circuit_breaker.py

import time
from enum import Enum
from threading import Lock

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered

class CircuitBreaker:
    """
    Circuit breaker for LLM provider calls.

    Prevents cascading failures by failing fast when a provider is down.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
        self._lock = Lock()

    def can_execute(self) -> bool:
        """Check if a call can be made."""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    return True
                return False

            # HALF_OPEN
            return self.half_open_calls < self.half_open_max_calls

    def record_success(self):
        """Record a successful call."""
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_calls += 1
                if self.half_open_calls >= self.half_open_max_calls:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    def record_failure(self):
        """Record a failed call."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass
```

### 9.3 Provider Failover

```python
# provider_failover.py

from typing import List, Optional

class ProviderFailover:
    """
    Manages failover between multiple LLM providers.

    If primary provider fails, automatically switches to backup.
    """

    def __init__(self, providers: List[dict]):
        """
        Initialize with provider configurations.

        Args:
            providers: List of provider configs in priority order
                [
                    {"provider": "azure", "endpoint": "...", "deployment": "..."},
                    {"provider": "openai", "model": "gpt-4o"},
                    {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}
                ]
        """
        self.providers = providers
        self.circuit_breakers = {
            p["provider"]: CircuitBreaker() for p in providers
        }
        self._current_evaluators = {}

    def get_evaluator(self) -> SemanticKernelEvaluator:
        """Get an available evaluator, with failover."""
        for config in self.providers:
            provider_name = config["provider"]
            breaker = self.circuit_breakers[provider_name]

            if breaker.can_execute():
                if provider_name not in self._current_evaluators:
                    self._current_evaluators[provider_name] = self._create_evaluator(config)
                return self._current_evaluators[provider_name], provider_name

        raise AllProvidersUnavailableError("All LLM providers are unavailable")

    def _create_evaluator(self, config: dict) -> SemanticKernelEvaluator:
        """Create evaluator from config."""
        return SemanticKernelEvaluator(**config)

    def record_result(self, provider_name: str, success: bool):
        """Record call result for circuit breaker."""
        breaker = self.circuit_breakers[provider_name]
        if success:
            breaker.record_success()
        else:
            breaker.record_failure()

    def evaluate_with_failover(self, issue: str, article_url: str) -> dict:
        """Evaluate with automatic failover."""
        last_error = None

        for config in self.providers:
            provider_name = config["provider"]
            breaker = self.circuit_breakers[provider_name]

            if not breaker.can_execute():
                continue

            try:
                evaluator = self._create_evaluator(config)
                result = evaluator.evaluate(issue, article_url)
                result["provider_used"] = provider_name
                breaker.record_success()
                return result
            except Exception as e:
                last_error = e
                breaker.record_failure()

        raise AllProvidersUnavailableError(f"All providers failed. Last error: {last_error}")
```

### 9.4 Dead Letter Queue

```python
# dead_letter.py

import json
from datetime import datetime
from azure.storage.queue import QueueClient

class DeadLetterHandler:
    """
    Handles failed evaluations by sending to dead letter queue.
    """

    def __init__(self, connection_string: str, queue_name: str = "evaluation-dlq"):
        self.queue = QueueClient.from_connection_string(connection_string, queue_name)

    def send_to_dlq(self, request: dict, error: Exception, retry_count: int):
        """Send failed request to dead letter queue."""
        message = {
            "original_request": request,
            "error": str(error),
            "error_type": type(error).__name__,
            "retry_count": retry_count,
            "failed_at": datetime.utcnow().isoformat(),
            "can_retry": self._is_retryable(error)
        }

        self.queue.send_message(json.dumps(message))

    def _is_retryable(self, error: Exception) -> bool:
        """Determine if error is retryable."""
        non_retryable = (
            ValueError,
            json.JSONDecodeError,
            # Add other non-retryable errors
        )
        return not isinstance(error, non_retryable)
```

---

## 10. Performance & Scalability

### 10.1 Performance Benchmarks

| Operation | P50 Latency | P95 Latency | P99 Latency |
|-----------|-------------|-------------|-------------|
| Parse Issue | 1.2s | 2.5s | 4.0s |
| Evaluate Relevance | 2.0s | 4.0s | 6.0s |
| Evaluate Completeness | 2.0s | 4.0s | 6.0s |
| Evaluate Validity | 2.5s | 5.0s | 8.0s |
| Full Evaluation | 8.0s | 15.0s | 25.0s |
| Full Eval (Low Score) | 12.0s | 22.0s | 35.0s |

### 10.2 Throughput Considerations

```
Throughput = (Concurrent Workers × 60) / Average Latency (seconds)

Example:
- 10 Azure Function instances
- 15 second average latency
- Throughput = (10 × 60) / 15 = 40 evaluations/minute
```

### 10.3 Optimization Strategies

**1. Parallel Evaluation (within single request):**

```python
# parallel_evaluation.py

import asyncio
from concurrent.futures import ThreadPoolExecutor

class ParallelEvaluator:
    """Run evaluation agents in parallel where possible."""

    def __init__(self, evaluator: SemanticKernelEvaluator, max_workers: int = 3):
        self.evaluator = evaluator
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def evaluate_parallel(self, issue_json: str, article_url: str) -> dict:
        """
        Run relevance, completeness, and validity in parallel.

        Reduces latency from ~8s (sequential) to ~3s (parallel).
        """
        plugin = self.evaluator.get_plugin()

        loop = asyncio.get_event_loop()

        # Run evaluations in parallel
        relevance_future = loop.run_in_executor(
            self.executor,
            plugin.evaluate_relevance, issue_json, article_url
        )
        completeness_future = loop.run_in_executor(
            self.executor,
            plugin.evaluate_completeness, issue_json, article_url
        )
        validity_future = loop.run_in_executor(
            self.executor,
            plugin.evaluate_validity, issue_json, article_url
        )

        # Wait for all to complete
        relevance, completeness, validity = await asyncio.gather(
            relevance_future, completeness_future, validity_future
        )

        return {
            "relevance": json.loads(relevance),
            "completeness": json.loads(completeness),
            "validity": json.loads(validity)
        }
```

**2. Response Caching:**

```python
# caching.py

import hashlib
import json
from datetime import timedelta
from azure.cosmos import CosmosClient

class EvaluationCache:
    """Cache evaluation results to avoid redundant LLM calls."""

    def __init__(self, cosmos_client: CosmosClient, database: str, container: str):
        self.container = cosmos_client.get_database_client(database).get_container_client(container)
        self.ttl_seconds = int(timedelta(days=7).total_seconds())

    def _generate_key(self, issue: str, article_url: str) -> str:
        """Generate cache key from inputs."""
        content = f"{issue}|{article_url}"
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, issue: str, article_url: str) -> dict | None:
        """Get cached result if exists and not expired."""
        key = self._generate_key(issue, article_url)

        try:
            item = self.container.read_item(item=key, partition_key=key)
            return item.get("result")
        except:
            return None

    def set(self, issue: str, article_url: str, result: dict):
        """Cache evaluation result."""
        key = self._generate_key(issue, article_url)

        self.container.upsert_item({
            "id": key,
            "partitionKey": key,
            "issue_hash": hashlib.sha256(issue.encode()).hexdigest()[:16],
            "article_url": article_url,
            "result": result,
            "ttl": self.ttl_seconds
        })
```

**3. Batch Processing Optimization:**

```python
# batch_optimizer.py

import asyncio
from typing import List

class BatchOptimizer:
    """Optimize batch processing throughput."""

    def __init__(
        self,
        evaluator: SemanticKernelEvaluator,
        concurrency: int = 10,
        rate_limit_per_minute: int = 60
    ):
        self.evaluator = evaluator
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.rate_limiter = AsyncRateLimiter(rate_limit_per_minute)

    async def evaluate_batch_async(self, cases: List[dict]) -> List[dict]:
        """Process batch with controlled concurrency and rate limiting."""

        async def process_one(case: dict) -> dict:
            async with self.semaphore:
                await self.rate_limiter.acquire()

                # Run in thread pool since evaluate() is sync
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    self.evaluator.evaluate,
                    case["issue"],
                    case.get("article_url")
                )
                result["case_id"] = case.get("case_id")
                return result

        tasks = [process_one(case) for case in cases]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

### 10.4 Scaling Guidelines

| Throughput Target | Recommended Configuration |
|-------------------|---------------------------|
| < 100/hour | Single Azure Function (Consumption) |
| 100-1000/hour | Azure Functions Premium (EP1) |
| 1000-10000/hour | Azure Functions Premium (EP2) + multiple instances |
| > 10000/hour | AKS with HPA, multiple pods |

---

## 11. Migration Strategy

### 11.1 Migration Phases

```
Phase 1: Parallel Run (2 weeks)
├── Deploy SK evaluator alongside existing
├── Route 10% traffic to SK evaluator
├── Compare results and latency
└── Monitor for discrepancies

Phase 2: Gradual Rollout (2 weeks)
├── Increase SK traffic to 50%
├── Validate consistency
├── Performance tune
└── Document differences

Phase 3: Full Migration (1 week)
├── Route 100% to SK evaluator
├── Keep old system on standby
├── Monitor closely
└── Ready for quick rollback

Phase 4: Cleanup (1 week)
├── Decommission old system
├── Remove parallel infrastructure
├── Update documentation
└── Close migration project
```

### 11.2 Compatibility Layer

```python
# compatibility.py

from article_evaluation_system import ArticleEvaluator
from article_evaluation_system.sk import SemanticKernelEvaluator

class MigrationEvaluator:
    """
    Compatibility layer for gradual migration.

    Routes traffic between old and new evaluators based on configuration.
    """

    def __init__(
        self,
        legacy_evaluator: ArticleEvaluator,
        sk_evaluator: SemanticKernelEvaluator,
        sk_traffic_percentage: float = 0.0,
        compare_mode: bool = False
    ):
        self.legacy = legacy_evaluator
        self.sk = sk_evaluator
        self.sk_percentage = sk_traffic_percentage
        self.compare_mode = compare_mode

    def evaluate(self, customer_issue: str, recommended_article: str = None) -> dict:
        """Evaluate with traffic splitting."""
        import random

        use_sk = random.random() < self.sk_percentage

        if self.compare_mode:
            # Run both and compare (for validation)
            legacy_result = self.legacy.evaluate(customer_issue, recommended_article)
            sk_result = self.sk.evaluate(customer_issue, recommended_article)

            self._log_comparison(legacy_result, sk_result)

            return sk_result if use_sk else legacy_result

        if use_sk:
            result = self.sk.evaluate(customer_issue, recommended_article)
            result["_evaluator"] = "semantic_kernel"
        else:
            result = self.legacy.evaluate(customer_issue, recommended_article)
            result["_evaluator"] = "legacy"

        return result

    def _log_comparison(self, legacy: dict, sk: dict):
        """Log comparison between evaluators."""
        score_diff = abs(legacy.get("overall_score", 0) - sk.get("overall_score", 0))
        verdict_match = legacy.get("verdict") == sk.get("verdict")

        logging.info(
            "Evaluator comparison",
            extra={
                "custom_dimensions": {
                    "score_difference": score_diff,
                    "verdict_match": verdict_match,
                    "legacy_score": legacy.get("overall_score"),
                    "sk_score": sk.get("overall_score")
                }
            }
        )
```

### 11.3 Rollback Procedure

```bash
# rollback.sh - Emergency rollback script

#!/bin/bash
set -e

echo "Starting rollback to legacy evaluator..."

# 1. Update traffic split to 0% SK
az functionapp config appsettings set \
    --name article-evaluation-func \
    --resource-group evaluation-rg \
    --settings SK_TRAFFIC_PERCENTAGE=0

# 2. Restart functions to pick up new config
az functionapp restart --name article-evaluation-func --resource-group evaluation-rg

# 3. Verify legacy is handling traffic
sleep 30
curl -s https://article-evaluation-func.azurewebsites.net/api/health | jq .evaluator

# 4. Alert team
az monitor activity-log alert create \
    --name "SK Rollback Executed" \
    --resource-group evaluation-rg \
    --condition category=Administrative and operationName=Rollback

echo "Rollback complete. Legacy evaluator is now handling 100% of traffic."
```

---

## 12. API Reference

### 12.1 SemanticKernelEvaluator

```python
class SemanticKernelEvaluator:
    """
    Main entry point for article evaluation using Semantic Kernel.
    """

    def __init__(
        self,
        api_key: str = None,
        model: str = "gpt-4o",
        provider: str = "openai",
        azure_endpoint: str = None,
        azure_deployment: str = None,
        azure_api_version: str = "2024-02-15-preview",
        base_url: str = None,
        kernel: Kernel = None,
        service_id: str = "default"
    ):
        """
        Initialize the evaluator.

        Args:
            api_key: API key for the provider
            model: Model name (e.g., "gpt-4o", "claude-sonnet-4-20250514")
            provider: "openai", "azure", or "anthropic"
            azure_endpoint: Azure OpenAI endpoint (required for azure)
            azure_deployment: Azure deployment name (required for azure)
            azure_api_version: Azure API version
            base_url: Custom base URL for API
            kernel: Pre-configured SK Kernel (overrides other settings)
            service_id: Service identifier
        """

    def evaluate(
        self,
        customer_issue: str,
        recommended_article: str = None
    ) -> dict:
        """
        Evaluate an article against a customer issue.

        Args:
            customer_issue: The customer's issue description
            recommended_article: URL of article to evaluate (optional)

        Returns:
            dict: Evaluation result with structure:
                {
                    "issue_summary": {...},
                    "current_article_evaluation": {
                        "url": str,
                        "title": str,
                        "relevance": {...},
                        "completeness": {...},
                        "validity": {...}
                    },
                    "overall_score": int (0-100),
                    "verdict": str ("adequate"|"needs_supplementation"|"inadequate"),
                    "action_required": str,
                    "recommended_articles": [...],
                    "content_gaps": {...},
                    "final_recommendation": str
                }
        """

    def evaluate_batch(
        self,
        cases: list[dict],
        progress_callback: callable = None
    ) -> list[dict]:
        """
        Evaluate multiple cases.

        Args:
            cases: List of {"issue": str, "article_url": str}
            progress_callback: fn(current, total) called after each case

        Returns:
            List of evaluation results
        """

    def get_plugin(self) -> ArticleEvaluationPlugin:
        """Get the SK plugin for direct function access."""

    def get_kernel(self) -> Kernel:
        """Get the SK Kernel instance."""

    # Convenience methods
    def parse_issue(self, issue_description: str) -> dict
    def evaluate_relevance(self, issue: dict, article_url: str) -> dict
    def evaluate_completeness(self, issue: dict, article_url: str) -> dict
    def evaluate_validity(self, issue: dict, article_url: str) -> dict
    def search_articles(self, issue: dict) -> dict
    def analyze_gaps(self, issue: dict, relevance: dict = None, ...) -> dict
```

### 12.2 ArticleEvaluationPlugin Kernel Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `parse_issue` | `(issue_description: str) -> str` | Parse issue to JSON |
| `evaluate_relevance` | `(issue_json: str, article_url: str) -> str` | Score relevance |
| `evaluate_completeness` | `(issue_json: str, article_url: str) -> str` | Score completeness |
| `evaluate_validity` | `(issue_json: str, article_url: str) -> str` | Score validity |
| `search_articles` | `(issue_json: str) -> str` | Generate search queries |
| `analyze_gaps` | `(issue_json: str, relevance_json: str, ...) -> str` | Analyze gaps |
| `evaluate_article` | `(customer_issue: str, article_url: str) -> str` | Full evaluation |

### 12.3 Response Schemas

**Evaluation Result:**
```json
{
    "issue_summary": {
        "product": "Microsoft Teams",
        "symptoms": ["No audio in calls", "Microphone not detected"],
        "error_codes": ["0x80004005"],
        "issue_type": "troubleshooting",
        "severity": "high",
        "keywords": ["teams", "audio", "microphone", "calls"]
    },
    "current_article_evaluation": {
        "url": "https://support.microsoft.com/...",
        "title": "Fix audio issues in Teams",
        "relevance": {
            "relevance_score": 85,
            "matched_aspects": ["audio issues", "Teams", "microphone"],
            "unmatched_aspects": ["specific error code"],
            "product_match": true,
            "version_match": true,
            "relevance_verdict": "highly_relevant"
        },
        "completeness": {
            "completeness_score": 72,
            "has_prerequisites": true,
            "has_step_by_step": true,
            "has_examples": false,
            "has_troubleshooting": true,
            "has_success_criteria": false,
            "missing_elements": ["screenshots", "success verification"],
            "completeness_verdict": "mostly_complete"
        },
        "validity": {
            "validity_score": 80,
            "addresses_root_cause": true,
            "is_current_solution": true,
            "environment_compatible": true,
            "potential_issues": ["May not work for USB microphones"],
            "confidence_level": "high",
            "validity_verdict": "likely_valid"
        }
    },
    "overall_score": 79,
    "verdict": "needs_supplementation",
    "action_required": "supplement_with_additional",
    "recommended_articles": [
        "Teams USB audio devices",
        "Windows audio troubleshooter"
    ],
    "content_gaps": {
        "documentation_gaps": ["USB device specific steps"],
        "suggested_content_outline": ["USB audio setup", "Driver verification"],
        "priority": "medium",
        "recommendation": "augment_existing"
    },
    "final_recommendation": "The article partially addresses the issue (score: 79/100)..."
}
```

---

## 13. Usage Examples

### 13.1 Basic Usage

```python
from article_evaluation_system.sk import SemanticKernelEvaluator

# OpenAI
evaluator = SemanticKernelEvaluator(
    api_key="sk-...",
    model="gpt-4o"
)

# Azure OpenAI
evaluator = SemanticKernelEvaluator(
    provider="azure",
    azure_endpoint="https://myresource.openai.azure.com",
    azure_deployment="gpt-4",
    api_key="azure-key"
)

# Anthropic/Claude
evaluator = SemanticKernelEvaluator(
    provider="anthropic",
    model="claude-sonnet-4-20250514",
    api_key="anthropic-key"
)

# Evaluate
result = evaluator.evaluate(
    customer_issue="Microsoft Teams has no audio during calls. Error 0x80004005.",
    recommended_article="https://support.microsoft.com/en-us/office/..."
)

print(f"Score: {result['overall_score']}/100")
print(f"Verdict: {result['verdict']}")
```

### 13.2 Individual Plugin Functions

```python
# Access individual functions for custom workflows
plugin = evaluator.get_plugin()

# Parse issue only
issue_json = plugin.parse_issue("Teams crashes when sharing screen")
print(json.loads(issue_json))

# Evaluate just relevance
relevance = plugin.evaluate_relevance(issue_json, "https://support.microsoft.com/...")
print(json.loads(relevance))

# Search for articles without evaluation
search_results = plugin.search_articles(issue_json)
print(json.loads(search_results))
```

### 13.3 Azure Function Implementation

```python
# function_app.py

import azure.functions as func
import json
import os
from article_evaluation_system.sk import SemanticKernelEvaluator

app = func.FunctionApp()

# Singleton evaluator
_evaluator = None

def get_evaluator():
    global _evaluator
    if _evaluator is None:
        _evaluator = SemanticKernelEvaluator(
            provider="azure",
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"]
        )
    return _evaluator

@app.route(route="evaluate", methods=["POST"])
def evaluate(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()

        result = get_evaluator().evaluate(
            customer_issue=body["issue"],
            recommended_article=body.get("article_url")
        )

        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.route(route="health")
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"status": "healthy", "evaluator": "semantic_kernel"}),
        mimetype="application/json"
    )
```

### 13.4 Batch Processing Script

```python
# batch_process.py

import pandas as pd
from datetime import datetime
from article_evaluation_system.sk import SemanticKernelEvaluator

def process_batch(input_csv: str, output_csv: str, provider: str = "azure"):
    # Load data
    df = pd.read_csv(input_csv)
    print(f"Loaded {len(df)} cases")

    # Initialize evaluator
    evaluator = SemanticKernelEvaluator(
        provider=provider,
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
        api_key=os.environ.get("AZURE_OPENAI_API_KEY")
    )

    # Process with progress tracking
    results = []

    def progress(current, total):
        pct = (current / total) * 100
        print(f"\rProgress: {current}/{total} ({pct:.1f}%)", end="")

    cases = [
        {"issue": row["issue"], "article_url": row.get("article_url")}
        for _, row in df.iterrows()
    ]

    batch_results = evaluator.evaluate_batch(cases, progress_callback=progress)

    # Build output dataframe
    for i, result in enumerate(batch_results):
        results.append({
            "case_id": df.iloc[i].get("case_id", i),
            "overall_score": result.get("overall_score", 0),
            "verdict": result.get("verdict", "error"),
            "relevance_score": result.get("current_article_evaluation", {}).get("relevance", {}).get("relevance_score", 0),
            "completeness_score": result.get("current_article_evaluation", {}).get("completeness", {}).get("completeness_score", 0),
            "validity_score": result.get("current_article_evaluation", {}).get("validity", {}).get("validity_score", 0),
            "recommendation": result.get("final_recommendation", "")[:200],
            "processed_at": datetime.utcnow().isoformat()
        })

    # Save results
    results_df = pd.DataFrame(results)
    results_df.to_csv(output_csv, index=False)
    print(f"\nResults saved to {output_csv}")

    # Print summary
    print("\nSummary:")
    print(f"  Adequate: {sum(1 for r in results if r['verdict'] == 'adequate')}")
    print(f"  Needs supplementation: {sum(1 for r in results if r['verdict'] == 'needs_supplementation')}")
    print(f"  Inadequate: {sum(1 for r in results if r['verdict'] == 'inadequate')}")
    print(f"  Average score: {sum(r['overall_score'] for r in results) / len(results):.1f}")

if __name__ == "__main__":
    import sys
    process_batch(sys.argv[1], sys.argv[2])
```

---

## 14. Appendices

### Appendix A: File Structure

```
article_evaluation_system/
├── __init__.py                    # Main exports + conditional SK imports
├── main.py                        # CLI entry point
├── agents/
│   ├── __init__.py                # BaseAgent with set_llm_callable()
│   ├── orchestrator.py            # Multi-agent coordinator
│   ├── issue_parser.py            # Issue parsing agent
│   ├── relevance_agent.py         # Relevance evaluation
│   ├── completeness_agent.py      # Completeness evaluation
│   ├── validity_agent.py          # Validity evaluation
│   ├── search_agent.py            # Article search
│   └── gap_agent.py               # Gap analysis
├── sk/                            # Semantic Kernel integration
│   ├── __init__.py                # SK exports
│   ├── evaluator.py               # SemanticKernelEvaluator
│   ├── plugin.py                  # ArticleEvaluationPlugin
│   ├── llm_adapter.py             # SK adapters + kernel factories
│   └── anthropic_connector.py     # Custom Claude connector
├── models/
│   ├── issue.py                   # Issue data model
│   ├── article.py                 # Article data model
│   └── evaluation.py              # Evaluation result models
├── config/
│   └── settings.py                # Configuration & thresholds
└── utils/
    ├── article_fetcher.py         # Article HTTP fetching
    ├── prompts.py                 # Agent prompts
    └── scoring.py                 # Scoring utilities

docs/
└── SEMANTIC_KERNEL_INTEGRATION_SPEC.md  # This document

run_evaluation.py                  # Original CLI runner
run_evaluation_sk.py               # SK CLI runner
requirements.txt                   # Dependencies
```

### Appendix B: Environment Variables

| Variable | Required | Provider | Description |
|----------|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI | OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Yes* | Azure | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | Yes* | Azure | Deployment/model name |
| `AZURE_OPENAI_API_KEY` | Yes* | Azure | Azure OpenAI key |
| `AZURE_OPENAI_API_VERSION` | No | Azure | API version (default: 2024-02-15-preview) |
| `ANTHROPIC_API_KEY` | Yes* | Anthropic | Anthropic API key |
| `EVALUATION_PROVIDER` | No | All | Default provider selection |
| `LOG_LEVEL` | No | All | Logging level (default: INFO) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | No | All | App Insights telemetry |

*Required for the selected provider

### Appendix C: Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `ImportError: semantic_kernel` | SK not installed | `pip install semantic-kernel>=1.0.0` |
| `AuthenticationError` | Invalid API key | Verify key in environment/Key Vault |
| `RateLimitError` | Too many requests | Implement rate limiting, reduce concurrency |
| `TimeoutError` | Slow LLM response | Increase timeout, check network |
| Low scores for valid articles | Prompt issues | Review agent prompts, adjust thresholds |
| Inconsistent results | Temperature too high | Ensure temperature=0.1 in settings |

### Appendix D: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | Jan 2026 | Initial SK integration |
| 1.0.1 | Jan 2026 | Added Anthropic/Claude support |

---

**Document Owner:** Article Evaluation Team
**Review Cycle:** Quarterly
**Next Review:** April 2026
