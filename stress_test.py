"""
Rotation stress tester. Makes real LLM calls through the keypool,
tracks which provider serves each request, and reports rotation behaviour.

Usage:
    uv run python stress_test.py [--requests N] [--rotate-every N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime

from llm_keypool.key_store import KeyStore
from llm_keypool.rotator import Rotator
from llm_keypool.providers.dispatch import complete

PROMPT = [{"role": "user", "content": "Reply in exactly 5 words."}]


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(tag: str, msg: str):
    width = 10
    print(f"[{ts()}] {tag:<{width}} {msg}")


async def run(n_requests: int, rotate_every: int):
    store = KeyStore()
    with open("llm_keypool/config/providers.json") as f:
        configs = json.load(f)["providers"]

    rotator = Rotator(store, configs, rotate_every=rotate_every)

    active = store.get_active_keys("general_purpose")
    if not active:
        print("No active general_purpose keys. Run: llm-keypool add --provider <p> --key <k>")
        return

    print(f"\nStress test: {n_requests} requests, rotate_every={rotate_every}")
    print(f"Active keys: {[k['provider'] for k in active]}")
    print("-" * 70)

    stats: dict[str, int] = defaultdict(int)
    rotations = 0
    errors = 0
    total_tokens = 0
    prev_provider = None

    for i in range(1, n_requests + 1):
        key_data = rotator.get_best_key("general_purpose")
        if key_data is None:
            earliest = rotator.get_earliest_retry("general_purpose")
            log("EXHAUSTED", f"All keys rate-limited. Earliest retry: {earliest}")
            break

        provider = key_data["provider"]
        model = key_data["model"]
        slot = f"[{key_data['cycle_position']}/{key_data['rotate_every']}]"

        if prev_provider and provider != prev_provider:
            rotations += 1
            log("ROTATE", f"{prev_provider} -> {provider}")
        prev_provider = provider

        t0 = time.monotonic()
        try:
            result, _ = await complete(
                rotator,
                category="general_purpose",
                messages=PROMPT,
                max_tokens=32,
                temperature=0.0,
            )
            elapsed = time.monotonic() - t0

            if result.error:
                errors += 1
                log("ERROR", f"req={i:3d} {provider:12}{slot} {result.error[:60]}")
            else:
                tokens = result.tokens_used or 0
                total_tokens += tokens
                stats[provider] += 1
                log("OK", f"req={i:3d} {provider:12}{slot} {elapsed:.2f}s tok={tokens:3d} | {(result.text or '')[:50]}")

        except Exception as e:
            errors += 1
            elapsed = time.monotonic() - t0
            log("EXCEPT", f"req={i:3d} {provider:12}{slot} {elapsed:.2f}s | {str(e)[:60]}")

    print("-" * 70)
    print(f"\nResults:")
    print(f"  Rotations:    {rotations}")
    print(f"  Errors:       {errors}")
    print(f"  Total tokens: {total_tokens}")
    print(f"\nRequests per provider:")
    for p, count in sorted(stats.items(), key=lambda x: -x[1]):
        bar = "█" * count
        print(f"  {p:14} {count:3d}  {bar}")

    print(f"\nFinal key state:")
    for k in store.get_all_keys():
        if k["category"] != "general_purpose":
            continue
        cd = f"cooldown until {k['cooldown_until'][:19]}" if k["cooldown_until"] else "available"
        print(f"  [{k['id']}] {k['provider']:12} req_today={k['requests_today']:4d} | {cd}")


def main():
    parser = argparse.ArgumentParser(description="llm-keypool rotation stress tester")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--rotate-every", type=int, default=3,
                        help="Requests per key before rotating (default 3)")
    args = parser.parse_args()
    asyncio.run(run(args.requests, args.rotate_every))


if __name__ == "__main__":
    main()
