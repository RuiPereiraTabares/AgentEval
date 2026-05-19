"""
Agent modules for the Agentic Insight Engine.
"""

from abc import ABC, abstractmethod
import json
import logging
import re
import time

logger = logging.getLogger(__name__)


class LLMRefusalError(ValueError):
    """Raised when the LLM refuses to process a request (RAI guardrail)."""
    pass


_RAI_MAX_RETRIES = 3        # extra attempts after first refusal
_RAI_RETRY_DELAY = 2.0      # seconds between retries
_RAI_RETRY_PREFIXES = [
    "Please provide a technical quality evaluation of the following Microsoft support content:\n\n",
    "Please analyze the following technical documentation for topical relevance to the user inquiry:\n\n",
    "As a documentation analyst, assess the following enterprise IT support material:\n\n",
    "Evaluate this Microsoft knowledge base article against the given technical inquiry:\n\n",
]
# Progressive truncation limits per retry attempt (attempt index 1-based)
_RAI_RETRY_TRUNCATE = {1: 4000, 2: 2000, 3: 800}

# Patterns that indicate the LLM refused to answer (shared across all agents)
_REFUSAL_PATTERNS = (
    "sorry, i can't help",    "sorry, i cannot help",
    "sorry, we can't",        "sorry, we cannot",
    "sorry we can't",         "sorry we cannot",
    "i can't assist",         "i cannot assist",
    "we can't assist",        "we cannot assist",
    "i'm unable to",          "i am unable to",
    "we're unable to",        "we are unable to",
    "i'm not able to",        "i am not able to",
    "i can't provide",        "i cannot provide",
    "we can't provide",       "we cannot provide",
    "as an ai",
    "i don't have the ability",
    "cannot process this",
    "this request cannot be processed",
)


def _is_refusal(text: str) -> bool:
    """Return True if the text matches a known LLM refusal pattern."""
    lower = text.lower().strip()
    return any(p in lower for p in _REFUSAL_PATTERNS)


def _log_refusal(agent_name: str, response: str, context: dict,
                 retry_count: int = 0, rai_penalty: bool = False,
                 system_prompt: str = "", user_message: str = "") -> None:
    """Log a refusal to the refusal CSV via refusal_logger."""
    try:
        from ..utils.refusal_logger import log_refusal
        log_refusal(agent_name, response, context,
                    retry_count=retry_count, rai_penalty=rai_penalty,
                    system_prompt=system_prompt, user_message=user_message)
    except Exception as e:
        logger.debug(f"[_log_refusal] Could not write to refusal log: {e}")


class BaseAgent(ABC):
    """Base class for all evaluation agents."""

    def __init__(self, client, model: str = "gpt-4o", provider: str = "mwai"):
        """
        Initialize the agent.

        Args:
            client: MWAI client instance
            model: Model to use for evaluations
            provider: API provider ("mwai")
        """
        self.client = client
        self.model = model
        self.provider = provider
        self._llm_callable = None  # Optional injectable LLM callable
        self._refusal_context: dict = {}  # Populated by agents before _call_llm for refusal logging
        self._last_system_prompt: str = ""  # Last system prompt sent (for refusal logging)
        self._last_user_message: str = ""   # Last user message sent (for refusal logging)

    def set_llm_callable(self, callable_fn):
        """
        Set a custom LLM callable for this agent.

        This allows injecting an alternative LLM implementation (e.g., Semantic Kernel)
        without modifying the agent's evaluation logic.

        Args:
            callable_fn: A callable that takes (system_prompt, user_message) and returns str
        """
        self._llm_callable = callable_fn

    @abstractmethod
    def evaluate(self, **kwargs) -> dict:
        """
        Perform the agent's evaluation task.

        Returns:
            Evaluation result dictionary
        """
        pass

    def _call_llm(self, system_prompt: str, user_message: str) -> str:
        """
        Make a call to the MWAI LLM API, with RAI refusal retry logic.

        Args:
            system_prompt: The system prompt
            user_message: The user message

        Returns:
            LLM response text

        Raises:
            LLMRefusalError: If all retry attempts are refused by RAI guardrails.
        """
        agent_name = self.__class__.__name__
        logger.info(f"[{agent_name}] Calling LLM (provider={self.provider}, model={self.model})")
        logger.debug(
            f"[{agent_name}] System prompt (first 200 chars): {system_prompt[:200]}"
        )
        logger.debug(
            f"[{agent_name}] User message (first 500 chars): {user_message[:500]}"
        )

        self._last_system_prompt = system_prompt
        self._last_user_message = user_message

        for attempt in range(1 + _RAI_MAX_RETRIES):
            if attempt > 0:
                prefix = _RAI_RETRY_PREFIXES[min(attempt - 1, len(_RAI_RETRY_PREFIXES) - 1)]
                char_limit = _RAI_RETRY_TRUNCATE.get(attempt)
                truncated = user_message[:char_limit] if char_limit else user_message
                effective_message = prefix + truncated
            else:
                effective_message = user_message

            self._last_user_message = effective_message

            _is_http_error = False
            try:
                response = (
                    self._llm_callable(system_prompt, effective_message)
                    if self._llm_callable is not None
                    else self.client.chat_completion(system_prompt, effective_message)
                )
            except RuntimeError as exc:
                # HTTP 5xx from MWAI — the wrapper returns 500 for RAI blocks, so
                # treat it like a text refusal and let the retry loop rephrase the prompt
                if "mwai api error 5" in str(exc).lower():
                    logger.warning(
                        f"[{agent_name}] HTTP 5xx on attempt {attempt + 1} — "
                        f"treating as RAI refusal, will retry with rephrased prompt: {exc}"
                    )
                    _is_http_error = True
                    response = str(exc)[:200]
                else:
                    raise

            if not _is_refusal(response) and not _is_http_error:
                if attempt > 0:
                    logger.info(f"[{agent_name}] Recovered from RAI refusal on attempt {attempt + 1}")
                    _log_refusal(agent_name, response, self._refusal_context,
                                 retry_count=attempt, rai_penalty=False,
                                 system_prompt=system_prompt, user_message=effective_message)
                else:
                    logger.info(f"[{agent_name}] Got response ({len(response)} chars)")
                logger.debug(f"[{agent_name}] Raw response (first 500 chars): {response[:500]}")
                return response

            logger.warning(f"[{agent_name}] RAI refusal (attempt {attempt + 1}): {response[:120]}")

            if attempt < _RAI_MAX_RETRIES:
                logger.info(f"[{agent_name}] Retrying in {_RAI_RETRY_DELAY}s...")
                time.sleep(_RAI_RETRY_DELAY)

        # All retries exhausted
        _log_refusal(agent_name, response, self._refusal_context,
                     retry_count=_RAI_MAX_RETRIES + 1, rai_penalty=True,
                     system_prompt=system_prompt, user_message=effective_message)
        logger.error(
            f"[{agent_name}] RAI penalty — all {_RAI_MAX_RETRIES + 1} attempts refused. "
            f"case_id={self._refusal_context.get('case_id', '')} "
            f"article_url={self._refusal_context.get('article_url', '')}"
        )
        raise LLMRefusalError(
            f"RAI penalty after {_RAI_MAX_RETRIES + 1} attempts: {response[:200]}"
        )

    def _parse_json_response(self, response: str) -> dict:
        """
        Parse JSON from LLM response, handling markdown code blocks.

        Args:
            response: LLM response text

        Returns:
            Parsed JSON dictionary
        """
        agent_name = self.__class__.__name__

        # Detect LLM content refusal before attempting JSON parse (safety net for
        # refusals that slipped past _call_llm, e.g. via injected callables)
        if _is_refusal(response):
            _log_refusal(agent_name, response, self._refusal_context,
                         retry_count=0, rai_penalty=True,
                         system_prompt=self._last_system_prompt,
                         user_message=self._last_user_message)
            logger.warning(f"[{agent_name}] LLM refused to process request: {response[:150]}")
            raise LLMRefusalError(f"LLM refused: {response[:200]}")

        # Try to extract JSON from markdown code blocks (closed fence first)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1)
            logger.debug(f"[{agent_name}] Extracted JSON from markdown code block")
        else:
            # Handle unclosed fence (LLM started ``` but response was truncated before closing ```)
            open_fence = re.search(r'```(?:json)?\s*([\s\S]+)', response)
            if open_fence:
                json_str = open_fence.group(1).strip()
                logger.debug(f"[{agent_name}] Extracted JSON from unclosed markdown fence")
            else:
                json_str = response
                logger.debug(f"[{agent_name}] No markdown code block found, using raw response")

        def _strip_trailing_commas(s: str) -> str:
            # Remove trailing commas before } or ]
            return re.sub(r',\s*([}\]])', r'\1', s)

        def _try_parse(s: str) -> dict:
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return json.loads(_strip_trailing_commas(s))

        def _repair_parse(s: str) -> dict:
            from json_repair import repair_json
            return repair_json(s, return_objects=True)

        try:
            parsed = _try_parse(json_str)
            logger.info(f"[{agent_name}] JSON parsed successfully. Keys: {list(parsed.keys())}")
            logger.debug(f"[{agent_name}] Full parsed JSON: {json.dumps(parsed, indent=2)[:2000]}")
            return parsed
        except json.JSONDecodeError as e:
            logger.debug(f"[{agent_name}] First JSON parse attempt failed: {e}")
            # Try json-repair first — handles truncation, trailing commas, missing quotes, etc.
            try:
                parsed = _repair_parse(json_str or response)
                if isinstance(parsed, dict):
                    logger.info(
                        f"[{agent_name}] JSON repaired successfully. Keys: {list(parsed.keys())}"
                    )
                    return parsed
            except Exception:
                pass
            # Last resort: extract bare {...} block from raw response and repair
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    parsed = _repair_parse(json_match.group())
                    if isinstance(parsed, dict):
                        logger.info(
                            f"[{agent_name}] JSON extracted+repaired via regex fallback. Keys: {list(parsed.keys())}"
                        )
                        return parsed
                except Exception:
                    pass
            logger.warning(
                f"[{agent_name}] Could not parse JSON from response (will use fallback): {response[:300]}"
            )
            raise ValueError(f"Could not parse JSON from response: {response[:200]}")


from .issue_parser import IssueParserAgent
from .relevance_agent import RelevanceAgent
from .completeness_agent import CompletenessAgent
from .validity_agent import ValidityAgent
from .search_agent import SearchAgent
from .gap_agent import GapAnalysisAgent
from .description_quality_agent import DescriptionQualityAgent
from .citation_quality_agent import CitationQualityAgent
from .response_quality_agent import ResponseQualityAgent
from .area_classification_agent import AreaClassificationAgent
from .orchestrator import Orchestrator

__all__ = [
    'LLMRefusalError',
    'BaseAgent',
    'IssueParserAgent',
    'RelevanceAgent',
    'CompletenessAgent',
    'ValidityAgent',
    'SearchAgent',
    'GapAnalysisAgent',
    'DescriptionQualityAgent',
    'CitationQualityAgent',
    'ResponseQualityAgent',
    'AreaClassificationAgent',
    'Orchestrator'
]
