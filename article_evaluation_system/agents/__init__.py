"""
Agent modules for the article evaluation system.
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

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1)
            logger.debug(f"[{agent_name}] Extracted JSON from markdown code block")
        else:
            json_str = response
            logger.debug(f"[{agent_name}] No markdown code block found, using raw response")

        try:
            parsed = json.loads(json_str)
            logger.info(f"[{agent_name}] JSON parsed successfully. Keys: {list(parsed.keys())}")
            logger.debug(f"[{agent_name}] Full parsed JSON: {json.dumps(parsed, indent=2)[:2000]}")
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"[{agent_name}] First JSON parse attempt failed: {e}")
            # Try to find JSON object in the response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    logger.info(
                        f"[{agent_name}] JSON extracted via regex fallback. Keys: {list(parsed.keys())}"
                    )
                    return parsed
                except json.JSONDecodeError as e2:
                    logger.warning(
                        f"[{agent_name}] Regex fallback also failed: {e2}"
                    )
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
    'Orchestrator'
]
