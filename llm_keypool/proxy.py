from __future__ import annotations
import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from llm_keypool.key_store import KeyStore
from llm_keypool.rotator import Rotator
from llm_keypool.providers.dispatch import complete


def _load_provider_configs() -> dict:
    config_path = Path(__file__).parent / "config" / "providers.json"
    with open(config_path) as f:
        return json.load(f)["providers"]


class _ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: list[dict[str, Any]]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: Optional[bool] = False


def make_app(category: str = "general_purpose", rotate_every: int = 5) -> FastAPI:
    store = KeyStore()
    configs = _load_provider_configs()
    rotator = Rotator(store, configs, rotate_every=rotate_every)

    app = FastAPI(title="llm-keypool proxy", version="1.0")

    @app.post("/v1/chat/completions")
    async def chat_completions(
        req: _ChatRequest,
        x_keypool_category: Optional[str] = Header(None),
    ):
        cat = x_keypool_category or category

        kwargs: dict[str, Any] = {}
        if req.max_tokens is not None:
            kwargs["max_tokens"] = req.max_tokens
        if req.temperature is not None:
            kwargs["temperature"] = req.temperature
        # Do not forward req.model - each key uses its own assigned model
        # so rotation across providers (groq/cerebras/mistral) works correctly.

        result, key_data = await complete(rotator, cat, req.messages, **kwargs)

        if result.error and not result.text:
            status = 429 if "exhausted" in (result.error or "") else 503
            raise HTTPException(status_code=status, detail=result.error)

        model_used = (key_data["model"] if key_data else None) or req.model or "unknown"
        resp_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        if req.stream:
            async def _stream():
                chunk = {
                    "id": resp_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model_used,
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": result.text}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                done_chunk = {
                    "id": resp_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model_used,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                yield f"data: {json.dumps(done_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(_stream(), media_type="text/event-stream")

        return {
            "id": resp_id,
            "object": "chat.completion",
            "created": created,
            "model": model_used,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": result.text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": result.tokens_used, "total_tokens": result.tokens_used},
        }

    @app.get("/v1/models")
    async def list_models():
        seen: set[str] = set()
        data = []
        for provider_name, cfg in configs.items():
            models = cfg.get("models", [])
            if isinstance(models, dict):
                models = [m for ms in models.values() for m in ms]
            default = cfg.get("default_model")
            if default and default not in models:
                models = [default] + list(models)
            for m in models:
                if m and m not in seen:
                    seen.add(m)
                    data.append({"id": m, "object": "model", "owned_by": provider_name, "created": 0})
        return {"object": "list", "data": data}

    @app.get("/health")
    async def health():
        keys = store.get_all_keys()
        active = sum(1 for k in keys if k["is_active"])
        return {"status": "ok", "keys_total": len(keys), "keys_active": active}

    return app
