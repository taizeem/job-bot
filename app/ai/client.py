"""
AI client wrapper for OpenAI-compatible APIs.

Handles communication with LLM providers (OpenAI, Groq, Together, Ollama, etc.)
using settings from the configuration. Supports standard completions, JSON mode,
and error handling.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Type

from openai import OpenAI
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)


class AIClient:
    """Client for interacting with OpenAI-compatible APIs."""

    def __init__(self) -> None:
        self.api_key = settings.ai_api_key
        self.base_url = settings.ai_base_url
        self.model = settings.ai_model
        
        # Initialize OpenAI client
        # If api_key is empty or placeholder, we will log a warning
        if not self.api_key or self.api_key.startswith("sk-..."):
            logger.warning("AI_API_KEY is not configured or is a placeholder. AI features may fail.")
            
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Get a chat completion from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            json_mode: Whether to force JSON output format.

        Returns:
            The generated text response.
        """
        try:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            return content or ""
        except Exception as e:
            logger.error("AI chat completion failed: %s", e)
            raise RuntimeError(f"AI Completion Error: {e}") from e

    def structured_output(
        self,
        messages: list[dict[str, str]],
        response_model: Type[BaseModel],
        temperature: float = 0.1,
    ) -> BaseModel:
        """Fetch completions and parse into a Pydantic model.

        Tries to use OpenAI's beta.chat.completions.parse API first.
        If it fails (e.g. provider doesn't support structured output), it falls
        back to standard completion with json_mode and parses manually.
        """
        try:
            # Attempt official beta parse API (if supported by provider)
            response = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=response_model,
                temperature=temperature,
            )
            parsed = response.choices[0].message.parsed
            if parsed is not None:
                return parsed
        except Exception as e:
            logger.warning(
                "Structured output parse failed or unsupported. Falling back to JSON mode: %s",
                e,
            )

        # Fallback: JSON mode with manual parsing
        # Append instruction to system message or last message to output valid JSON matching the schema
        schema_json = json.dumps(response_model.model_json_schema())
        fallback_messages = list(messages)
        
        # Modify the last user message or append a system instruction
        instruction = f"\n\nYou MUST respond with valid JSON matching this schema: {schema_json}"
        if fallback_messages:
            last_msg = fallback_messages[-1]
            fallback_messages[-1] = {
                "role": last_msg["role"],
                "content": last_msg["content"] + instruction
            }

        content = self.chat_completion(fallback_messages, temperature=temperature, json_mode=True)
        try:
            data = json.loads(content)
            return response_model.model_validate(data)
        except Exception as parse_err:
            logger.error("Failed to parse fallback JSON response: %s. Content: %r", parse_err, content)
            raise RuntimeError(f"AI parsing error: {parse_err}") from parse_err


# Global client instance
ai_client = AIClient()
