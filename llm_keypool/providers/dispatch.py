import time
from .base import CompletionResult
from . import openai_compat, cohere as _cohere, cloudflare as _cloudflare

MAX_RETRY_ATTEMPTS = 10


async def complete(
    rotator,
    capabilities: list[str] | None = None,
    messages: list[dict] = None,
    subscriber_id: str = "unknown",
    # deprecated - kept for backward compat
    category: str | None = None,
    **kwargs,
) -> tuple[CompletionResult, dict | None]:
    """
    Select best key, call provider, auto-rotate on 429.
    Returns (CompletionResult, key_data_used) - key_data is None if exhausted.
    """
    if capabilities is None:
        capabilities = [category] if category else ["general_purpose"]
    messages = messages or []

    for _ in range(MAX_RETRY_ATTEMPTS):
        key_data = rotator.get_best_key(capabilities, subscriber_id=subscriber_id)
        if not key_data:
            return CompletionResult(text="", tokens_used=0, was_429=False, error="all_keys_exhausted"), None

        t0 = time.monotonic()
        result = await _call_complete(key_data, messages, **kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)

        if result.was_429:
            rotator.handle_429(
                key_data["key_id"],
                key_data["provider"],
                result.rate_limit_headers,
                subscriber_id=subscriber_id,
                model=key_data.get("model", ""),
            )
            continue

        # estimate tokens_in from message content length (rough heuristic; real count unavailable pre-call)
        tokens_in = sum(len(m.get("content", "")) // 4 for m in messages)

        rotator.handle_success(
            key_data["key_id"],
            result.tokens_used,
            result.rate_limit_headers,
            key_data["provider"],
            tokens_in=tokens_in,
            latency_ms=latency_ms,
            subscriber_id=subscriber_id,
            model=key_data.get("model", ""),
        )
        return result, key_data

    return CompletionResult(text="", tokens_used=0, was_429=False, error="max_retries_exceeded"), None


async def _call_complete(key_data: dict, messages: list[dict], **kwargs) -> CompletionResult:
    if key_data["openai_compatible"]:
        return await openai_compat.complete(key_data, messages, **kwargs)
    if key_data["provider"] == "cohere":
        return await _cohere.complete(key_data, messages, **kwargs)
    if key_data["provider"] == "cloudflare":
        return await _cloudflare.complete(key_data, messages, **kwargs)
    return CompletionResult(
        text="", tokens_used=0, was_429=False,
        error=f"no client for provider '{key_data['provider']}'",
    )
