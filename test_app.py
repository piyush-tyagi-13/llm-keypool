"""
LLM aggregator stress tester.

Hammers the MCP server with get_key -> LLM call -> report_usage in a tight loop.
Intentionally exceeds rate limits to verify key rotation behaviour.

Usage:
    python test_app.py [--requests N] [--category CATEGORY] [--prompt TEXT]
"""

import argparse
import asyncio
import json
import time
from datetime import datetime

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI, RateLimitError, APIError

SERVER = StdioServerParameters(command=".venv/bin/python", args=["server.py"])
PROMPT = "Reply in exactly one sentence: what is 2+2 and why?"


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(tag: str, msg: str):
    print(f"[{ts()}] {tag:12} {msg}")


async def call_llm(base_url: str, api_key: str, model: str, prompt: str) -> tuple[int, bool, str]:
    """Returns (tokens_used, was_429, error_msg)."""
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=64,
        )
        tokens = resp.usage.total_tokens if resp.usage else 0
        content = resp.choices[0].message.content or ""
        return tokens, False, content[:80]
    except RateLimitError as e:
        return 0, True, str(e)[:120]
    except APIError as e:
        return 0, False, f"APIError {e.status_code}: {str(e)[:80]}"
    except Exception as e:
        return 0, False, f"Error: {str(e)[:80]}"


async def run(n_requests: int, category: str, prompt: str):
    async with stdio_client(SERVER) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            log("INIT", f"MCP connected. Sending {n_requests} requests, category={category}")
            print("-" * 72)

            success = failed = rotations = exhausted_waits = 0
            prev_provider = None

            for i in range(1, n_requests + 1):
                # --- get key ---
                res = await session.call_tool("get_key", {"category": category})
                key_data = json.loads(res.content[0].text)

                if "error" in key_data:
                    if key_data["error"] == "all_keys_exhausted":
                        retry = key_data.get("retry_after", "unknown")
                        log("EXHAUSTED", f"All keys rate-limited. Retry after: {retry}")
                        exhausted_waits += 1
                        break
                    log("ERROR", f"get_key failed: {key_data}")
                    break

                provider = key_data["provider"]
                model    = key_data["model"]
                key_id   = key_data["key_id"]

                cycle_pos   = key_data.get("cycle_position", "?")
                rotate_every = key_data.get("rotate_every", 0)

                if prev_provider and provider != prev_provider:
                    rotations += 1
                    log("ROTATE", f"{prev_provider} -> {provider}")
                prev_provider = provider

                # --- call LLM ---
                t0 = time.monotonic()
                tokens, was_429, detail = await call_llm(
                    key_data["base_url"], key_data["api_key"], model, prompt
                )
                elapsed = time.monotonic() - t0

                # --- report usage ---
                await session.call_tool("report_usage", {
                    "key_id": key_id,
                    "tokens_used": tokens,
                    "was_429": was_429,
                })

                slot = f"[{cycle_pos}/{rotate_every}]" if rotate_every else ""
                if was_429:
                    failed += 1
                    log("429", f"req={i:3d} {provider}{slot} -> cooled down")
                else:
                    success += 1
                    log("OK", f"req={i:3d} {provider:12}{slot} tok={tokens:4d} {elapsed:.2f}s | {detail}")

            print("-" * 72)
            # --- final status ---
            res = await session.call_tool("list_keys", {})
            keys = json.loads(res.content[0].text)["keys"]
            print(f"\nResults: {success} ok / {failed} 429s / {rotations} rotations / {exhausted_waits} full-exhaustion stops")
            print("\nKey status:")
            for k in keys:
                cd = f"cooldown until {k['cooldown_until']}" if k["in_cooldown"] else "available"
                print(f"  [{k['id']}] {k['provider']:12} model={k['model']:40} req_today={k['requests_today']:4d} | {cd}")


def main():
    parser = argparse.ArgumentParser(description="LLM aggregator stress tester")
    parser.add_argument("--requests", type=int, default=20, help="Number of requests to send (default 20)")
    parser.add_argument("--category", default="general_purpose", choices=["general_purpose", "embedding"])
    parser.add_argument("--prompt", default=PROMPT)
    args = parser.parse_args()
    asyncio.run(run(args.requests, args.category, args.prompt))


if __name__ == "__main__":
    main()
