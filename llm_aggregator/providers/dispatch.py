from .base import CompletionResult, EmbeddingResult
from . import openai_compat, cohere as _cohere, cloudflare as _cloudflare

MAX_RETRY_ATTEMPTS = 10


async def complete(
    rotator,
    category: str = "general_purpose",
    messages: list[dict] = None,
    **kwargs,
) -> tuple[CompletionResult, dict | None]:
    """
    Select best key, call provider, auto-rotate on 429.
    Returns (CompletionResult, key_data_used) — key_data is None if exhausted.
    """
    messages = messages or []
    for _ in range(MAX_RETRY_ATTEMPTS):
        key_data = rotator.get_best_key(category)
        if not key_data:
            return CompletionResult(text="", tokens_used=0, was_429=False, error="all_keys_exhausted"), None

        result = await _call_complete(key_data, messages, **kwargs)

        if result.was_429:
            rotator.handle_429(key_data["key_id"], key_data["provider"], result.rate_limit_headers)
            continue

        rotator.handle_success(
            key_data["key_id"], result.tokens_used,
            result.rate_limit_headers, key_data["provider"],
        )
        return result, key_data

    return CompletionResult(text="", tokens_used=0, was_429=False, error="max_retries_exceeded"), None


async def embed(
    rotator,
    category: str = "embedding",
    texts: list[str] = None,
    **kwargs,
) -> tuple[EmbeddingResult, dict | None]:
    texts = texts or []
    for _ in range(MAX_RETRY_ATTEMPTS):
        key_data = rotator.get_best_key(category)
        if not key_data:
            return EmbeddingResult(embeddings=[], tokens_used=0, was_429=False, error="all_keys_exhausted"), None

        result = await _call_embed(key_data, texts, **kwargs)

        if result.was_429:
            rotator.handle_429(key_data["key_id"], key_data["provider"], result.rate_limit_headers)
            continue

        rotator.handle_success(
            key_data["key_id"], result.tokens_used,
            result.rate_limit_headers, key_data["provider"],
        )
        return result, key_data

    return EmbeddingResult(embeddings=[], tokens_used=0, was_429=False, error="max_retries_exceeded"), None


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


async def _call_embed(key_data: dict, texts: list[str], **kwargs) -> EmbeddingResult:
    if key_data["openai_compatible"]:
        return await openai_compat.embed(key_data, texts, **kwargs)
    if key_data["provider"] == "cohere":
        return await _cohere.embed(key_data, texts, **kwargs)
    if key_data["provider"] == "cloudflare":
        return await _cloudflare.embed(key_data, texts, **kwargs)
    return EmbeddingResult(
        embeddings=[], tokens_used=0, was_429=False,
        error=f"no client for provider '{key_data['provider']}'",
    )
