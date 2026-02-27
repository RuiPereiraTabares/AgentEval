# Transfer Reason Classification

The `TransferReasonAgent` runs **last** in the pipeline, after all other agents have produced their scores. It synthesizes CSV metadata, upstream agent scores, and escalation-signal detection to classify **why** a support case was transferred.

**File:** `agents/transfer_reason_agent.py`

## Transfer Reason Categories

| Reason | Description |
|--------|-------------|
| `not_transferred` | Case was not transferred (fast path) |
| `customer_escalation` | Customer explicitly requested escalation (>= 2 signals detected) |
| `poor_description` | Description too vague (KT score < 40), root cause of transfer |
| `poor_description_bad_citation` | Vague description *caused* an irrelevant citation (cascade) |
| `no_citation_found` | Description was adequate but no articles were found (documentation gap) |
| `bad_citation_match` | Description was adequate but the cited article is irrelevant |
| `inadequate_article` | Citation is relevant but the article doesn't fully solve the problem |
| `unknown` | All quality signals are within thresholds — reason undetermined |

## Decision Tree

```
transferred?
  |
  +-- False (or None) --> "not_transferred" (confidence: high)
  |
  +-- True
       |
       +-- escalation_signals >= 2?
       |     +-- Yes --> "customer_escalation" (confidence: high)
       |     +-- No  --> continue
       |
       +-- description_quality < 40?
       |     |
       |     +-- Yes (poor description):
       |     |     |
       |     |     +-- has citations AND relevance < 50?
       |     |     |     +-- Yes --> "poor_description_bad_citation" (high)
       |     |     |     +-- No  --> "poor_description" (high)
       |     |     |
       |     |     +-- no citations?
       |     |           +-- Yes --> "poor_description" (high)
       |     |
       |     +-- No (description >= 40):
       |           |
       |           +-- no citations?
       |           |     +-- Yes --> "no_citation_found" (high)
       |           |
       |           +-- relevance < 50?
       |           |     +-- Yes --> "bad_citation_match" (high)
       |           |
       |           +-- overall_score < 60?
       |           |     +-- Yes --> "inadequate_article" (medium)
       |           |
       |           +-- else --> "unknown" (low)
```

## Escalation Signal Detection

The agent uses a two-phase approach to detect customer escalation intent.

### Phase 1: Heuristic Keyword Patterns

13 compiled regex patterns scan the issue description:

| # | Pattern | Example Match |
|---|---------|---------------|
| 1 | `\bescalat(e\|ed\|ion\|ing)\b` | "Please escalate this case" |
| 2 | `\btransfer\s+(me\|this\|the case\|to)\b` | "Transfer me to a specialist" |
| 3 | `\bspeak\s+to\s+(a\s+)?(manager\|supervisor\|specialist\|engineer)\b` | "I need to speak to a manager" |
| 4 | `\bneed\s+(a\s+)?specialist\b` | "We need a specialist on this" |
| 5 | `\b(unacceptable\|ridiculous\|outrageous)\b` | "This is unacceptable" |
| 6 | `\b(\d+)(st\|nd\|rd\|th)\s+time\s+(calling\|contacting\|reaching)\b` | "This is the 3rd time calling" |
| 7 | `\balready\s+contact(ed)?\s+support\b` | "I already contacted support" |
| 8 | `\bprevious\s+case\b` | "Reference my previous case" |
| 9 | `\bSLA\s+breach\b` | "This is an SLA breach" |
| 10 | `\bbusiness\s+is\s+stopped\b` | "Our business is stopped" |
| 11 | `\bcritical\s+deadline\b` | "We have a critical deadline" |
| 12 | `\bexecutive\s+sponsor\b` | "Our executive sponsor is asking" |
| 13 | `\bVP\s+is\s+asking\b` | "The VP is asking for an update" |

### Phase 2: LLM Escalation Detection

If the description is >= 30 characters AND (heuristic signals were found OR text > 200 characters), the agent calls the LLM with the `TRANSFER_REASON_ESCALATION_DETECTION` prompt. The LLM returns:

```json
{
    "escalation_detected": true,
    "escalation_signals": ["customer frustration with repeated contacts", "..."]
}
```

LLM-detected signals are merged with heuristic signals (deduped). If the LLM call fails, only heuristic signals are used.

### Escalation Threshold

**>= 2 signals** are required to classify as `customer_escalation`. This prevents false positives from single keyword matches.

## Narrative Generation

The agent generates a human-readable narrative for each classification. Templates per reason:

| Reason | Narrative Template |
|--------|-------------------|
| `not_transferred` | "This case was not transferred — no root-cause analysis required." |
| `customer_escalation` | "The case was transferred because the customer explicitly requested escalation. Detected signals: {signals}." |
| `poor_description` | "The case description is too vague (KT score: {score}/100)..." |
| `poor_description_bad_citation` | "The vague description (KT score: {score}/100) likely caused the LLM to select an irrelevant article (relevance: {rel}/100)..." |
| `no_citation_found` | "The description was adequate (KT score: {score}/100) but no citations were found..." |
| `bad_citation_match` | "The description was adequate (KT score: {score}/100) but the cited article is not relevant (relevance: {rel}/100)..." |
| `inadequate_article` | "The description was adequate...and the citation is relevant...but the article does not fully solve the problem (overall: {score}/100)." |
| `unknown` | "The transfer reason could not be determined. All quality signals are within acceptable ranges..." |

## Configuration Thresholds

From `config/settings.py`:

```python
TRANSFER_CLASSIFICATION_THRESHOLDS = {
    "poor_description_ceiling": 40,          # KT score below this -> description is root cause
    "bad_citation_relevance_ceiling": 50,    # Relevance below this -> citation doesn't match
    "inadequate_article_overall_ceiling": 60  # Overall below this -> article insufficient
}
```

These thresholds control the decision tree branches. Adjusting them changes classification sensitivity — see [Contributing > Modifying scoring weights and thresholds](contributing.md#modifying-scoring-weights-and-thresholds).
