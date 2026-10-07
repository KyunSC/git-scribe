"""Single place that turns configuration into a chat model.

Pipeline nodes call `get_structured_model` through this module (not a direct
import) so tests can swap in a stub, and so another provider such as
`ChatAnthropic` can be added here without touching the pipeline.
"""

from __future__ import annotations

from typing import Literal, TypeVar

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ValidationError

from gitscribe.config import get_settings

ModelKind = Literal["fast", "strong"]
T = TypeVar("T", bound=BaseModel)


def model_name(kind: ModelKind) -> str:
    s = get_settings()
    return s.llm_model_fast if kind == "fast" else s.llm_model_strong


def get_chat_model(kind: ModelKind = "fast") -> BaseChatModel:
    s = get_settings()
    if s.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model_name(kind),
            base_url=s.llm_base_url,
            num_ctx=s.num_ctx,
            temperature=0,
            # Layer 1 runs once per file: never think. Layers 2-3 are configurable.
            reasoning=s.llm_think_strong if kind == "strong" else False,
        )
    raise ValueError(f"unsupported LLM_PROVIDER: {s.llm_provider!r}")


def get_structured_model(kind: ModelKind, schema: type[T]) -> Runnable:
    """A runnable that takes chat messages and returns a validated `schema` instance."""
    return get_chat_model(kind).with_structured_output(schema, method="json_schema")


def is_retryable(exc: Exception) -> bool:
    """Retry policy for LLM nodes: malformed output and transient connection errors."""
    if isinstance(exc, (ValidationError, OutputParserException)):
        return True
    try:
        import httpx

        if isinstance(exc, httpx.TransportError):
            return True
    except ImportError:
        pass
    try:
        from ollama import ResponseError

        if isinstance(exc, ResponseError):
            return exc.status_code >= 500
    except ImportError:
        pass
    return isinstance(exc, (ConnectionError, TimeoutError))
