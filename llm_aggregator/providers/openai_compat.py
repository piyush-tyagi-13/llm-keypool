import re
from openai import AsyncOpenAI, RateLimitError, APIStatusError
from .base import CompletionResult, EmbeddingResult

_THINK_CLOSED_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
_THINK_OPEN_RE   = re.compile(r"<think>.*$", re.DOTALL)


def _strip_thinking(text: str) -> str:
    text = _THINK_CLOSED_RE.sub("", text)  # complete blocks
    text = _THINK_OPEN_RE.sub("", text)    # truncated block at end
    return text.strip()


def _parse_remaining(headers) -> int | None:
    val = headers.get("x-ratelimit-remaining-requests")
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


async def complete(key_data: dict, messages: list[dict], **kwargs) -> CompletionResult:
    strip_thinking = kwargs.pop("strip_thinking", True)
    client = AsyncOpenAI(base_url=key_data["base_url"], api_key=key_data["api_key"])
    try:
        raw = await client.chat.completions.with_raw_response.create(
            model=key_data["model"],
            messages=messages,
            **kwargs,
        )
        resp = raw.parse()
        remaining = _parse_remaining(raw.headers)
        text = resp.choices[0].message.content or ""
        if strip_thinking:
            text = _strip_thinking(text)
        return CompletionResult(
            text=text,
            tokens_used=resp.usage.total_tokens if resp.usage else 0,
            was_429=False,
            remaining_requests=remaining,
        )
    except RateLimitError as e:
        return CompletionResult(text="", tokens_used=0, was_429=True, error=str(e)[:200])
    except APIStatusError as e:
        return CompletionResult(text="", tokens_used=0, was_429=False, error=f"HTTP {e.status_code}: {str(e)[:160]}")
    except Exception as e:
        return CompletionResult(text="", tokens_used=0, was_429=False, error=str(e)[:200])


async def embed(key_data: dict, texts: list[str], **kwargs) -> EmbeddingResult:
    client = AsyncOpenAI(base_url=key_data["base_url"], api_key=key_data["api_key"])
    try:
        resp = await client.embeddings.create(
            model=key_data["model"],
            input=texts,
            **kwargs,
        )
        embeddings = [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]
        tokens = resp.usage.total_tokens if resp.usage else 0
        return EmbeddingResult(embeddings=embeddings, tokens_used=tokens, was_429=False)
    except RateLimitError as e:
        return EmbeddingResult(embeddings=[], tokens_used=0, was_429=True, error=str(e)[:200])
    except Exception as e:
        return EmbeddingResult(embeddings=[], tokens_used=0, was_429=False, error=str(e)[:200])
