"""
LangChain-compatible wrapper for llm-keypool.

Drop into any LangChain pipeline as a chat model:

    from llm_keypool import AggregatorChat

    llm = AggregatorChat(
        capabilities=["general_purpose", "fast"],
        subscriber_id="mdcore.ingest",
    )

Config examples:
    # general inference
    AggregatorChat(capabilities=["general_purpose"])

    # hermes main loop - agentic models only
    AggregatorChat(capabilities=["agentic"], subscriber_id="hermes.main")

    # mdcore synthesis - fast formatter models
    AggregatorChat(capabilities=["general_purpose", "fast"], subscriber_id="mdcore.synth")

    # deprecated single-category style still works
    AggregatorChat(category="general_purpose")
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

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
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


class AggregatorChat(BaseChatModel):
    """
    LangChain ChatModel backed by llm-keypool.
    Handles key selection, rotation, 429 retries, and audit logging transparently.

    Parameters
    ----------
    capabilities : list[str]
        Key capabilities to draw from. Keys must have at least one matching
        capability. Defaults to ["general_purpose"].
        Known values: general_purpose, agentic, fast, code, vision, large_context.
    subscriber_id : str
        Identifier for this client, written to the audit log.
        Use a dotted hierarchy: "mdcore.ingest", "hermes.main", "mdcore.synth".
    max_tokens : int
        Maximum tokens to generate. Default 4096.
    temperature : float
        Sampling temperature. Default 0.7.
    rotate_every : int
        Number of requests before rotating to the next key. Default 5.
    category : str
        Deprecated. Use capabilities instead.
    """

    capabilities: list[str] = ["general_purpose"]
    subscriber_id: str = "unknown"
    max_tokens: int = 4096
    temperature: float = 0.7
    rotate_every: int = 5

    # deprecated - kept for backward compat with mdcore aggregator_category config
    category: str = ""

    _rotator: Any = None

    class Config:
        arbitrary_types_allowed = True

    def model_post_init(self, __context: Any) -> None:
        # if category passed and capabilities is still default, use category
        if self.category and self.capabilities == ["general_purpose"]:
            object.__setattr__(self, "capabilities", [self.category])

    def _get_rotator(self):
        if self._rotator is None:
            self._rotator = _build_rotator(self.rotate_every)
        return self._rotator

    @property
    def _llm_type(self) -> str:
        return "llm_keypool"

    @property
    def _identifying_params(self) -> dict:
        return {
            "model": f"keypool/{','.join(self.capabilities)}",
            "capabilities": self.capabilities,
            "subscriber_id": self.subscriber_id,
        }

    def current_key(self) -> dict | None:
        """
        Return the key that would be selected for the next request.
        Does not make any API call or mutate rotation state.
        """
        return self._get_rotator().peek_current_key(self.capabilities)

    def pool_status(self) -> list[dict]:
        """
        Return current quota state for all active keys matching capabilities.
        Does not make any API call.
        """
        from .key_store import KeyStore
        store = KeyStore()
        now = datetime.now(timezone.utc).isoformat()
        keys = store.get_active_keys(self.capabilities)
        result = []
        for k in keys:
            cd = k.get("cooldown_until")
            available = not cd or cd < now
            result.append({
                "key_id":            k["id"],
                "provider":          k["provider"],
                "model":             k["model"] or "(provider default)",
                "capabilities":      store.parse_capabilities(k),
                "requests_today":    k["requests_today"],
                "tokens_used_today": k["tokens_used_today"],
                "cooldown_until":    cd,
                "is_available":      available,
            })
        return result

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
            capabilities=self.capabilities,
            messages=msgs,
            subscriber_id=self.subscriber_id,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        if result.error:
            raise RuntimeError(f"llm-keypool error: {result.error}")

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
                "provider":           key_data["provider"],
                "model":              model_name,
                "model_name":         model_name,
                "tokens_used":        tokens,
                "requests_today":     key_data.get("requests_today", 0) + 1,
                "tokens_used_today":  key_data.get("tokens_used_today", 0) + tokens,
                "remaining_requests": result.remaining_requests,
                "key_id":             key_data["key_id"],
                "subscriber_id":      self.subscriber_id,
                "capabilities":       key_data.get("capabilities", self.capabilities),
            },
        )
        return ChatResult(
            generations=[ChatGeneration(message=ai_msg)],
            llm_output={
                "model_name": model_name,
                "provider": key_data["provider"],
                "subscriber_id": self.subscriber_id,
                "token_usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": tokens,
                    "total_tokens": tokens,
                },
            },
        )
