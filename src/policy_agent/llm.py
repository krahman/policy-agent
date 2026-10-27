"""LLM factory: all models are reached through OpenRouter's OpenAI-compatible API."""

import os

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-haiku-5-5"  # OpenRouter "provider/model" slug


def get_chat_model(model: str | None = None, **kwargs) -> ChatOpenAI:
    kwargs.setdefault("temperature", 0)
    return ChatOpenAI(
        model=model or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        base_url=os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
        **kwargs,
    )
