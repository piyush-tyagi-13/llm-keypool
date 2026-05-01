import re
from openai import AsyncOpenAI, RateLimitError, APIStatusError
from .base import CompletionResult
from .headers import collect_rl_headers, extract_remaining_requests

_THINK_CLOSED_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
_THINK_OPEN_RE   = re.compile(r"<think>.*$", re.DOTALL)


def _strip_thinking(text: str) -> str:
    text = _THINK_CLOSED_RE.sub("", text)
    text = _THINK_OPEN_RE.sub("", text)
    return text.strip()


async def complete(key_data: dict, messages: list[dict], **kwargs) -> CompletionResult:
    strip_thinking = kwargs.pop("strip_thinking", True)
    model = kwargs.pop("model", None) or key_data["model"]
    provider = key_data.get("provider", "")
    client = AsyncOpenAI(base_url=key_data["base_url"], api_key=key_data["api_key"])
    try:
        raw = await client.chat.completions.with_raw_response.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        resp = raw.parse()
        rl_headers = collect_rl_headers(raw.headers)
        remaining = extract_remaining_requests(provider, rl_headers)
        text = resp.choices[0].message.content or ""
        if strip_thinking:
            text = _strip_thinking(text)
        return CompletionResult(
            text=text,
            tokens_used=resp.usage.total_tokens if resp.usage else 0,
            was_429=False,
            remaining_requests=remaining,
            rate_limit_headers=rl_headers,
        )
    except RateLimitError as e:
        rl_headers = {}
        if hasattr(e, "response") and e.response is not None:
            rl_headers = collect_rl_headers(e.response.headers)
        return CompletionResult(
            text="", tokens_used=0, was_429=True,
            error=str(e)[:200], rate_limit_headers=rl_headers,
        )
    except APIStatusError as e:
        return CompletionResult(
            text="", tokens_used=0, was_429=False,
            error=f"HTTP {e.status_code}: {str(e)[:160]}",
        )
    except Exception as e:
        return CompletionResult(text="", tokens_used=0, was_429=False, error=str(e)[:200])
