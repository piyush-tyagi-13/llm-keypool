"""Cloudflare Workers AI client."""
import httpx
from .base import CompletionResult, EmbeddingResult


async def complete(key_data: dict, messages: list[dict], **kwargs) -> CompletionResult:
    account_id = key_data.get("extra_params", {}).get("account_id", "")
    model = key_data["model"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {key_data['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": messages,
        "max_tokens": kwargs.get("max_tokens", 1024),
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 429:
            return CompletionResult(text="", tokens_used=0, was_429=True, error="429 rate limit")
        resp.raise_for_status()
        data = resp.json()
        text = data.get("result", {}).get("response", "")
        return CompletionResult(text=text, tokens_used=0, was_429=False)
    except httpx.HTTPStatusError as e:
        return CompletionResult(text="", tokens_used=0, was_429=False, error=f"HTTP {e.response.status_code}")
    except Exception as e:
        return CompletionResult(text="", tokens_used=0, was_429=False, error=str(e)[:200])


async def embed(key_data: dict, texts: list[str], **kwargs) -> EmbeddingResult:
    account_id = key_data.get("extra_params", {}).get("account_id", "")
    model = key_data["model"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {key_data['api_key']}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json={"text": texts}, headers=headers)
        if resp.status_code == 429:
            return EmbeddingResult(embeddings=[], tokens_used=0, was_429=True, error="429 rate limit")
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("result", {}).get("data", [])
        return EmbeddingResult(embeddings=embeddings, tokens_used=0, was_429=False)
    except httpx.HTTPStatusError as e:
        return EmbeddingResult(embeddings=[], tokens_used=0, was_429=False, error=f"HTTP {e.response.status_code}")
    except Exception as e:
        return EmbeddingResult(embeddings=[], tokens_used=0, was_429=False, error=str(e)[:200])
