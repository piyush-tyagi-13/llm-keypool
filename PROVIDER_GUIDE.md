# llm-keypool - Provider Guide

> Generated: 2026-04-30
> Purpose: Registration guide for API keys + config source for reset schedules and rate limits.
> Use this doc to sign up for each provider and register keys into llm-keypool.

---

## How to use this guide

1. Visit each provider's signup URL below
2. Create account, generate API key
3. Register key via CLI: `llm-keypool add --provider <name> --key <key>`
4. llm-keypool loads reset schedules and limits from `providers.json` (derived from this doc)

---

## Category Definitions

| Category | Description |
|---|---|
| `general_purpose` | Chat, completion, instruction-following models |
| `embedding` | Text embedding / vector models |

Some providers (Google, Cohere, Cloudflare) appear in both categories.

---

## General Purpose Providers

### 1. Groq

- **Signup:** https://console.groq.com
- **No credit card required:** Yes
- **Base URL:** `https://api.groq.com/openai/v1`
- **Auth header:** `Authorization: Bearer <API_KEY>`
- **OpenAI-compatible:** Yes

**Free tier limits:**

| Metric | Limit |
|---|---|
| Requests per minute (RPM) | 30 |
| Tokens per minute (TPM) | 6,000 (Gemma 2 9B: 15,000) |
| Requests per day (RPD) | ~14,400 |

**Free models:**

| Model ID | Notes |
|---|---|
| `llama-3.3-70b-versatile` | Best general-purpose |
| `llama-3.1-8b-instant` | Fast, smaller |
| `gemma2-9b-it` | Higher TPM limit |
| `mixtral-8x7b-32768` | Long context |

**Quota tracking:**

- Response headers expose: `x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens`
- `x-ratelimit-remaining-requests` = remaining **per-day** requests
- `x-ratelimit-remaining-tokens` = remaining **per-minute** tokens
- No dedicated quota API endpoint
- **Strategy:** Parse response headers + local counter for daily RPD

**Reset schedule:**

| Window | Resets |
|---|---|
| RPM/TPM | Rolling 60-second window |
| RPD | Daily (midnight UTC assumed) |

---

### 2. Google AI Studio (Gemini)

- **Signup:** https://aistudio.google.com
- **No credit card required:** Yes
- **Base URL (REST):** `https://generativelanguage.googleapis.com/v1beta`
- **Base URL (OpenAI-compat):** `https://generativelanguage.googleapis.com/v1beta/openai`
- **Auth header:** `Authorization: Bearer <API_KEY>` or `?key=<API_KEY>` param
- **OpenAI-compatible:** Yes (via `/openai` path)

**Free tier limits (Gemini 2.5 Flash):**

| Metric | Limit |
|---|---|
| Requests per minute (RPM) | 10 |
| Tokens per minute (TPM) | 250,000 |
| Requests per day (RPD) | 500 |

**Free models:**

| Model ID | Category | Notes |
|---|---|---|
| `gemini-2.5-flash` | general_purpose | Best free model |
| `gemini-2.0-flash` | general_purpose | Stable alternative |
| `text-embedding-005` | embedding | 768 dimensions, free |
| `gemini-embedding-exp-03-07` | embedding | Experimental, higher dim |

**Quota tracking:**

- 429 response includes headers: `x-ratelimit-limit-requests`, `x-ratelimit-remaining-requests`, `x-ratelimit-reset-requests`
- Also `x-ratelimit-limit-tokens`, `x-ratelimit-remaining-tokens`
- **Strategy:** Parse 429 response headers for reset time; track RPD locally

**Reset schedule:**

| Window | Resets |
|---|---|
| RPM/TPM | Rolling 60-second window |
| RPD | Daily at midnight Pacific time |

---

### 3. Cerebras

- **Signup:** https://cloud.cerebras.ai
- **No credit card required:** Yes
- **Base URL:** `https://api.cerebras.ai/v1`
- **Auth header:** `Authorization: Bearer <API_KEY>`
- **OpenAI-compatible:** Yes

**Free tier limits:**

| Metric | Limit |
|---|---|
| Requests per minute (RPM) | 30 |
| Tokens per minute (TPM) | 60,000 - 100,000 |
| Tokens per day | 1,000,000 |
| Max context (free) | 8,192 tokens |

**Free models:**

| Model ID | Notes |
|---|---|
| `qwen-3-235b` | Largest available |
| `gpt-oss-120b` | Strong general use |
| `llama3.3-70b` | Fast, reliable |
| `llama3.1-8b` | Fastest |

**Quota tracking:**

- Uses token bucket algorithm - replenishes continuously, no hard daily reset at fixed clock time
- Daily token cap (1M) resets at midnight UTC
- No dedicated quota API endpoint
- **Strategy:** Local token counter; reset daily at 00:00 UTC; treat 429 as signal

**Reset schedule:**

| Window | Resets |
|---|---|
| RPM/TPM | Continuous replenishment (token bucket) |
| Daily token cap | 00:00 UTC |

---

### 4. SambaNova Cloud

- **Signup:** https://cloud.sambanova.ai
- **No credit card required:** Yes (includes $5 initial credits, expires 30 days)
- **Base URL:** `https://api.sambanova.ai/v1`
- **Auth header:** `Authorization: Bearer <API_KEY>`
- **OpenAI-compatible:** Yes

**Free tier limits:**

| Model | RPM |
|---|---|
| Llama 3.1 8B | 30 |
| Llama 3.3 70B | 20 |
| Qwen 2.5 72B | 20 |
| Llama 3.1 405B | 10 |

**Free models:**

| Model ID | Notes |
|---|---|
| `Meta-Llama-3.1-8B-Instruct` | Fastest |
| `Meta-Llama-3.3-70B-Instruct` | Best quality free |
| `Meta-Llama-3.1-405B-Instruct` | Largest, slowest RPM |
| `Qwen2.5-72B-Instruct` | Strong alternative |

**Quota tracking:**

- No dedicated quota API endpoint
- No published response headers for quota
- **Strategy:** Local request counter per model + 429 signal

**Reset schedule:**

| Window | Resets |
|---|---|
| RPM | Rolling 60-second window |
| Initial $5 credits | Expire 30 days after signup (one-time) |

> **Note:** After $5 credits expire, rate-limited free tier persists. RPM limits are the main constraint.

---

### 5. Mistral AI

- **Signup:** https://console.mistral.ai
- **Plan:** Experiment (free, no CC)
- **No credit card required:** Yes
- **Base URL:** `https://api.mistral.ai/v1`
- **Auth header:** `Authorization: Bearer <API_KEY>`
- **OpenAI-compatible:** Yes

**Free tier limits:**

| Metric | Limit |
|---|---|
| Requests per second (RPS) | ~0.033 (2 RPM) |
| Requests per minute (RPM) | 2 |
| Tokens per minute (TPM) | 500,000 |
| Tokens per month | 1,000,000,000 (1B) |

**Free models:**

| Model ID | Notes |
|---|---|
| `mistral-large-latest` | Best quality |
| `mistral-small-latest` | Faster |
| `codestral-latest` | Code-specialized |
| `open-mistral-7b` | Smallest |
| `open-mixtral-8x7b` | MoE |

**Quota tracking:**

- API responses include `usage` field: `prompt_tokens`, `completion_tokens`, `total_tokens`
- No programmatic quota-remaining endpoint
- Monthly cap viewable in console only
- **Strategy:** Accumulate monthly token count locally; reset on calendar month boundary

**Reset schedule:**

| Window | Resets |
|---|---|
| RPM | Rolling 60-second window |
| Monthly token cap | 1st of each calendar month |

---

### 6. OpenRouter

- **Signup:** https://openrouter.ai
- **No credit card required:** Yes (free models need no credits)
- **Base URL:** `https://openrouter.ai/api/v1`
- **Auth header:** `Authorization: Bearer <API_KEY>`
- **OpenAI-compatible:** Yes

**Free tier limits:**

| Metric | Limit |
|---|---|
| Requests per minute (RPM) | 20 |
| Requests per day (RPD) | 200 |

> Free models use the `:free` suffix. They share rate limits across all `:free` models on a key.

**Free models (select):**

| Model ID | Notes |
|---|---|
| `meta-llama/llama-3.3-70b-instruct:free` | Strong general use |
| `google/gemma-3-27b-it:free` | Google's open model |
| `mistralai/mistral-7b-instruct:free` | Fast |
| `microsoft/phi-4:free` | Strong for size |
| `qwen/qwen-2.5-72b-instruct:free` | Multilingual |
| `nvidia/llama-3.1-nemotron-70b-instruct:free` | High quality |

> Full current list: https://openrouter.ai/models/?q=free (30+ models)

**Quota tracking:**

- **Dedicated endpoint exists:** `GET https://openrouter.ai/api/v1/credits`
  - Returns: `{ "data": { "total_credits": X, "total_usage": Y } }`
- Also: `GET https://openrouter.ai/api/v1/key` returns rate limit and credits info
- **Strategy:** Poll `/api/v1/credits` to check remaining balance; track RPD locally

**Reset schedule:**

| Window | Resets |
|---|---|
| RPM | Rolling 60-second window |
| RPD (200 req) | Daily at 00:00 UTC |

---

### 7. Cloudflare Workers AI

- **Signup:** https://dash.cloudflare.com (Workers & Pages -> Workers AI)
- **No credit card required:** Yes (free plan)
- **Base URL:** `https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/`
- **Auth header:** `Authorization: Bearer <API_TOKEN>` (also needs `CF-Account-Id` or embedded in URL)
- **OpenAI-compatible:** Partial (via `/v1` gateway)
- **Note:** Requires your Cloudflare `ACCOUNT_ID` alongside the API token

**Free tier limits:**

| Metric | Limit |
|---|---|
| Neurons per day | 10,000 |

> Neurons = GPU compute units. Vary by model and token count.

**Free models:**

| Model ID | Notes |
|---|---|
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | General purpose |
| `@cf/meta/llama-3.1-8b-instruct` | Fast |
| `@cf/mistral/mistral-7b-instruct-v0.2-lora` | Mistral |
| `@cf/qwen/qwen1.5-14b-chat-awq` | Qwen |
| `@cf/baai/bge-large-en-v1.5` | embedding |
| `@cf/baai/bge-base-en-v1.5` | embedding, smaller |

**Quota tracking:**

- No API endpoint to query remaining Neurons
- Dashboard only (dash.cloudflare.com -> Workers AI -> Usage)
- **Strategy:** Local Neuron estimation (approximate) + 429 signal

**Reset schedule:**

| Window | Resets |
|---|---|
| Daily Neuron cap | 00:00 UTC daily |

---

### 8. Cohere

- **Signup:** https://dashboard.cohere.com
- **Plan:** Trial key (free, no CC)
- **No credit card required:** Yes
- **Base URL:** `https://api.cohere.com/v2`
- **Auth header:** `Authorization: Bearer <API_KEY>`
- **OpenAI-compatible:** No (native SDK or REST)

**Free tier limits:**

| Endpoint | Per-minute limit | Monthly cap |
|---|---|---|
| `/v2/chat` | 20 RPM | Shared 1,000 calls/month |
| `/v2/embed` (text) | 100 RPM | Shared 1,000 calls/month |
| `/v2/embed` (image) | 5 RPM | Shared 1,000 calls/month |
| `/v2/rerank` | 10 RPM | Shared 1,000 calls/month |

> All endpoints share the 1,000 call/month pool.

**Free models:**

| Model ID | Category | Notes |
|---|---|---|
| `command-a-03-2025` | general_purpose | Latest Command A |
| `command-r-plus-08-2024` | general_purpose | Command R+ |
| `command-r-08-2024` | general_purpose | Smaller |
| `embed-v4.0` | embedding | Best embedding model |
| `embed-english-v3.0` | embedding | English-only, lighter |

**Quota tracking:**

- No programmatic quota remaining endpoint
- Usage visible in dashboard only
- **Strategy:** Local monthly call counter; reset on 1st of calendar month

**Reset schedule:**

| Window | Resets |
|---|---|
| RPM | Rolling 60-second window |
| Monthly call cap (1,000) | 1st of each calendar month |

---

## Embedding-Only Providers

### 9. Jina AI

- **Signup:** https://jina.ai/embeddings
- **No credit card required:** Yes (auto-generates key on page)
- **Base URL:** `https://api.jina.ai/v1`
- **Auth header:** `Authorization: Bearer <API_KEY>`
- **OpenAI-compatible:** Yes (`/v1/embeddings` endpoint)

**Free tier limits:**

| Metric | Limit |
|---|---|
| One-time initial tokens | 1,000,000 tokens |
| RPM (free ongoing) | 100 |
| TPM (free ongoing) | 100,000 |
| Concurrent requests | 2 |

> After 1M initial tokens consumed, rate-limited free access continues at 100 RPM/100K TPM.

**Free models:**

| Model ID | Dimensions | Notes |
|---|---|---|
| `jina-embeddings-v3` | 1024 | Multilingual, best |
| `jina-colbert-v2` | - | Late interaction, retrieval-optimized |
| `jina-clip-v2` | 1024 | Text + image |

> Same key works for Jina Reader, Reranker, and Classifier APIs - tokens shared.

**Quota tracking:**

- Dashboard: "API Key & Billing" tab shows usage history + remaining tokens
- No programmatic quota API endpoint
- **Strategy:** Local token counter + 429 signal; initial 1M tokens tracked from first use

**Reset schedule:**

| Window | Resets |
|---|---|
| Initial 1M token grant | One-time, does not reset |
| RPM/TPM ongoing limits | Rolling windows |

---

### 10. Hugging Face (Serverless Inference)

- **Signup:** https://huggingface.co
- **No credit card required:** Yes
- **Base URL:** `https://api-inference.huggingface.co/models/<model-id>`
- **Alt Base URL (Inference Providers):** `https://router.huggingface.co`
- **Auth header:** `Authorization: Bearer <HF_TOKEN>`
- **OpenAI-compatible:** Partial (via `https://api-inference.huggingface.co/v1/`)

**Free tier limits:**

| Metric | Limit |
|---|---|
| Monthly credits | Undisclosed (modest, shared across providers) |
| Rate limit | ~few hundred requests/hour |

> Exact limit varies by model and load. Free tier is best-effort.

**Free embedding models:**

| Model ID | Dimensions | Notes |
|---|---|---|
| `BAAI/bge-large-en-v1.5` | 1024 | Strong English |
| `BAAI/bge-m3` | 1024 | Multilingual |
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | Lightweight |
| `sentence-transformers/all-mpnet-base-v2` | 768 | Good quality |
| `thenlper/gte-large` | 1024 | Strong MTEB |

**Quota tracking:**

- No programmatic quota API
- Dashboard: https://huggingface.co/settings/billing
- **Strategy:** 429 signal only; treat as best-effort fallback provider

**Reset schedule:**

| Window | Resets |
|---|---|
| Monthly credits | 1st of each calendar month |

---

## Provider Summary Table

| Provider | Category | Free? | Monthly Reset | Daily Reset | Quota API | OpenAI-Compat |
|---|---|---|---|---|---|---|
| Groq | general_purpose | Yes | No | Yes (RPD) | Headers only | Yes |
| Google AI Studio | both | Yes | No | Yes (RPD) | Headers (429) | Yes |
| Cerebras | general_purpose | Yes | No | Yes (1M tok) | No | Yes |
| SambaNova | general_purpose | Yes | No | No (RPM only) | No | Yes |
| Mistral | general_purpose | Yes | Yes (1B tok) | No | No | Yes |
| OpenRouter | general_purpose | Yes | No | Yes (200 req) | Yes (`/api/v1/credits`) | Yes |
| Cloudflare | both | Yes | No | Yes (10K neurons) | No | Partial |
| Cohere | both | Yes | Yes (1K calls) | No | No | No |
| Jina AI | embedding | Yes | No (one-time 1M) | No | No | Yes |
| Hugging Face | embedding | Yes (best-effort) | Yes | No | No | Partial |

---

## llm-keypool Configuration Reference

Below is the data this guide generates into `providers.json`. Edit reset cadences here if provider changes limits.

```json
{
  "providers": {
    "groq": {
      "category": ["general_purpose"],
      "base_url": "https://api.groq.com/openai/v1",
      "openai_compatible": true,
      "free_tier": true,
      "limits": {
        "rpm": 30,
        "tpm": 6000,
        "rpd": 14400
      },
      "quota_reset": {
        "rpm_tpm": "rolling",
        "rpd": "daily_utc_midnight"
      },
      "quota_api": "headers",
      "quota_headers": {
        "remaining_requests": "x-ratelimit-remaining-requests",
        "remaining_tokens": "x-ratelimit-remaining-tokens"
      },
      "default_model": "llama-3.3-70b-versatile",
      "models": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "mixtral-8x7b-32768"
      ]
    },
    "google_ai_studio": {
      "category": ["general_purpose", "embedding"],
      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
      "openai_compatible": true,
      "free_tier": true,
      "limits": {
        "rpm": 10,
        "tpm": 250000,
        "rpd": 500
      },
      "quota_reset": {
        "rpm_tpm": "rolling",
        "rpd": "daily_pacific_midnight"
      },
      "quota_api": "headers_on_429",
      "quota_headers": {
        "remaining_requests": "x-ratelimit-remaining-requests",
        "remaining_tokens": "x-ratelimit-remaining-tokens",
        "reset_requests": "x-ratelimit-reset-requests"
      },
      "default_model": "gemini-2.5-flash",
      "default_embedding_model": "text-embedding-005",
      "models": {
        "general_purpose": ["gemini-2.5-flash", "gemini-2.0-flash"],
        "embedding": ["text-embedding-005", "gemini-embedding-exp-03-07"]
      }
    },
    "cerebras": {
      "category": ["general_purpose"],
      "base_url": "https://api.cerebras.ai/v1",
      "openai_compatible": true,
      "free_tier": true,
      "limits": {
        "rpm": 30,
        "tpm": 60000,
        "tokens_per_day": 1000000,
        "max_context_tokens": 8192
      },
      "quota_reset": {
        "rpm_tpm": "rolling_token_bucket",
        "tokens_per_day": "daily_utc_midnight"
      },
      "quota_api": "none",
      "default_model": "llama3.3-70b",
      "models": [
        "qwen-3-235b",
        "gpt-oss-120b",
        "llama3.3-70b",
        "llama3.1-8b"
      ]
    },
    "sambanova": {
      "category": ["general_purpose"],
      "base_url": "https://api.sambanova.ai/v1",
      "openai_compatible": true,
      "free_tier": true,
      "limits": {
        "rpm_per_model": {
          "Meta-Llama-3.1-8B-Instruct": 30,
          "Meta-Llama-3.3-70B-Instruct": 20,
          "Qwen2.5-72B-Instruct": 20,
          "Meta-Llama-3.1-405B-Instruct": 10
        }
      },
      "quota_reset": {
        "rpm": "rolling"
      },
      "quota_api": "none",
      "default_model": "Meta-Llama-3.3-70B-Instruct",
      "models": [
        "Meta-Llama-3.1-8B-Instruct",
        "Meta-Llama-3.3-70B-Instruct",
        "Qwen2.5-72B-Instruct",
        "Meta-Llama-3.1-405B-Instruct"
      ]
    },
    "mistral": {
      "category": ["general_purpose"],
      "base_url": "https://api.mistral.ai/v1",
      "openai_compatible": true,
      "free_tier": true,
      "limits": {
        "rpm": 2,
        "tpm": 500000,
        "tokens_per_month": 1000000000
      },
      "quota_reset": {
        "rpm_tpm": "rolling",
        "monthly_token_cap": "first_of_calendar_month"
      },
      "quota_api": "none",
      "default_model": "mistral-large-latest",
      "models": [
        "mistral-large-latest",
        "mistral-small-latest",
        "codestral-latest",
        "open-mistral-7b",
        "open-mixtral-8x7b"
      ]
    },
    "openrouter": {
      "category": ["general_purpose"],
      "base_url": "https://openrouter.ai/api/v1",
      "openai_compatible": true,
      "free_tier": true,
      "limits": {
        "rpm": 20,
        "rpd": 200
      },
      "quota_reset": {
        "rpm": "rolling",
        "rpd": "daily_utc_midnight"
      },
      "quota_api": "endpoint",
      "quota_endpoint": {
        "url": "https://openrouter.ai/api/v1/credits",
        "method": "GET",
        "auth": "bearer",
        "response_fields": {
          "total_credits": "data.total_credits",
          "total_usage": "data.total_usage"
        }
      },
      "default_model": "meta-llama/llama-3.3-70b-instruct:free",
      "models": [
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemma-3-27b-it:free",
        "mistralai/mistral-7b-instruct:free",
        "microsoft/phi-4:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "nvidia/llama-3.1-nemotron-70b-instruct:free"
      ]
    },
    "cloudflare": {
      "category": ["general_purpose", "embedding"],
      "base_url": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run",
      "openai_compatible": false,
      "requires_account_id": true,
      "free_tier": true,
      "limits": {
        "neurons_per_day": 10000
      },
      "quota_reset": {
        "neurons_per_day": "daily_utc_midnight"
      },
      "quota_api": "none",
      "default_model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
      "default_embedding_model": "@cf/baai/bge-large-en-v1.5",
      "models": {
        "general_purpose": [
          "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
          "@cf/meta/llama-3.1-8b-instruct",
          "@cf/mistral/mistral-7b-instruct-v0.2-lora"
        ],
        "embedding": [
          "@cf/baai/bge-large-en-v1.5",
          "@cf/baai/bge-base-en-v1.5"
        ]
      }
    },
    "cohere": {
      "category": ["general_purpose", "embedding"],
      "base_url": "https://api.cohere.com/v2",
      "openai_compatible": false,
      "free_tier": true,
      "limits": {
        "calls_per_month": 1000,
        "rpm_chat": 20,
        "rpm_embed_text": 100,
        "rpm_embed_image": 5,
        "rpm_rerank": 10
      },
      "quota_reset": {
        "rpm": "rolling",
        "monthly_call_cap": "first_of_calendar_month"
      },
      "quota_api": "none",
      "default_model": "command-r-plus-08-2024",
      "default_embedding_model": "embed-v4.0",
      "models": {
        "general_purpose": [
          "command-a-03-2025",
          "command-r-plus-08-2024",
          "command-r-08-2024"
        ],
        "embedding": [
          "embed-v4.0",
          "embed-english-v3.0"
        ]
      }
    },
    "jina": {
      "category": ["embedding"],
      "base_url": "https://api.jina.ai/v1",
      "openai_compatible": true,
      "free_tier": true,
      "limits": {
        "initial_token_grant": 1000000,
        "rpm": 100,
        "tpm": 100000,
        "concurrent_requests": 2
      },
      "quota_reset": {
        "rpm_tpm": "rolling",
        "initial_grant": "one_time_no_reset"
      },
      "quota_api": "none",
      "default_embedding_model": "jina-embeddings-v3",
      "models": [
        "jina-embeddings-v3",
        "jina-colbert-v2",
        "jina-clip-v2"
      ]
    },
    "huggingface": {
      "category": ["embedding"],
      "base_url": "https://api-inference.huggingface.co/v1",
      "openai_compatible": true,
      "free_tier": true,
      "limits": {
        "monthly_credits": "undisclosed",
        "rate": "best_effort"
      },
      "quota_reset": {
        "monthly_credits": "first_of_calendar_month"
      },
      "quota_api": "none",
      "default_embedding_model": "BAAI/bge-large-en-v1.5",
      "models": [
        "BAAI/bge-large-en-v1.5",
        "BAAI/bge-m3",
        "sentence-transformers/all-MiniLM-L6-v2",
        "sentence-transformers/all-mpnet-base-v2",
        "thenlper/gte-large"
      ]
    }
  }
}
```

---

## Key Registration Checklist

- [ ] Groq - console.groq.com - API Keys section
- [ ] Google AI Studio - aistudio.google.com - Get API Key
- [ ] Cerebras - cloud.cerebras.ai - API Keys
- [ ] SambaNova - cloud.sambanova.ai - API section
- [ ] Mistral - console.mistral.ai - API Keys
- [ ] OpenRouter - openrouter.ai - Keys section
- [ ] Cloudflare - dash.cloudflare.com - Workers AI - also note your Account ID
- [ ] Cohere - dashboard.cohere.com - API Keys (get Trial key)
- [ ] Jina - jina.ai/embeddings - auto-generated on page load
- [ ] Hugging Face - huggingface.co/settings/tokens - create token with Inference scope

---

## Notes

- **Together AI** excluded: no persistent free tier as of 2026 (one-time credits only, no recurring reset)
- **Ollama** excluded: local deployment only, no remote API key concept
- **OpenAI / Anthropic** excluded: no free tier
- Provider limits change frequently - re-run survey periodically and update `providers.json`
- Cloudflare requires `ACCOUNT_ID` in addition to API token - store both when registering
