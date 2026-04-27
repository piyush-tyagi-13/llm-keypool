"""
LangChain-compatible wrappers for the LLM Aggregator.

Drop into mdcore's llm_layer.py as a new backend:

    from llm_aggregator.langchain_wrapper import AggregatorChat, AggregatorEmbeddings

    # in _build_llm():
    elif backend == "llm_aggregator":
        return AggregatorChat()

    # in _build_embeddings():
    elif backend == "llm_aggregator":
        return AggregatorEmbeddings()

Config (~/.mdcore/config.yaml):
    llm:
      backend: llm_aggregator
    embeddings:
      backend: llm_aggregator
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Iterator, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

_CONFIG_PATH = Path(__file__).parent / "config" / "providers.json"


def _build_rotator(rotate_every: int = 5):
    from .key_store import KeyStore
    from .rotator import Rotator
    with open(_CONFIG_PATH) as f:
        configs = json.load(f)["providers"]
    return Rotator(KeyStore(), configs, rotate_every=rotate_every)


def _msgs_to_dicts(messages: list[BaseMessage]) -> list[dict]:
    role_map = {
        "human": "user",
        "ai": "assistant",
        "system": "system",
        "chat": "user",
    }
    result = []
    for m in messages:
        role = role_map.get(m.type, "user")
        result.append({"role": role, "content": m.content})
    return result


def _run_async(coro):
    """Run async coroutine from sync context safely."""
    try:
        loop = asyncio.get_running_loop()
        # already inside an event loop - use a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


class AggregatorChat(BaseChatModel):
    """
    LangChain ChatModel backed by the LLM Aggregator.
    Handles key selection, rotation, and 429 retries transparently.
    """

    category: str = "general_purpose"
    max_tokens: int = 4096
    temperature: float = 0.7
    rotate_every: int = 5

    # private - not part of Pydantic model
    _rotator: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _get_rotator(self):
        if self._rotator is None:
            self._rotator = _build_rotator(self.rotate_every)
        return self._rotator

    @property
    def _llm_type(self) -> str:
        return "llm_aggregator"

    @property
    def _identifying_params(self) -> dict:
        return {"model": f"aggregator/{self.category}", "category": self.category}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager=None,
        **kwargs,
    ) -> ChatResult:
        return _run_async(self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs))

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager=None,
        **kwargs,
    ) -> ChatResult:
        from .providers.dispatch import complete as _complete

        msgs = _msgs_to_dicts(messages)
        result, key_data = await _complete(
            self._get_rotator(),
            category=self.category,
            messages=msgs,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        if result.error:
            raise RuntimeError(f"LLM Aggregator error: {result.error}")

        model_name = key_data["model"] or key_data["provider"]
        tokens = result.tokens_used or 0

        ai_msg = AIMessage(
            content=result.text,
            usage_metadata={
                "input_tokens": 0,
                "output_tokens": tokens,
                "total_tokens": tokens,
            },
            response_metadata={
                "provider": key_data["provider"],
                "model": model_name,
                "model_name": model_name,
                "tokens_used": tokens,
            },
        )
        return ChatResult(
            generations=[ChatGeneration(message=ai_msg)],
            llm_output={
                "model_name": model_name,
                "provider": key_data["provider"],
                "token_usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": tokens,
                    "total_tokens": tokens,
                },
            },
        )


class AggregatorEmbeddings(Embeddings):
    """
    LangChain Embeddings backed by the LLM Aggregator.
    Handles key selection, rotation, and 429 retries transparently.
    """

    category: str = "embedding"
    rotate_every: int = 5

    _rotator: Any = None

    def __init__(self, **kwargs):
        self.category = kwargs.get("category", "embedding")
        self.rotate_every = kwargs.get("rotate_every", 5)
        self._rotator = None

    def _get_rotator(self):
        if self._rotator is None:
            self._rotator = _build_rotator(self.rotate_every)
        return self._rotator

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return _run_async(self._aembed(texts))

    def embed_query(self, text: str) -> list[float]:
        results = _run_async(self._aembed([text]))
        return results[0]

    async def _aembed(self, texts: list[str]) -> list[list[float]]:
        from .providers.dispatch import embed as _embed

        result, key_data = await _embed(
            self._get_rotator(),
            category=self.category,
            texts=texts,
        )

        if result.error:
            raise RuntimeError(f"LLM Aggregator embed error: {result.error}")

        return result.embeddings
