"""
Anthropic/Claude connector for Semantic Kernel.

Provides a ChatCompletionClientBase implementation that uses the Anthropic API,
enabling Claude models to be used with Semantic Kernel.
"""

import asyncio
from typing import Any, Optional, List

from anthropic import Anthropic, AsyncAnthropic

from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.connectors.ai.prompt_execution_settings import PromptExecutionSettings
from semantic_kernel.contents import ChatHistory, ChatMessageContent, AuthorRole


class AnthropicChatCompletionSettings(PromptExecutionSettings):
    """Execution settings specific to Anthropic/Claude."""

    max_tokens: int = 4096
    temperature: float = 0.1
    top_p: Optional[float] = None
    top_k: Optional[int] = None


class AnthropicChatCompletion(ChatCompletionClientBase):
    """
    Semantic Kernel chat completion service for Anthropic/Claude.

    This connector allows Claude models to be used with Semantic Kernel,
    implementing the ChatCompletionClientBase interface.

    Usage:
        from semantic_kernel import Kernel
        from article_evaluation_system.sk.anthropic_connector import AnthropicChatCompletion

        kernel = Kernel()
        service = AnthropicChatCompletion(
            ai_model_id="claude-sonnet-4-20250514",
            api_key="your-anthropic-key"
        )
        kernel.add_service(service)
    """

    def __init__(
        self,
        ai_model_id: str = "claude-sonnet-4-20250514",
        api_key: Optional[str] = None,
        service_id: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        Initialize the Anthropic chat completion service.

        Args:
            ai_model_id: The Claude model to use (e.g., "claude-sonnet-4-20250514", "claude-3-opus-20240229")
            api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
            service_id: Service identifier for the kernel
            base_url: Optional custom base URL for the API
        """
        super().__init__(
            ai_model_id=ai_model_id,
            service_id=service_id or "anthropic"
        )

        # Get API key from parameter or environment
        if api_key is None:
            import os
            api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not api_key:
            raise ValueError(
                "Anthropic API key required. Set api_key parameter or "
                "ANTHROPIC_API_KEY environment variable."
            )

        # Initialize clients
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self._client = Anthropic(**client_kwargs)
        self._async_client = AsyncAnthropic(**client_kwargs)
        self._model_id = ai_model_id

    def get_prompt_execution_settings_class(self) -> type[PromptExecutionSettings]:
        """Return the settings class for this service."""
        return AnthropicChatCompletionSettings

    def _convert_chat_history(self, chat_history: ChatHistory) -> tuple[str, list[dict]]:
        """
        Convert SK ChatHistory to Anthropic format.

        Returns:
            Tuple of (system_prompt, messages_list)
        """
        system_prompt = ""
        messages = []

        for message in chat_history.messages:
            if message.role == AuthorRole.SYSTEM:
                system_prompt = message.content
            elif message.role == AuthorRole.USER:
                messages.append({
                    "role": "user",
                    "content": message.content
                })
            elif message.role == AuthorRole.ASSISTANT:
                messages.append({
                    "role": "assistant",
                    "content": message.content
                })

        return system_prompt, messages

    async def get_chat_message_content(
        self,
        chat_history: ChatHistory,
        settings: Optional[PromptExecutionSettings] = None,
        **kwargs: Any
    ) -> ChatMessageContent:
        """
        Get a chat message content response from Claude.

        Args:
            chat_history: The chat history to send
            settings: Execution settings
            **kwargs: Additional arguments (including kernel)

        Returns:
            ChatMessageContent with the response
        """
        # Use default settings if none provided
        if settings is None:
            settings = AnthropicChatCompletionSettings()

        # Convert chat history to Anthropic format
        system_prompt, messages = self._convert_chat_history(chat_history)

        # Ensure we have at least one message
        if not messages:
            messages = [{"role": "user", "content": "Hello"}]

        # Build request parameters
        request_params = {
            "model": self._model_id,
            "messages": messages,
            "max_tokens": getattr(settings, 'max_tokens', 4096),
        }

        # Add system prompt if present
        if system_prompt:
            request_params["system"] = system_prompt

        # Add optional parameters
        if hasattr(settings, 'temperature') and settings.temperature is not None:
            request_params["temperature"] = settings.temperature
        if hasattr(settings, 'top_p') and settings.top_p is not None:
            request_params["top_p"] = settings.top_p
        if hasattr(settings, 'top_k') and settings.top_k is not None:
            request_params["top_k"] = settings.top_k

        # Make API call
        response = await self._async_client.messages.create(**request_params)

        # Extract response content
        content = ""
        if response.content:
            content = response.content[0].text

        return ChatMessageContent(
            role=AuthorRole.ASSISTANT,
            content=content,
            ai_model_id=self._model_id
        )

    async def get_chat_message_contents(
        self,
        chat_history: ChatHistory,
        settings: Optional[PromptExecutionSettings] = None,
        **kwargs: Any
    ) -> List[ChatMessageContent]:
        """
        Get chat message contents (returns list with single response).

        Args:
            chat_history: The chat history to send
            settings: Execution settings
            **kwargs: Additional arguments

        Returns:
            List containing single ChatMessageContent
        """
        result = await self.get_chat_message_content(chat_history, settings, **kwargs)
        return [result]

    async def get_streaming_chat_message_content(
        self,
        chat_history: ChatHistory,
        settings: Optional[PromptExecutionSettings] = None,
        **kwargs: Any
    ):
        """
        Stream chat message content from Claude.

        Args:
            chat_history: The chat history to send
            settings: Execution settings
            **kwargs: Additional arguments

        Yields:
            ChatMessageContent chunks
        """
        # Use default settings if none provided
        if settings is None:
            settings = AnthropicChatCompletionSettings()

        # Convert chat history to Anthropic format
        system_prompt, messages = self._convert_chat_history(chat_history)

        if not messages:
            messages = [{"role": "user", "content": "Hello"}]

        # Build request parameters
        request_params = {
            "model": self._model_id,
            "messages": messages,
            "max_tokens": getattr(settings, 'max_tokens', 4096),
        }

        if system_prompt:
            request_params["system"] = system_prompt

        if hasattr(settings, 'temperature') and settings.temperature is not None:
            request_params["temperature"] = settings.temperature

        # Stream response
        async with self._async_client.messages.stream(**request_params) as stream:
            async for text in stream.text_stream:
                yield ChatMessageContent(
                    role=AuthorRole.ASSISTANT,
                    content=text,
                    ai_model_id=self._model_id
                )

    async def get_streaming_chat_message_contents(
        self,
        chat_history: ChatHistory,
        settings: Optional[PromptExecutionSettings] = None,
        **kwargs: Any
    ):
        """
        Stream chat message contents.

        Args:
            chat_history: The chat history to send
            settings: Execution settings
            **kwargs: Additional arguments

        Yields:
            Lists containing ChatMessageContent chunks
        """
        async for chunk in self.get_streaming_chat_message_content(
            chat_history, settings, **kwargs
        ):
            yield [chunk]

    def get_chat_message_content_sync(
        self,
        chat_history: ChatHistory,
        settings: Optional[PromptExecutionSettings] = None,
        **kwargs: Any
    ) -> ChatMessageContent:
        """
        Synchronous version of get_chat_message_content.

        Args:
            chat_history: The chat history to send
            settings: Execution settings
            **kwargs: Additional arguments

        Returns:
            ChatMessageContent with the response
        """
        # Use default settings if none provided
        if settings is None:
            settings = AnthropicChatCompletionSettings()

        # Convert chat history
        system_prompt, messages = self._convert_chat_history(chat_history)

        if not messages:
            messages = [{"role": "user", "content": "Hello"}]

        # Build request parameters
        request_params = {
            "model": self._model_id,
            "messages": messages,
            "max_tokens": getattr(settings, 'max_tokens', 4096),
        }

        if system_prompt:
            request_params["system"] = system_prompt

        if hasattr(settings, 'temperature') and settings.temperature is not None:
            request_params["temperature"] = settings.temperature

        # Make synchronous API call
        response = self._client.messages.create(**request_params)

        content = ""
        if response.content:
            content = response.content[0].text

        return ChatMessageContent(
            role=AuthorRole.ASSISTANT,
            content=content,
            ai_model_id=self._model_id
        )
