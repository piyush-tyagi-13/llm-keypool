# llm-aggregator

Free-tier LLM key aggregator with automatic rotation. Register API keys from multiple providers once; the aggregator selects the best available key, rotates on rate limits, and retries transparently - your application never touches a key directly.

Exposed as both an **MCP server** (for Claude and other MCP clients) and a **LangChain drop-in** (`AggregatorChat`, `AggregatorEmbeddings`).

---

## What it does

- **Multi-provider pooling** - pool keys across Groq, Cerebras, SambaNova, Mistral, OpenRouter, and more
- **Automatic rotation** - round-robin across keys, forced every N requests (default: 5)
- **429 handling** - on rate limit, key enters provider-specific cooldown; next call auto-retries a different key
- **Header-aware** - reads `x-ratelimit-remaining-requests` from provider responses; cooldowns key preemptively when exhausted
- **Think-token stripping** - removes `<think>...</think>` blocks from reasoning models before returning text
- **Persistent state** - rotation position and quota counters survive server restarts (SQLite, WAL mode)
- **Quota tracking** - per-key daily/monthly request and token counters with automatic period resets

---

## Supported Providers

| Provider | Category | Free Limits |
|---|---|---|
| Groq | general_purpose | 14,400 req/day, 6,000 TPM |
| Cerebras | general_purpose | 1M tokens/day |
| SambaNova | general_purpose | 20-30 RPM per model |
| Mistral | general_purpose | 2 RPM, 1B tokens/month |
| OpenRouter | general_purpose | 200 req/day (free models) |
| Cloudflare Workers AI | general_purpose | 10,000 neurons/day |
| Cohere | general_purpose + embedding | 1,000 calls/month |

Full signup URLs and rate limit details: [PROVIDER_GUIDE.md](PROVIDER_GUIDE.md)

---

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/llm-aggregator
cd llm-aggregator
pip install -e .
```

Dependencies: `mcp[cli]`, `openai`, `httpx`, `langchain-core`

---

## Quickstart: MCP Server

### 1. Start the server

```bash
python server.py
```

Or register it with Claude Desktop / any MCP client:

```json
{
  "mcpServers": {
    "llm-aggregator": {
      "command": "python",
      "args": ["/path/to/llm-aggregator/server.py"]
    }
  }
}
```

### 2. Register keys (one-time setup)

```
register_key(provider="groq", api_key="gsk_...")
register_key(provider="cerebras", api_key="csk_...")
register_key(provider="mistral", api_key="...")
register_key(provider="openrouter", api_key="sk-or-...")
```

Providers with multiple categories (Cohere, Cloudflare) require an explicit `category`:

```
register_key(provider="cohere", api_key="...", category="general_purpose")
```

Override the default model for a key:

```
register_key(provider="groq", api_key="gsk_...", model="llama-3.1-8b-instant")
```

### 3. Make completions

```
complete(messages='[{"role": "user", "content": "Hello!"}]')
```

Returns:
```json
{
  "text": "Hello! How can I help you?",
  "provider": "groq",
  "model": "llama-3.3-70b-versatile",
  "tokens_used": 42
}
```

The aggregator selects the key, handles rate limits, and retries - you never see provider errors unless all keys are exhausted.

---

## MCP Tools Reference

| Tool | Description |
|---|---|
| `register_key` | Register an API key for a provider |
| `get_key` | Get the best available key for a category (use `complete` instead for most cases) |
| `complete` | Send a chat completion - handles key selection, rotation, retries |
| `list_keys` | Show all keys with quota usage and cooldown status |
| `report_usage` | Report result of a manual API call (needed when using `get_key` directly) |
| `update_key` | Change the model or API key value for an existing key in-place |
| `deactivate_key` | Permanently deactivate a revoked or expired key |
| `clear_cooldown` | Manually clear a key's cooldown after confirmed quota reset |
| `get_providers` | List all supported providers with limits and models |

### `complete` parameters

| Parameter | Default | Description |
|---|---|---|
| `messages` | required | JSON array: `[{"role": "user", "content": "..."}]` |
| `category` | `general_purpose` | Key pool to use |
| `max_tokens` | `4096` | Max response tokens |
| `temperature` | `0.7` | Sampling temperature (0.0-2.0) |

### `register_key` parameters

| Parameter | Required | Description |
|---|---|---|
| `provider` | yes | Provider name (see `get_providers`) |
| `api_key` | yes | API key string |
| `category` | auto | Required for multi-category providers (cohere, cloudflare) |
| `model` | no | Override provider default model |
| `extra_params` | no | JSON string, required for Cloudflare: `'{"account_id": "..."}'` |

---

## Integration: LangChain

Drop `AggregatorChat` into any LangChain application as a `BaseChatModel`:

```python
from llm_aggregator import AggregatorChat

llm = AggregatorChat(
    category="general_purpose",
    max_tokens=4096,
    temperature=0.7,
    rotate_every=5,        # force rotation after N requests per key
)

response = llm.invoke("What is the capital of France?")
print(response.content)
```

Async usage:

```python
response = await llm.ainvoke("What is the capital of France?")
```

Chain usage:

```python
from langchain_core.prompts import ChatPromptTemplate

chain = ChatPromptTemplate.from_template("Answer: {question}") | llm
result = chain.invoke({"question": "What is Python?"})
```

`response_metadata` carries provider/model/token info:

```python
response.response_metadata
# {"provider": "cerebras", "model": "llama3.3-70b", "tokens_used": 87}
```

### Drop into an existing LangChain app (mdcore / llm_layer pattern)

In your `_build_llm()`:

```python
from llm_aggregator import AggregatorChat

elif backend == "llm_aggregator":
    return AggregatorChat()
```

Config (`~/.yourapp/config.yaml`):

```yaml
llm:
  backend: llm_aggregator
```

---

## Integration: Direct Python (no LangChain)

```python
import asyncio
from llm_aggregator.key_store import KeyStore
from llm_aggregator.rotator import Rotator
from llm_aggregator.providers.dispatch import complete
import json

with open("llm_aggregator/config/providers.json") as f:
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

## Configuration

### Database path

Default: `<project_root>/db/keys.db`

Override:

```bash
LLM_AGGREGATOR_DB=/custom/path/keys.db python server.py
```

### Rotation policy

Rotation is round-robin - keys are served in fixed order, each key used up to `rotate_every` times before advancing. After all keys exhaust their slots, the cycle resets from the beginning.

Default `rotate_every`: 5. Override per-instance:

```python
AggregatorChat(rotate_every=10)
```

Or in `server.py`:

```python
rotator = Rotator(store, PROVIDER_CONFIGS, rotate_every=10)
```

### Cooldown strategies per provider

| Provider | On 429 / exhaustion |
|---|---|
| Groq, Cerebras, OpenRouter | Cooldown until next UTC midnight |
| Mistral | 35-second rolling cooldown |
| SambaNova | 65-second rolling cooldown |
| Cohere | Cooldown until first of next month |
| Cloudflare | Cooldown until next UTC midnight |

---

## Key management

### List all keys and quota status

```
list_keys()
```

```json
{
  "keys": [
    {
      "id": 1,
      "provider": "groq",
      "model": "llama-3.3-70b-versatile",
      "active": true,
      "in_cooldown": false,
      "requests_today": 42,
      "tokens_today": 18500
    }
  ]
}
```

### Update a key's model without re-registering

```
update_key(key_id=1, model="llama-3.1-8b-instant")
```

### Manually clear a cooldown

```
clear_cooldown(key_id=1)
```

### Deactivate a revoked key

```
deactivate_key(key_id=3)
```

---

## Publishing to GitHub

### First publish

```bash
cd llm-aggregator
git init
git add .
git commit -m "Initial release: LLM aggregator MCP server with LangChain wrapper"
gh repo create llm-aggregator --public --source=. --push
```

### What to exclude (.gitignore)

```
db/
*.db
*.db-wal
*.db-shm
keys_and_models.txt
__pycache__/
*.egg-info/
.env
```

The `db/` directory contains your registered API keys - never commit it.

### Publishing to PyPI (optional)

```bash
pip install build twine
python -m build
twine upload dist/*
```

Users can then install with:

```bash
pip install llm-aggregator
```

Start the MCP server via:

```bash
python -m llm_aggregator.server
```

For that to work, add `server.py` as `llm_aggregator/server.py` or add an entry point to `pyproject.toml`:

```toml
[project.scripts]
llm-aggregator = "server:mcp.run"
```

---

## Project structure

```
llm-aggregator/
- server.py                          # MCP server entry point
- llm_aggregator/
  - __init__.py                      # exports AggregatorChat, AggregatorEmbeddings
  - key_store.py                     # SQLite persistence (keys, quotas, rotation state)
  - rotator.py                       # round-robin rotation logic + cooldown strategies
  - langchain_wrapper.py             # AggregatorChat (BaseChatModel), AggregatorEmbeddings
  - providers/
    - base.py                        # CompletionResult, EmbeddingResult dataclasses
    - dispatch.py                    # retry loop, 429 handling, provider routing
    - openai_compat.py               # AsyncOpenAI client + think-token stripping
    - cohere.py                      # Cohere native client
    - cloudflare.py                  # Cloudflare Workers AI native client
  - config/
    - providers.json                 # provider metadata, limits, models, reset schedules
- PROVIDER_GUIDE.md                  # signup URLs and free tier limits per provider
- pyproject.toml
```
