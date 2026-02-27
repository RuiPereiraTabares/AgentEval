"""
LLM Adapter for Semantic Kernel integration.

Provides adapters to bridge Semantic Kernel chat completion services
with the existing agent infrastructure.
"""

from typing import Callable, Optional
import asyncio

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents import ChatHistory, ChatMessageContent, AuthorRole


class SKChatCompletionAdapter:
    """
    Adapter that bridges Semantic Kernel chat completion with the existing
    agent infrastructure's _call_claude() interface.

    This allows existing agents to use any SK-supported LLM provider
    (OpenAI, Azure OpenAI, etc.) without modifying their evaluation logic.
    """

    def __init__(
        self,
        kernel: Kernel,
        service_id: Optional[str] = None
    ):
        """
        Initialize the SK chat completion adapter.

        Args:
            kernel: Configured Semantic Kernel instance
            service_id: Optional service ID if multiple services are registered
        """
        self.kernel = kernel
        self.service_id = service_id
        self._chat_service: Optional[ChatCompletionClientBase] = None

    def _get_chat_service(self) -> ChatCompletionClientBase:
        """Get the chat completion service from the kernel."""
        if self._chat_service is None:
            if self.service_id:
                self._chat_service = self.kernel.get_service(self.service_id)
            else:
                # Get the default chat completion service
                services = self.kernel.get_services_by_type(ChatCompletionClientBase)
                if not services:
                    raise RuntimeError(
                        "No chat completion service registered with the kernel. "
                        "Add one using kernel.add_service()."
                    )
                self._chat_service = list(services.values())[0]
        return self._chat_service

    async def call_async(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 4096
    ) -> str:
        """
        Make an async call to the LLM via Semantic Kernel.

        Args:
            system_prompt: The system prompt
            user_message: The user message
            temperature: Temperature for generation
            max_tokens: Maximum tokens in response

        Returns:
            LLM response text
        """
        chat_service = self._get_chat_service()

        # Build chat history with system and user messages
        chat_history = ChatHistory()
        chat_history.add_system_message(system_prompt)
        chat_history.add_user_message(user_message)

        # Configure execution settings
        from semantic_kernel.connectors.ai.prompt_execution_settings import PromptExecutionSettings
        settings = PromptExecutionSettings(
            temperature=temperature,
            max_tokens=max_tokens
        )

        # Get completion
        response = await chat_service.get_chat_message_content(
            chat_history=chat_history,
            settings=settings,
            kernel=self.kernel
        )

        return response.content if response else ""

    def call(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 4096
    ) -> str:
        """
        Synchronous wrapper for call_async.

        Args:
            system_prompt: The system prompt
            user_message: The user message
            temperature: Temperature for generation
            max_tokens: Maximum tokens in response

        Returns:
            LLM response text
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.call_async(system_prompt, user_message, temperature, max_tokens)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.call_async(system_prompt, user_message, temperature, max_tokens)
                )
        except RuntimeError:
            # No event loop exists
            return asyncio.run(
                self.call_async(system_prompt, user_message, temperature, max_tokens)
            )

    def get_callable(self) -> Callable[[str, str], str]:
        """
        Return a callable that matches the _call_claude signature.

        Returns:
            Callable that takes (system_prompt, user_message) and returns response
        """
        return self.call


class SKAgentWrapper:
    """
    Wraps existing agents to use Semantic Kernel services.

    This wrapper injects an SK-based LLM callable into agents,
    allowing them to use any SK-supported provider while maintaining
    their existing evaluation logic.
    """

    def __init__(
        self,
        agent,
        kernel: Kernel,
        service_id: Optional[str] = None
    ):
        """
        Initialize the SK agent wrapper.

        Args:
            agent: An instance of a BaseAgent subclass
            kernel: Configured Semantic Kernel instance
            service_id: Optional service ID for the chat completion service
        """
        self.agent = agent
        self.adapter = SKChatCompletionAdapter(kernel, service_id)

        # Inject the SK-based callable into the agent
        if hasattr(self.agent, 'set_llm_callable'):
            self.agent.set_llm_callable(self.adapter.get_callable())
        else:
            # Fallback: monkey-patch _call_claude
            self.agent._call_claude = self._sk_call_claude

    def _sk_call_claude(self, system_prompt: str, user_message: str) -> str:
        """Replacement for agent's _call_claude using SK."""
        return self.adapter.call(system_prompt, user_message)

    def evaluate(self, *args, **kwargs):
        """Delegate evaluation to the wrapped agent."""
        return self.agent.evaluate(*args, **kwargs)

    def __getattr__(self, name):
        """Delegate attribute access to the wrapped agent."""
        return getattr(self.agent, name)


def create_openai_kernel(
    api_key: str,
    model: str = "gpt-4o",
    service_id: str = "default"
) -> Kernel:
    """
    Create a Semantic Kernel configured with OpenAI.

    Args:
        api_key: OpenAI API key
        model: Model name (e.g., "gpt-4o", "gpt-4-turbo")
        service_id: Service identifier

    Returns:
        Configured Kernel instance
    """
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

    kernel = Kernel()
    service = OpenAIChatCompletion(
        ai_model_id=model,
        api_key=api_key,
        service_id=service_id
    )
    kernel.add_service(service)
    return kernel


def create_azure_openai_kernel(
    api_key: str,
    endpoint: str,
    deployment_name: str,
    api_version: str = "2024-02-15-preview",
    service_id: str = "default"
) -> Kernel:
    """
    Create a Semantic Kernel configured with Azure OpenAI.

    Args:
        api_key: Azure OpenAI API key
        endpoint: Azure OpenAI endpoint URL
        deployment_name: Deployment name (model deployment)
        api_version: Azure OpenAI API version
        service_id: Service identifier

    Returns:
        Configured Kernel instance
    """
    from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

    kernel = Kernel()
    service = AzureChatCompletion(
        deployment_name=deployment_name,
        endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        service_id=service_id
    )
    kernel.add_service(service)
    return kernel


def create_anthropic_kernel(
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    service_id: str = "default",
    base_url: Optional[str] = None
) -> Kernel:
    """
    Create a Semantic Kernel configured with Anthropic/Claude.

    Args:
        api_key: Anthropic API key
        model: Claude model name (e.g., "claude-sonnet-4-20250514", "claude-3-opus-20240229")
        service_id: Service identifier
        base_url: Optional custom base URL for the API

    Returns:
        Configured Kernel instance
    """
    from .anthropic_connector import AnthropicChatCompletion

    kernel = Kernel()
    service = AnthropicChatCompletion(
        ai_model_id=model,
        api_key=api_key,
        service_id=service_id,
        base_url=base_url
    )
    kernel.add_service(service)
    return kernel
