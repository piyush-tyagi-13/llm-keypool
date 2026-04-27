# llm-aggregator

Free-tier LLM key pool manager. Register API keys from multiple providers once - the aggregator round-robins across them, handles 429 cooldowns, and retries transparently. No paid API needed.

Exposes a CLI, a Textual TUI, and a LangChain drop-in (`AggregatorChat`).

---

## What it does

- **Multi-provider pooling** - pool keys across Groq, Cerebras, Mistral, OpenRouter, SambaNova, and more
- **Automatic rotation** - round-robin across keys, rotates every N requests (default: 5)
- **429 handling** - on rate limit, key enters cooldown; next call retries a different key automatically
- **Think-token stripping** - removes `<think>...</think>` from reasoning model outputs
- **Persistent state** - SQLite, WAL mode; rotation position and cooldowns survive restarts
- **LangSmith compatible** - works with LangChain tracing out of the box

Keys DB lives at: `~/.llm-aggregator/keys.db`

Override path: `export LLM_AGGREGATOR_DB=/custom/path/keys.db`

---

## Installation

Not on PyPI. Install from GitHub:

```bash
pip install git+https://github.com/piyush-tyagi-13/llm-aggregator
```

With MCP server support:

```bash
pip install "llm-aggregator[mcp] @ git+https://github.com/piyush-tyagi-13/llm-aggregator"
```

With Textual TUI:

```bash
pip install "llm-aggregator[gui] @ git+https://github.com/piyush-tyagi-13/llm-aggregator"
```

If installing alongside another `uv tool` (e.g. mdcore):

```bash
uv tool install "markdowncore-ai[gui]" --with "llm-aggregator @ git+https://github.com/piyush-tyagi-13/llm-aggregator"
```

### Upgrading

```bash
pip install --force-reinstall git+https://github.com/piyush-tyagi-13/llm-aggregator

# via uv tool:
uv tool install --force --refresh "markdowncore-ai[gui]" --with "llm-aggregator @ git+https://github.com/piyush-tyagi-13/llm-aggregator"
```

---

## Quickstart

```bash
# Register keys (one-time)
llm-aggregator add groq gsk_... --model llama-3.3-70b-versatile --category general_purpose
llm-aggregator add cerebras csk_... --model llama-3.3-70b --category general_purpose

# Check status
llm-aggregator status

# Launch TUI
llm-aggregator gui
```

---

## CLI Reference

### `llm-aggregator status`

Show all registered keys with cooldown and usage info.

```
llm-aggregator status
```

```
 ID  Provider    Category          Model                       Active  Req Today  Cooldown Until
 1   groq        general_purpose   llama-3.3-70b-versatile     yes     42         -
 2   cerebras    general_purpose   llama-3.3-70b               yes     18         -
 3   mistral     general_purpose   mistral-small-latest        yes     0          2026-04-27T00:00:00
```

---

### `llm-aggregator add`

Register an API key for a provider.

```bash
llm-aggregator add <provider> <key> --model <model> --category <category>
```

| Flag | Default | Description |
|---|---|---|
| `--model` | provider default | Override the model used for this key |
| `--category` | `general_purpose` | Key pool category |

Examples:

```bash
llm-aggregator add groq gsk_...          --model llama-3.3-70b-versatile --category general_purpose
llm-aggregator add cerebras csk_...      --model llama-3.3-70b           --category general_purpose
llm-aggregator add mistral sk_...        --model mistral-small-latest     --category general_purpose
llm-aggregator add openrouter sk-or-...  --model meta-llama/llama-3.3-70b-instruct:free --category general_purpose
```

---

### `llm-aggregator deactivate`

Deactivate a revoked or expired key. Does not delete it.

```bash
llm-aggregator deactivate --id 3
```

---

### `llm-aggregator clear-cooldown`

Manually clear a key's cooldown after you've confirmed the quota has reset.

```bash
llm-aggregator clear-cooldown --id 2
```

---

### `llm-aggregator providers`

List all supported providers, their categories, default models, and OpenAI compatibility.

```bash
llm-aggregator providers
```

---

### `llm-aggregator gui`

Launch the Textual TUI. Requires `[gui]` extra.

```bash
llm-aggregator gui
```

Features: tabular key view, inline deactivate/clear-cooldown, add key form.

---

### `llm-aggregator serve`

Start the MCP server for Claude Desktop / MCP clients. Requires `[mcp]` extra.

```bash
llm-aggregator serve
```

---

## Registering keys - free tier providers

All providers below have a free tier. No credit card required.

| Provider | Suggested model | Signup |
|---|---|---|
| Groq | `llama-3.3-70b-versatile` | https://console.groq.com/keys |
| Cerebras | `llama-3.3-70b` | https://cloud.cerebras.ai |
| Mistral | `mistral-small-latest` | https://console.mistral.ai/api-keys |
| OpenRouter | `meta-llama/llama-3.3-70b-instruct:free` | https://openrouter.ai/settings/keys |

Full provider details and rate limits: [PROVIDER_GUIDE.md](PROVIDER_GUIDE.md)

---

## LangChain integration

`AggregatorChat` is a `BaseChatModel` drop-in:

```python
from llm_aggregator import AggregatorChat

llm = AggregatorChat(
    category="general_purpose",
    max_tokens=4096,
    temperature=0.7,
    rotate_every=5,
)

response = llm.invoke("What is the capital of France?")
print(response.content)
print(response.response_metadata)
# {"provider": "groq", "model": "llama-3.3-70b-versatile", "tokens_used": 42}
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
from llm_aggregator.key_store import KeyStore
from llm_aggregator.rotator import Rotator
from llm_aggregator.providers.dispatch import complete
from pathlib import Path

with open(Path(__file__).parent / "llm_aggregator/config/providers.json") as f:
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

| Provider | On 429 / exhaustion |
|---|---|
| Groq, Cerebras, OpenRouter | Cooldown until next UTC midnight |
| Mistral | 35-second rolling cooldown |
| SambaNova | 65-second rolling cooldown |
| Cohere | Cooldown until first of next month |
| Cloudflare | Cooldown until next UTC midnight |

---

## Project structure

```
llm-aggregator/
- llm_aggregator/
  - cli.py               # Typer CLI (status, add, deactivate, clear-cooldown, providers, serve, gui)
  - tui.py               # Textual TUI
  - key_store.py         # SQLite persistence (~/.llm-aggregator/keys.db)
  - rotator.py           # round-robin rotation + cooldown logic
  - langchain_wrapper.py # AggregatorChat (BaseChatModel)
  - providers/
    - dispatch.py        # retry loop, 429 handling, provider routing
    - openai_compat.py   # AsyncOpenAI client + think-token stripping
    - cohere.py
    - cloudflare.py
  - config/
    - providers.json     # provider metadata, limits, models, reset schedules
- server.py              # MCP server entry point (optional)
- PROVIDER_GUIDE.md      # signup URLs and rate limits per provider
- TODO.md                # known limitations and planned improvements
```
