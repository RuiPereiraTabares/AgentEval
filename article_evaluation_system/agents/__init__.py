"""
Agent modules for the Agentic Insight Engine.
"""

from abc import ABC, abstractmethod
import json
import logging
import re

logger = logging.getLogger(__name__)


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
        Make a call to the MWAI LLM API.

        Args:
            system_prompt: The system prompt
            user_message: The user message

        Returns:
            LLM response text
        """
        agent_name = self.__class__.__name__
        logger.info(f"[{agent_name}] Calling LLM (provider={self.provider}, model={self.model})")
        logger.debug(
            f"[{agent_name}] System prompt (first 200 chars): {system_prompt[:200]}"
        )
        logger.debug(
            f"[{agent_name}] User message (first 500 chars): {user_message[:500]}"
        )

        # Use injected callable if available
        if self._llm_callable is not None:
            response = self._llm_callable(system_prompt, user_message)
            logger.info(f"[{agent_name}] Got response via injected callable ({len(response)} chars)")
            logger.debug(f"[{agent_name}] Raw response (first 500 chars): {response[:500]}")
            return response

        # MWAI ChatCompletionWithoutData API
        response = self.client.chat_completion(system_prompt, user_message)
        logger.info(f"[{agent_name}] Got MWAI response ({len(response)} chars)")
        logger.debug(f"[{agent_name}] Raw response (first 500 chars): {response[:500]}")
        return response

    def _parse_json_response(self, response: str) -> dict:
        """
        Parse JSON from LLM response, handling markdown code blocks.

        Args:
            response: LLM response text

        Returns:
            Parsed JSON dictionary
        """
        agent_name = self.__class__.__name__

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
