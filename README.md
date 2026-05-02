# llm-keypool

Free-tier LLM key pool manager. Register API keys from multiple providers once - llm-keypool round-robins across them, handles 429 cooldowns, and retries transparently. No paid API needed.

Exposes a CLI, a Textual TUI, a LangChain drop-in (`AggregatorChat`), and a local OpenAI-compatible proxy server so any agent or tool that speaks the OpenAI API can use the key pool with zero code changes.

Works as a free drop-in backend for [Hermes Agent](https://github.com/nousresearch/hermes-agent) - run the proxy, point Hermes at it, and your free-tier keys handle all LLM calls including delegated sub-agents, with no paid API subscription required. See [docs/hermes-agent.md](docs/hermes-agent.md).

---

## Screenshots

![Keys tab](docs/screenshots/home.jpg)

![Add Key tab](docs/screenshots/add_key.jpg)

---

## What it does

- **Multi-provider pooling** - pool keys across Groq, Cerebras, Mistral, OpenRouter, SambaNova, Google, and more
- **Capabilities tagging** - tag keys with multiple capabilities (`agentic`, `fast`, `general_purpose`, `code`, `vision`, `large_context`); each proxy instance filters by the capabilities it serves
- **Automatic rotation** - round-robin across keys, rotates every N requests (default: 5)
- **429 handling** - on rate limit, key enters cooldown; next call retries a different key automatically
- **Two-tier proxy** - run separate proxy instances for agentic vs. fast general-purpose traffic; Hermes main loop uses :8000 (agentic), delegate calls use :8001 (fast)
- **Audit log** - every LLM call logged with subscriber ID, provider, model, token counts, latency; query with `llm-keypool audit`
- **Subscriber tracking** - pass `X-Subscriber-ID` header (proxy) or `subscriber_id=` param (AggregatorChat) to attribute calls to `hermes.main`, `mdcore.ingest`, `mdcore.synth`, etc.
- **OpenAI-compatible proxy** - `llm-keypool proxy` starts a local server at `http://localhost:8000/v1`; point any agent or tool at it and get transparent rotation
- **Think-token stripping** - removes `<think>...</think>` from reasoning model outputs
- **Persistent state** - SQLite, WAL mode; rotation position and cooldowns survive restarts
- **LangSmith compatible** - works with LangChain tracing out of the box

Keys DB lives at: `~/.llm-keypool/keys.db`

Override path: `export LLM_KEYPOOL_DB=/custom/path/keys.db`

---

## Installation

**PyPI:** `llm-keypool`

```bash
# Recommended - with TUI
uv tool install "llm-keypool[gui]"

# With proxy server
pip install "llm-keypool[proxy]"

# Everything
pip install "llm-keypool[all]"

# Minimal
pip install llm-keypool
```

If installing alongside mdcore (so mdcore can import it):

```bash
uv tool install --force "markdowncore-ai[gui]" --with llm-keypool
```

### Upgrading

```bash
uv tool upgrade llm-keypool
# re-add to mdcore environment too
uv tool install --force "markdowncore-ai[gui]" --with llm-keypool
```

---

## Quickstart

```bash
# Register keys (one-time)
llm-keypool add --provider groq --key gsk_... --model llama-3.3-70b-versatile --capabilities general_purpose,fast
llm-keypool add --provider cerebras --key csk_... --model llama-3.3-70b --capabilities general_purpose,fast
llm-keypool add --provider mistral --key sk_... --model mistral-large-latest --capabilities agentic

# Check status
llm-keypool status

# Launch TUI
llm-keypool gui
```

---

## CLI Reference

### `llm-keypool status`

Show all registered keys with cooldown and usage info.

```
llm-keypool status
```

```
 ID  Provider    Category          Model                       Active  Req Today  Cooldown Until
 1   groq        general_purpose   llama-3.3-70b-versatile     yes     42         -
 2   cerebras    general_purpose   llama-3.3-70b               yes     18         -
 3   mistral     general_purpose   mistral-small-latest        yes     0          2026-04-27T00:00:00
```

---

### `llm-keypool add`

Register an API key for a provider.

```bash
llm-keypool add --provider <provider> --key <key> [--model <model>] [--capabilities <caps>]
```

| Flag | Default | Description |
|---|---|---|
| `--model` | provider default | Override the model used for this key |
| `--capabilities` | `general_purpose` | Comma-separated capabilities for this key |

Known capabilities: `general_purpose`, `agentic`, `fast`, `code`, `vision`, `large_context`

Examples:

```bash
# general + fast pool (cerebras, groq)
llm-keypool add --provider groq     --key gsk_...     --capabilities general_purpose,fast  --model llama-3.3-70b-versatile
llm-keypool add --provider cerebras --key csk_...     --capabilities general_purpose,fast  --model llama3.3-70b

# agentic pool (tool use, reasoning)
llm-keypool add --provider mistral    --key sk_...    --capabilities agentic               --model mistral-large-latest
llm-keypool add --provider openrouter --key sk-or-... --capabilities agentic               --model nousresearch/hermes-3-llama-3.1-405b:free

# agentic + fast (groq qwen3)
llm-keypool add --provider groq --key gsk_... --capabilities agentic,fast --model qwen/qwen3-32b

# google gemini (general + fast)
llm-keypool add --provider google --key AIza... --capabilities general_purpose,fast --model gemini-2.0-flash
```

---

### `llm-keypool deactivate`

Deactivate a revoked or expired key. Does not delete it.

```bash
llm-keypool deactivate --id 3
```

---

### `llm-keypool clear-cooldown`

Manually clear a key's cooldown after you've confirmed the quota has reset.

```bash
llm-keypool clear-cooldown --id 2
```

---

### `llm-keypool providers`

List all supported providers, their categories, default models, and OpenAI compatibility.

```bash
llm-keypool providers
```

---

### `llm-keypool gui`

Launch the Textual TUI. Requires `[gui]` extra.

```bash
llm-keypool gui
```

Features: tabular key view, inline deactivate/clear-cooldown, add key form.

---

### `llm-keypool audit`

Show the audit log of all LLM calls with subscriber attribution.

```bash
# summary by subscriber (last 7 days)
llm-keypool audit --summary

# raw rows
llm-keypool audit

# filter to one subscriber
llm-keypool audit --subscriber mdcore.ingest

# longer window
llm-keypool audit --summary --days 30
```

---

### `llm-keypool proxy`

Start a local OpenAI-compatible proxy server. Requires `[proxy]` extra.

```bash
llm-keypool proxy [--host 127.0.0.1] [--port 8000] [--capabilities general_purpose] [--rotate-every 5]
```

Two-proxy setup (recommended for Hermes + mdcore):

```bash
llm-keypool proxy --port 8000 --capabilities agentic               # Hermes main loop
llm-keypool proxy --port 8001 --capabilities general_purpose,fast  # delegate + mdcore
```

The proxy exposes four endpoints:

| Endpoint | Description |
|---|---|
| `POST /v1/chat/completions` | Chat completions with streaming (SSE) support |
| `GET /v1/models` | Lists all models across registered providers |
| `GET /health` | Pool status including active capabilities |
| `GET /audit` | Aggregate token usage by subscriber (last 7 days) |

Request headers:

| Header | Description |
|---|---|
| `X-Subscriber-ID` | Tag this call for audit (e.g. `hermes.main`, `mdcore.ingest`) |
| `X-Keypool-Capabilities` | Override capabilities for this request (comma-separated) |
| `X-Keypool-Category` | Deprecated - use `X-Keypool-Capabilities` |

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="keypool")
response = client.chat.completions.create(
    model="any",
    messages=[{"role": "user", "content": "Hello"}],
    extra_headers={"X-Subscriber-ID": "my-app"},
)
print(response.choices[0].message.content)
```

Each key uses its own assigned model - the `model` field is ignored so rotation across providers works regardless of what model name the client sends.

**Hermes Agent integration:** see [docs/hermes-agent.md](docs/hermes-agent.md) for full two-proxy setup guide.

---

## Registering keys - free tier providers

All providers below have a free tier. No credit card required.

| Provider | Suggested model | Capabilities | Signup |
|---|---|---|---|
| Groq | `llama-3.3-70b-versatile` | general_purpose, fast | https://console.groq.com/keys |
| Cerebras | `llama3.3-70b` | general_purpose, fast | https://cloud.cerebras.ai |
| Mistral | `mistral-large-latest` | agentic | https://console.mistral.ai/api-keys |
| OpenRouter | `meta-llama/llama-3.3-70b-instruct:free` | general_purpose | https://openrouter.ai/settings/keys |
| Google | `gemini-2.0-flash` | general_purpose, fast | https://aistudio.google.com/apikey |
| SambaNova | `Meta-Llama-3.3-70B-Instruct` | general_purpose | https://cloud.sambanova.ai/apis |

Full provider details and rate limits: [PROVIDER_GUIDE.md](PROVIDER_GUIDE.md)

---

## LangChain integration

`AggregatorChat` is a `BaseChatModel` drop-in:

```python
from llm_keypool import AggregatorChat  # only chat models - no embedding support

llm = AggregatorChat(
    capabilities=["general_purpose", "fast"],
    subscriber_id="my-app",
    max_tokens=4096,
    temperature=0.7,
    rotate_every=5,
)

response = llm.invoke("What is the capital of France?")
print(response.content)
print(response.response_metadata)
# {"provider": "groq", "model": "llama-3.3-70b-versatile", "subscriber_id": "my-app", "tokens_used": 42}

# mdcore ingestion
ingest_llm = AggregatorChat(capabilities=["general_purpose", "fast"], subscriber_id="mdcore.ingest")

# mdcore synthesis
synth_llm = AggregatorChat(capabilities=["general_purpose", "fast"], subscriber_id="mdcore.synth")

# hermes delegate calls
delegate_llm = AggregatorChat(capabilities=["general_purpose", "fast"], subscriber_id="hermes.delegate")

# deprecated category style still works
legacy_llm = AggregatorChat(category="general_purpose")  # same as capabilities=["general_purpose"]
```

Async:

```python
response = await llm.ainvoke("Explain async Python.")
```

Works in chains:

```python
from langchain_core.prompts import ChatPromptTemplate

chain = ChatPromptTemplate.from_template("Answer: {question}") | llm
result = chain.invoke({"question": "What is Python?"})
```

LangSmith tracing works automatically if `LANGCHAIN_TRACING_V2` and `LANGCHAIN_API_KEY` are set.

---

## Direct Python usage

```python
import asyncio, json
from llm_keypool.key_store import KeyStore
from llm_keypool.rotator import Rotator
from llm_keypool.providers.dispatch import complete
from pathlib import Path

with open(Path(__file__).parent / "llm_keypool/config/providers.json") as f:
    configs = json.load(f)["providers"]

rotator = Rotator(KeyStore(), configs, rotate_every=5)

async def ask(question: str) -> str:
    result, key_data = await complete(
        rotator,
        category="general_purpose",
        messages=[{"role": "user", "content": question}],
        max_tokens=1024,
    )
    if result.error:
        raise RuntimeError(result.error)
    print(f"[{key_data['provider']} / {key_data['model']}]")
    return result.text

print(asyncio.run(ask("What is 2 + 2?")))
```

---

## Cooldown behaviour per provider

Cooldown timestamps are derived from response headers where available, so the key is released at the earliest possible moment rather than a conservative guess.

| Provider | Source | Behaviour |
|---|---|---|
| **Groq** | `x-ratelimit-reset-requests` header | Exact reset duration parsed from the header (e.g. `1m26.4s`). On 429 with `retry-after`, uses that instead. |
| **Cerebras** | `x-ratelimit-remaining-requests-{minute,hour,day}` | Tiered: minute exhausted -> 60s; hour exhausted -> 3600s; day exhausted -> next UTC midnight. |
| **Mistral** | `x-ratelimit-remaining-req-minute` | 60s rolling when per-minute quota hits zero. |
| **OpenRouter** | none (no headers returned) | Next UTC midnight (RPD is binding limit). |
| **SambaNova** | none | 65s rolling. |
| **Cohere** | none | First of next calendar month (monthly call cap). |
| **Cloudflare** | none | Next UTC midnight (daily neuron budget). |
| **Jina** | none | 65s rolling. |
| **HuggingFace** | none | 120s rolling. |

Header parsing was verified against live API responses. Providers without header support fall back to the `cooldown_fallback.strategy` field in `providers.json`, so the strategy is config-driven rather than hardcoded.

---

## Project structure

```
llm-keypool/
- llm_keypool/
  - cli.py               # Typer CLI (status, add, deactivate, clear-cooldown, providers, gui, proxy)
  - proxy.py             # OpenAI-compatible proxy server (FastAPI)
  - tui.py               # Textual TUI
  - key_store.py         # SQLite persistence (~/.llm-keypool/keys.db)
  - rotator.py           # round-robin rotation + cooldown logic
  - langchain_wrapper.py # AggregatorChat (BaseChatModel)
  - providers/
    - dispatch.py        # retry loop, 429 handling, provider routing
    - headers.py         # rate-limit header parsing + per-provider cooldown extraction
    - openai_compat.py   # AsyncOpenAI client + think-token stripping
    - cohere.py
    - cloudflare.py
  - config/
    - providers.json     # provider metadata, limits, models, reset schedules
- docs/
  - hermes-agent.md      # Hermes Agent integration guide
- tests/
  - test_key_store.py    # KeyStore CRUD, cooldown, usage, migration
  - test_rotator.py      # rotation, 429 handling, cooldown strategies
  - test_cli.py          # CLI commands via Typer test runner
  - test_langchain_wrapper.py  # AggregatorChat mocks
- stress_test.py         # live rotation stress tester (real API calls)
- PROVIDER_GUIDE.md      # signup URLs and rate limits per provider
- TODO.md                # known limitations and planned improvements
```

---

## Roadmap

**OpenClaw AgentSkill** - expose llm-keypool as an [OpenClaw](https://github.com/openclaw/openclaw) AgentSkill so OpenClaw's autonomous agent loop can call the key pool directly without needing a LangChain wrapper. OpenClaw skills register as callable tools with typed inputs - `keypool_complete(messages, category)` would drop in as a first-class skill, giving OpenClaw transparent key rotation and free-tier quota management across its LLM calls.

**Session affinity** - optionally pin a conversation to the same provider/key for the duration of a session, so multi-turn context stays consistent. Useful when a delegated sub-agent needs to maintain state within a single task.
