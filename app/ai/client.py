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
        # Build a clean, simplified key list instead of passing raw JSON Schema,
        # which confuses open-source models like Llama 3.1.
        props = response_model.model_json_schema().get("properties", {})
        key_instructions = []
        for k, v in props.items():
            p_type = v.get("type", "string")
            p_desc = v.get("description", "")
            key_instructions.append(f"- {k}: {p_type} ({p_desc})")
            
        key_list_str = "\n".join(key_instructions)
        instruction = (
            f"\n\nYou MUST respond with a single valid JSON object containing these keys:\n"
            f"{key_list_str}\n\n"
            f"Do NOT output the schema itself. Return ONLY the JSON object. Do not wrap in a list."
        )
        
        fallback_messages = list(messages)
        if fallback_messages:
            last_msg = fallback_messages[-1]
            fallback_messages[-1] = {
                "role": last_msg["role"],
                "content": last_msg["content"] + instruction
            }

        content = self.chat_completion(fallback_messages, temperature=temperature, json_mode=True)
        
        # Clean markdown code block wraps if returned by the LLM
        cleaned_content = content.strip()
        if cleaned_content.startswith("```"):
            lines = cleaned_content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_content = "\n".join(lines).strip()
            
        try:
            data = json.loads(cleaned_content)
            
            # Handle list-wrap output quirk
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "match_score" in item:
                        data = item
                        break
                        
            return response_model.model_validate(data)
        except Exception as parse_err:
            logger.error("Failed to parse fallback JSON response: %s. Content: %r", parse_err, content)
            raise RuntimeError(f"AI parsing error: {parse_err}") from parse_err


# Global client instance
ai_client = AIClient()
