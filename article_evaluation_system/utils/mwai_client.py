"""
MWAI API Client - Wraps the ChatCompletionWithoutData endpoint.

Provides MSAL-based token acquisition and a simple chat completion interface
compatible with the Agentic Insight Engine's BaseAgent.
"""

import json
import logging
import os
import threading
import time

import msal
import requests

logger = logging.getLogger(__name__)

# Delay between MWAI API requests to avoid rate limiting
MWAI_REQUEST_DELAY = 1.2  # seconds — reduce to 0.3 if no 429 rate-limit errors appear

# ---------------------------------------------------------------------------
# MWAI API Configuration
# ---------------------------------------------------------------------------
BASE_API_URL = "https://api.ppe.mwai.microsoft.net/ai/ChatCompletions"
ENDPOINT_WITHOUT_DATA = f"{BASE_API_URL}/ChatCompletionWithoutData"

# ---------------------------------------------------------------------------
# MSAL Configuration
# ---------------------------------------------------------------------------
_CLIENT_ID = "fb189e14-af5d-4383-9ce6-1ea93749aa1e"
_TENANT_ID = "72f988bf-86f1-41af-91ab-2d7cd011db47"
_REDIRECT_URI = "http://localhost"
_SCOPES = ["https://api.ppe.mwai.microsoft.net/Index.Read"]
_AUTHORITY = f"https://login.microsoftonline.com/{_TENANT_ID}"

# MSAL persists tokens here so re-runs are silent (uses refresh token)
_MSAL_CACHE_FILE = os.path.join(os.path.expanduser("~"), ".mwai_msal_cache.json")

# Serialises all token-acquisition calls so parallel threads don't race on the cache file
_TOKEN_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# MSAL token helpers
# ---------------------------------------------------------------------------

def _load_msal_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if os.path.exists(_MSAL_CACHE_FILE):
        with open(_MSAL_CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    return cache


def _save_msal_cache(cache: msal.SerializableTokenCache):
    if cache.has_state_changed:
        with open(_MSAL_CACHE_FILE, "w") as f:
            f.write(cache.serialize())


def acquire_msal_token(force_refresh: bool = False) -> str:
    """
    Acquire an MWAI access token via MSAL (thread-safe).

    Tries silent acquisition first (using cached refresh token).
    Falls back to interactive browser auth on first run or after cache is cleared.

    Args:
        force_refresh: When True, bypass the cached access token and use the
                       refresh token to get a new one (call after receiving a 401).

    Returns:
        Access token string
    """
    with _TOKEN_LOCK:
        cache = _load_msal_cache()
        app = msal.PublicClientApplication(
            client_id=_CLIENT_ID,
            authority=_AUTHORITY,
            token_cache=cache,
        )

        result = None
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(
                _SCOPES, account=accounts[0], force_refresh=force_refresh
            )

        if not result:
            logger.info("No cached MSAL credentials — launching browser for authentication...")
            result = app.acquire_token_interactive(scopes=_SCOPES)

        _save_msal_cache(cache)

    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown MSAL error"))
        raise RuntimeError(f"MSAL authentication failed: {error}")

    logger.info("MSAL token acquired successfully.")
    return result["access_token"]


def resolve_mwai_token(token: str = None, force_new: bool = False) -> str:
    """
    Resolve an MWAI bearer token.

    Args:
        token: Explicit token string override (skips MSAL)
        force_new: Clear MSAL cache and force interactive re-authentication

    Returns:
        Valid bearer token string
    """
    if token:
        return token

    if force_new and os.path.exists(_MSAL_CACHE_FILE):
        os.remove(_MSAL_CACHE_FILE)
        logger.info("MSAL cache cleared — will re-authenticate interactively.")

    return acquire_msal_token()


# ---------------------------------------------------------------------------
# MWAI Client
# ---------------------------------------------------------------------------

class MwaiClient:
    """
    Lightweight client for the MWAI ChatCompletionWithoutData API.

    Designed as a drop-in replacement for OpenAI/Anthropic clients
    within the Agentic Insight Engine's agent framework.
    """

    def __init__(self, token: str, timeout: int = 120, _via_msal: bool = False, model: str = "gpt-4o"):
        """
        Initialize the MWAI client.

        Args:
            token: MWAI bearer token
            timeout: Request timeout in seconds
            _via_msal: True when token came from MSAL — enables silent refresh
                       before each request via acquire_token_silent.
            model: Deployment/model name sent in the API payload.
        """
        self.token = token
        self.timeout = timeout
        self._via_msal = _via_msal
        self.model = model

    def _ensure_token_fresh(self) -> None:
        """
        Refresh the bearer token via MSAL before each request.

        MSAL returns a cached token when it is still valid and silently
        acquires a new one (using the refresh token) when it has expired.
        No-op when the token was supplied explicitly (not via MSAL).
        """
        if not self._via_msal:
            return
        self.token = acquire_msal_token()

    def chat_completion(self, system_prompt: str, user_message: str) -> str:
        """
        Call ChatCompletionWithoutData and return the response text.

        Args:
            system_prompt: System prompt content
            user_message: User message content

        Returns:
            The assistant's response text

        Raises:
            RuntimeError: If the API call fails
        """
        self._ensure_token_fresh()

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AgenticInsightEngine/1.0",
        }
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "model": self.model,
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }

        logger.info(f"MWAI request to {ENDPOINT_WITHOUT_DATA}")
        logger.debug(
            "MWAI payload (system prompt first 200 chars): %s",
            system_prompt[:200]
        )
        logger.debug(
            "MWAI payload (user message first 300 chars): %s",
            user_message[:300]
        )

        resp = requests.post(
            ENDPOINT_WITHOUT_DATA,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        logger.info(f"MWAI response status: {resp.status_code}")
        logger.debug(f"MWAI raw response (first 1000 chars): {resp.text[:1000]}")

        # On 401, force-refresh the token and retry once
        if resp.status_code == 401 and self._via_msal:
            logger.warning("MWAI returned 401 — forcing token refresh and retrying...")
            self.token = acquire_msal_token(force_refresh=True)
            headers["Authorization"] = f"Bearer {self.token}"
            resp = requests.post(
                ENDPOINT_WITHOUT_DATA,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            logger.info(f"MWAI retry response status: {resp.status_code}")

        # Sleep after each request to avoid rate limiting
        logger.debug(f"Sleeping {MWAI_REQUEST_DELAY}s between MWAI requests...")
        time.sleep(MWAI_REQUEST_DELAY)

        if resp.status_code < 200 or resp.status_code >= 300:
            logger.error(
                f"MWAI API error {resp.status_code}: {resp.text[:500]}"
            )
            raise RuntimeError(
                f"MWAI API error {resp.status_code}: {resp.text[:500]}"
            )

        extracted = self._extract_response_text(resp)
        logger.debug(
            "MWAI extracted response (first 500 chars): %s",
            extracted[:500] if extracted else "<empty>"
        )
        return extracted

    @staticmethod
    def _extract_response_text(resp: requests.Response) -> str:
        """
        Extract the assistant's text from the MWAI API response.

        Handles multiple possible response formats:
        - OpenAI-compatible: {"choices": [{"message": {"content": "..."}}]}
        - Plain text response
        - Direct content field: {"content": "..."}
        """
        try:
            body = resp.json()
        except (ValueError, requests.exceptions.JSONDecodeError):
            # Plain text response
            logger.debug("MWAI response format: plain text (non-JSON)")
            return resp.text

        logger.debug(
            "MWAI response body keys: %s",
            list(body.keys()) if isinstance(body, dict) else type(body).__name__
        )

        # OpenAI-compatible format
        if isinstance(body, dict):
            # choices[].message.content
            choices = body.get("choices")
            if choices and isinstance(choices, list):
                message = choices[0].get("message", {})
                content = message.get("content")
                if content:
                    logger.debug("MWAI response format: OpenAI-compatible (choices[0].message.content)")
                    return content

            # Direct content field
            if "content" in body:
                logger.debug("MWAI response format: direct content field")
                return body["content"]

            # Message field
            if "message" in body and isinstance(body["message"], str):
                logger.debug("MWAI response format: message string field")
                return body["message"]

            # Response field
            if "response" in body:
                logger.debug("MWAI response format: response field")
                return str(body["response"])

            # result field
            if "result" in body:
                logger.debug("MWAI response format: result field")
                return str(body["result"])

        # If body is a string
        if isinstance(body, str):
            logger.debug("MWAI response format: JSON string body")
            return body

        # Last resort: return the full JSON as string
        logger.warning(
            "MWAI response format: UNKNOWN - returning full JSON. Keys: %s",
            list(body.keys()) if isinstance(body, dict) else type(body).__name__
        )
        return json.dumps(body)
