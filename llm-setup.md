# LLM Setup for mdcore

mdcore uses up to 3 models. All configured in `~/.mdcore/config.yaml`.

---

## Models and Their Purpose

| Model | Config section | Used for | Required? |
|---|---|---|---|
| Embedding model | `embeddings` | Vectorising vault chunks + incoming docs | Yes - always |
| Primary LLM | `llm` | Classification, folder routing, proposal generation (Flow B) | Yes - for `mdcore ingest` |
| Synthesis LLM | `llm.synthesise_model` | Reformatting retrieved excerpts into a briefing (Flow A) | No - defaults to primary LLM |

---

## Minimum Required Info Per Backend

### Ollama (local, no API key)

```yaml
embeddings:
  backend: ollama
  local_model: nomic-embed-text   # or bge-m3

llm:
  backend: ollama
  model: qwen3.5:4b               # or any pulled model
```

Pull models first:
```bash
ollama pull nomic-embed-text
ollama pull qwen3.5:4b
```

---

### Gemini

```yaml
embeddings:
  backend: gemini
  api_model: models/gemini-embedding-001
  api_key: AIza...

llm:
  backend: gemini
  model: gemini-2.5-flash-lite
  api_key: AIza...
```

Get key: https://aistudio.google.com/apikey

---

### OpenAI

```yaml
embeddings:
  backend: openai
  api_model: text-embedding-3-small
  api_key: sk-...

llm:
  backend: openai
  model: gpt-4o-mini
  api_key: sk-...
```

Install extra: `uv tool install "markdowncore-ai[openai]"`

---

### Anthropic

Anthropic does not offer an embedding model. Use a different backend for embeddings.

```yaml
embeddings:
  backend: ollama              # or openai/gemini
  local_model: nomic-embed-text

llm:
  backend: anthropic
  model: claude-haiku-4-5
  api_key: sk-ant-...
```

Install extra: `uv tool install "markdowncore-ai[anthropic]"`

---

## Split Config - Different Providers for Ingestion vs Synthesis

Use a cheap/fast model for synthesis (Flow A) and a stronger model for classification (Flow B):

```yaml
llm:
  backend: ollama
  model: qwen3.5:4b             # used for classify + propose + route_folder

  synthesise_backend: gemini    # optional - omit to reuse primary backend
  synthesise_model: gemini-2.5-flash-lite
  synthesise_api_key: AIza...
```

If `synthesise_backend` is omitted, synthesis uses the same backend as `llm.backend`.
If `synthesise_model` is omitted, synthesis uses the same model as `llm.model`.

---

## Fallback LLM

If primary LLM call fails, mdcore retries with a fallback:

```yaml
llm:
  backend: ollama
  model: qwen3.5:4b
  fallback_backend: gemini
  fallback_model: gemini-2.5-flash-lite
  fallback_api_key: AIza...
```

---

## Hardware Guidance

| Hardware | Recommended LLM | Recommended Embedding |
|---|---|---|
| Apple M2 16GB+ | `qwen3.5:4b` (Ollama) | `nomic-embed-text` (Ollama) |
| i5 + RTX 4070 | `qwen3:8b` (Ollama) | `bge-m3` (Ollama) |
| Low-end / no GPU | `gpt-4o-mini` or `gemini-2.5-flash-lite` | `text-embedding-3-small` or `models/gemini-embedding-001` |

---

## Observability

Token usage logged after every LLM call:
```
INFO llm - tokens [gemini-2.5-flash-lite] in=312 out=89 total=401
```
Log file: `~/.mdcore/logs/`

Optional LangSmith tracing:
```yaml
llm:
  langsmith_api_key: <your-key>
  langsmith_project: mdcore
```
