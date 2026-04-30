"""
llm_factory.py — Provider-agnostic LLM factory.

Returns the right ChatModel and helpers based on config.llm_provider.
"""
from __future__ import annotations

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from config import AppConfig


def get_chat_model(cfg: AppConfig):
    """Return a LangChain ChatModel for the configured provider."""
    if cfg.llm_provider == "opencode_go":
        return ChatOpenAI(
            model=cfg.opencode_go_model,
            api_key=cfg.opencode_go_api_key,
            base_url=cfg.opencode_go_base_url,
            temperature=0,
        )

    # Default: anthropic
    return ChatAnthropic(
        model=cfg.model_name,
        api_key=cfg.anthropic_api_key,
        temperature=0,
    )


def has_llm_key(cfg: AppConfig) -> bool:
    """Check whether the configured provider has a usable API key."""
    if cfg.llm_provider == "opencode_go":
        return bool(cfg.opencode_go_api_key)
    return bool(cfg.anthropic_api_key)


def tool_choice_for(name: str, provider: str) -> dict:
    """Return the provider-specific tool_choice dict to force structured output."""
    if provider == "opencode_go":
        return {"type": "function", "function": {"name": name}}
    return {"type": "tool", "name": name}


def extract_token_usage(response: Any) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from an LLM response.

    Handles both:
      - OpenAI-compatible: response_metadata.token_usage.{prompt_tokens, completion_tokens}
      - Anthropic:         response_metadata.usage.{input_tokens, output_tokens}
    """
    meta = getattr(response, "response_metadata", {}) or {}

    # OpenAI-compatible format
    tu = meta.get("token_usage", {})
    if "prompt_tokens" in tu:
        return tu.get("prompt_tokens", 0), tu.get("completion_tokens", 0)

    # Anthropic format
    usage = meta.get("usage", {})
    return usage.get("input_tokens", 0), usage.get("output_tokens", 0)
