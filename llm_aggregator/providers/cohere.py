"""Cohere native API client (not OpenAI-compatible)."""
import httpx
from .base import CompletionResult, EmbeddingResult
from .headers import collect_rl_headers

BASE_URL = "https://api.cohere.com/v2"


async def complete(key_data: dict, messages: list[dict], **kwargs) -> CompletionResult:
    max_tokens = kwargs.get("max_tokens", 1024)
    temperature = kwargs.get("temperature", 0.7)

    payload = {
        "model": key_data["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {key_data['api_key']}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{BASE_URL}/chat", json=payload, headers=headers)
        rl_headers = collect_rl_headers(resp.headers)
        if resp.status_code == 429:
            return CompletionResult(
                text="", tokens_used=0, was_429=True,
                error="429 rate limit", rate_limit_headers=rl_headers,
            )
        resp.raise_for_status()
        data = resp.json()
        text = data["message"]["content"][0]["text"]
        tokens = data.get("usage", {}).get("tokens", {})
        total = tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
        return CompletionResult(
            text=text, tokens_used=total, was_429=False, rate_limit_headers=rl_headers,
        )
    except httpx.HTTPStatusError as e:
        return CompletionResult(
            text="", tokens_used=0, was_429=False,
            error=f"HTTP {e.response.status_code}",
        )
    except Exception as e:
        return CompletionResult(text="", tokens_used=0, was_429=False, error=str(e)[:200])


async def embed(key_data: dict, texts: list[str], **kwargs) -> EmbeddingResult:
    payload = {
        "model": key_data["model"],
        "texts": texts,
        "input_type": kwargs.get("input_type", "search_document"),
        "embedding_types": ["float"],
    }
    headers = {
        "Authorization": f"Bearer {key_data['api_key']}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{BASE_URL}/embed", json=payload, headers=headers)
        rl_headers = collect_rl_headers(resp.headers)
        if resp.status_code == 429:
            return EmbeddingResult(
                embeddings=[], tokens_used=0, was_429=True,
                error="429 rate limit", rate_limit_headers=rl_headers,
            )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data["embeddings"]["float"]
        tokens = data.get("meta", {}).get("billed_units", {}).get("input_tokens", 0)
        return EmbeddingResult(
            embeddings=embeddings, tokens_used=tokens,
            was_429=False, rate_limit_headers=rl_headers,
        )
    except httpx.HTTPStatusError as e:
        return EmbeddingResult(
            embeddings=[], tokens_used=0, was_429=False,
            error=f"HTTP {e.response.status_code}",
        )
    except Exception as e:
        return EmbeddingResult(embeddings=[], tokens_used=0, was_429=False, error=str(e)[:200])
