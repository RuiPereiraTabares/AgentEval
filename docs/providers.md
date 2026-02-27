# LLM Provider Setup

The system supports three LLM providers via `BaseAgent._call_claude()`, plus an optional Semantic Kernel integration. All providers use the same agent logic — only the API call differs.

## Provider Comparison

| Feature | OpenAI | Anthropic | MWAI |
|---------|--------|-----------|------|
| Default model | `gpt-4o` | `claude-sonnet-4-20250514` | (server-side) |
| Auth | API key | API key | JWT bearer token |
| Env var | `OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | `MWAI_TOKEN` |
| Custom base URL | Yes | No | No (fixed endpoint) |
| JSON mode | No | No | Yes (`response_format`) |
| Rate limit delay | None | None | 2s between requests |
| Max tokens | 4096 | 4096 | 4096 |
| Temperature | 0.1 | 0.1 | 0.1 |

## OpenAI Setup

### Environment

```env
OPENAI_API_KEY=sk-proj-...
```

### CLI

```bash
python run_evaluation.py --provider openai --model gpt-4o
```

### Custom Base URL

For API proxies or Azure OpenAI endpoints:

```bash
python run_evaluation.py --provider openai --base-url https://my-proxy.com/v1
```

### API Call

```python
# agents/__init__.py, BaseAgent._call_claude()
response = self.client.chat.completions.create(
    model=self.model,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ],
    max_tokens=4096,
    temperature=0.1
)
text = response.choices[0].message.content
```

## Anthropic / Claude Setup

### Environment

```env
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### CLI

```bash
python run_evaluation.py --provider anthropic --model claude-sonnet-4-20250514
```

### API Call

```python
# agents/__init__.py, BaseAgent._call_claude()
response = self.client.messages.create(
    model=self.model,
    max_tokens=4096,
    system=system_prompt,
    messages=[{"role": "user", "content": user_message}]
)
text = response.content[0].text
```

## MWAI Setup

MWAI (Microsoft Web Azure AI) uses a bearer token (JWT) for authentication against the `ChatCompletionWithoutData` endpoint.

**File:** `utils/mwai_client.py`

### Token Flow

Priority for token resolution (`resolve_mwai_token()`):

1. **Explicit token** — `--token` CLI arg or direct parameter
2. **Environment variable** — `MWAI_TOKEN`
3. **Cached token** — `~/.mwai_token` file (if not expired)
4. **Interactive prompt** — opens `https://playground.mwai.microsoft.com/.auth/me` in browser, user pastes the `access_token`

### JWT Handling

- Tokens are decoded (base64 payload) to check the `exp` claim
- Expired tokens trigger re-authentication
- Valid tokens are cached to `~/.mwai_token`
- The `--new-token` CLI flag forces re-prompt regardless of cache

### Rate Limiting

MWAI has a hardcoded 2-second delay between requests (`MWAI_REQUEST_DELAY = 2` in `mwai_client.py`).

### Interactive Auth

```bash
# First run (prompts for token):
python run_evaluation.py --provider mwai

# Explicit token:
python run_evaluation.py --provider mwai --token eyJ0eX...

# Force new token:
python run_evaluation.py --provider mwai --new-token
```

### API Call

```python
# utils/mwai_client.py, MwaiClient.chat_completion()
payload = {
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ],
    "temperature": 0.1,
    "max_tokens": 4096,
    "response_format": {"type": "json_object"},
}
resp = requests.post(ENDPOINT_WITHOUT_DATA, headers=headers, json=payload)
```

The client handles multiple response formats: OpenAI-compatible (`choices[0].message.content`), direct `content` field, `message` string, `response` field, `result` field, and plain text.

### Endpoint

```
POST https://api.mwai.microsoft.com/ai/ChatCompletions/ChatCompletionWithoutData
Authorization: Bearer <JWT>
Content-Type: application/json
User-Agent: ArticleEvaluationSystem/1.0
```

## Semantic Kernel Integration

**Directory:** `article_evaluation_system/sk/`

The SK integration is optional and provides an alternative execution path using Microsoft's Semantic Kernel framework.

### Components

| File | Description |
|------|-------------|
| `sk/__init__.py` | Exports `SemanticKernelEvaluator`, `ArticleEvaluationPlugin` |
| `sk/anthropic_connector.py` | Custom Anthropic connector for SK |
| `sk/llm_adapter.py` | Adapter wrapping SK kernel as an LLM callable |
| `sk/plugin.py` | SK plugin with evaluation functions |
| `sk/evaluator.py` | SK-based evaluator wrapper |

### How It Works

The SK integration uses `BaseAgent.set_llm_callable()` to inject a Semantic Kernel-backed callable into each agent. The agents' evaluation logic remains unchanged — only the LLM call is routed through SK.

```python
# Pseudo-code for SK integration
from article_evaluation_system.sk import SemanticKernelEvaluator

sk_evaluator = SemanticKernelEvaluator(...)
result = sk_evaluator.evaluate(customer_issue="...", ...)
```

### Azure OpenAI (SK Only)

The Semantic Kernel integration supports Azure OpenAI endpoints. See the [SK Integration Spec](SEMANTIC_KERNEL_INTEGRATION_SPEC.md) for full details.

### Availability Check

```python
from article_evaluation_system import SK_AVAILABLE

if SK_AVAILABLE:
    from article_evaluation_system import SemanticKernelEvaluator
```

SK imports are conditional — the system works without Semantic Kernel packages installed.

## Content Truncation

All providers receive truncated article content to stay within context limits. The `ArticleFetcher` provides `get_content_summary(max_length)` on the Article model, and system prompts are designed for content up to approximately 8000 characters.
