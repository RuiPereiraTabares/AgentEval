# LLM Provider Setup

The system uses MWAI as its LLM provider. All agents use the same evaluation logic -- only the API call configuration differs.

## Provider Details

| Feature | MWAI |
|---------|------|
| Default model | (server-side) |
| Auth | JWT bearer token |
| Env var | `MWAI_TOKEN` |
| JSON mode | Yes (`response_format`) |
| Rate limit delay | 2s between requests |
| Max tokens | 4096 |
| Temperature | 0.1 |

## MWAI Setup

MWAI (Microsoft Web Azure AI) uses a bearer token (JWT) for authentication against the `ChatCompletionWithoutData` endpoint.

**File:** `utils/mwai_client.py`

### Token Flow

Priority for token resolution (`resolve_mwai_token()`):

1. **Explicit token** -- `--token` CLI arg or direct parameter
2. **Environment variable** -- `MWAI_TOKEN`
3. **Cached token** -- `~/.mwai_token` file (if not expired)
4. **Interactive prompt** -- opens `https://playground.mwai.microsoft.com/.auth/me` in browser, user pastes the `access_token`

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
python run_evaluation.py

# Explicit token:
python run_evaluation.py --token eyJ0eX...

# Force new token:
python run_evaluation.py --new-token
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

The client handles multiple response formats: `choices[0].message.content`, direct `content` field, `message` string, `response` field, `result` field, and plain text.

### Endpoint

```
POST https://api.mwai.microsoft.com/ai/ChatCompletions/ChatCompletionWithoutData
Authorization: Bearer <JWT>
Content-Type: application/json
User-Agent: ArticleEvaluationSystem/1.0
```

## Content Truncation

All providers receive truncated article content to stay within context limits. The `ArticleFetcher` provides `get_content_summary(max_length)` on the Article model, and system prompts are designed for content up to approximately 8000 characters.
