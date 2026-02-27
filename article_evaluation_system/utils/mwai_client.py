"""
MWAI API Client - Wraps the ChatCompletionWithoutData endpoint.

Provides token management (caching, expiration) and a simple chat completion interface
compatible with the article evaluation system's BaseAgent.
"""

import base64
import json
import logging
import os
import sys
import time
import webbrowser

import requests

logger = logging.getLogger(__name__)

# Delay between MWAI API requests to avoid rate limiting
MWAI_REQUEST_DELAY = 2  # seconds

# ---------------------------------------------------------------------------
# MWAI API Configuration
# ---------------------------------------------------------------------------
BASE_API_URL = "https://api.mwai.microsoft.com/ai/ChatCompletions"
AUTH_ME_URL = "https://playground.mwai.microsoft.com/.auth/me"

ENDPOINT_WITHOUT_DATA = f"{BASE_API_URL}/ChatCompletionWithoutData"

# Token cache lives next to the user's home directory
TOKEN_CACHE_FILE = os.path.join(os.path.expanduser("~"), ".mwai_token")


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _is_token_expired(token: str) -> bool:
    """Check if a JWT token is expired by decoding the payload."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp", 0)
        return time.time() >= exp
    except Exception:
        return True


def _load_cached_token() -> str | None:
    """Load token from cache file if it exists and is not expired."""
    if not os.path.exists(TOKEN_CACHE_FILE):
        return None
    with open(TOKEN_CACHE_FILE, "r") as f:
        token = f.read().strip()
    if not token or _is_token_expired(token):
        return None
    return token


def _save_token_to_cache(token: str):
    """Save token to local cache file."""
    with open(TOKEN_CACHE_FILE, "w") as f:
        f.write(token)


def _prompt_for_token() -> str:
    """Open .auth/me in browser and prompt user to paste the access_token."""
    print("[*] Opening the MWAI auth endpoint in your browser...")
    print(f"    {AUTH_ME_URL}")
    webbrowser.open(AUTH_ME_URL)
    print()
    print('    1. Log in if prompted')
    print('    2. Copy the "access_token" value from the JSON response')
    print('    3. Paste it below')
    print()
    token = input("    access_token: ").strip()
    if not token:
        print("ERROR: No token provided.")
        sys.exit(1)
    return token


def resolve_mwai_token(token: str = None, force_new: bool = False) -> str:
    """
    Resolve an MWAI bearer token.

    Priority: explicit token arg > cached token > interactive prompt.

    Args:
        token: Explicit token string (e.g. from --token CLI arg)
        force_new: Force interactive prompt even if cache exists

    Returns:
        Valid bearer token string
    """
    if token:
        if not _is_token_expired(token):
            _save_token_to_cache(token)
        return token

    # Check environment variable
    env_token = os.environ.get("MWAI_TOKEN", "").strip()
    if env_token:
        if not _is_token_expired(env_token):
            logger.info("Using MWAI token from MWAI_TOKEN environment variable.")
            _save_token_to_cache(env_token)
            return env_token
        else:
            logger.warning("MWAI_TOKEN environment variable is set but token is expired.")

    if not force_new:
        cached = _load_cached_token()
        if cached:
            logger.info("Using cached MWAI token (still valid).")
            return cached

    token = _prompt_for_token()

    if _is_token_expired(token):
        logger.warning("This token appears to be expired.")
    else:
        _save_token_to_cache(token)
        logger.info("MWAI token cached for future runs.")

    return token


# ---------------------------------------------------------------------------
# MWAI Client
# ---------------------------------------------------------------------------

class MwaiClient:
    """
    Lightweight client for the MWAI ChatCompletionWithoutData API.

    Designed as a drop-in replacement for OpenAI/Anthropic clients
    within the article evaluation system's agent framework.
    """

    def __init__(self, token: str, timeout: int = 120):
        """
        Initialize the MWAI client.

        Args:
            token: MWAI bearer token (JWT)
            timeout: Request timeout in seconds
        """
        self.token = token
        self.timeout = timeout

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
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "ArticleEvaluationSystem/1.0",
        }
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
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
