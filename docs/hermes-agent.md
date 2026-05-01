# Using llm-keypool with Hermes Agent

Run Hermes Agent entirely on free-tier API keys. llm-keypool acts as a local
OpenAI-compatible proxy - Hermes points at it like any other LLM endpoint, and
the proxy handles key rotation, 429 cooldowns, and provider switching
transparently.

---

## How it works

```
hermes-agent
    |
    | OpenAI API calls (http://127.0.0.1:8000/v1)
    v
llm-keypool proxy
    |
    +-- groq key 1  (llama-3.3-70b-versatile)
    +-- groq key 2
    +-- cerebras key (llama3.1-8b)
    +-- mistral key  (ministral-8b)
    +-- openrouter key
```

Main agent, delegated sub-agents, and fallback failover all route through the
same proxy. No code changes to Hermes required.

---

## Prerequisites

- Hermes Agent installed (`hermes --version`)
- Python 3.11+
- Free-tier API keys from one or more supported providers

**Supported free-tier providers:** Groq, Cerebras, Mistral, OpenRouter,
SambaNova, Cohere, Cloudflare, HuggingFace

---

## Step 1 - Install llm-keypool

```bash
pip install 'llm-keypool[proxy]'
```

Verify:

```bash
llm-keypool --help
```

---

## Step 2 - Register API keys

Get free keys from any of the providers above and register them:

```bash
llm-keypool add --provider groq     --key gsk_...
llm-keypool add --provider cerebras --key csk_...
llm-keypool add --provider mistral  --key ...
```

Multiple keys per provider are supported and will be round-robin rotated:

```bash
llm-keypool add --provider groq --key gsk_SECOND_KEY
```

Check your pool:

```bash
llm-keypool status
```

```
╭──────┬──────────┬──────────────────┬────────────────────────┬─────────╮
│ ID   │ Provider │ Category         │ Model                  │ Active  │
├──────┼──────────┼──────────────────┼────────────────────────┼─────────┤
│ 1    │ groq     │ general_purpose  │ llama-3.3-70b-versatile│ yes     │
│ 2    │ cerebras │ general_purpose  │ llama3.1-8b            │ yes     │
╰──────┴──────────┴──────────────────┴────────────────────────┴─────────╯
```

---

## Step 3 - Start the proxy

```bash
llm-keypool proxy
```

```
llm-keypool proxy listening on http://127.0.0.1:8000/v1
Category: general_purpose | Rotate every: 5 requests
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Verify it is working:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","keys_total":2,"keys_active":2}
```

**Keep this terminal open.** Start it in a separate window or as a background
service before launching Hermes.

### Optional flags

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | `8000` | Port to listen on |
| `--host` | `127.0.0.1` | Bind address |
| `--category` | `general_purpose` | Key category to draw from |
| `--rotate-every` | `5` | Requests per key before rotating |

---

## Step 4 - Configure Hermes

Edit `~/.hermes/config.yaml`:

```yaml
# Main agent model
model:
  default: llama-3.3-70b-versatile
  provider: ''
  base_url: 'http://127.0.0.1:8000/v1'
  api_key: 'keypool'

# Delegated sub-agents (delegate_task tool)
delegation:
  model: 'llama-3.3-70b-versatile'
  provider: ''
  base_url: 'http://127.0.0.1:8000/v1'
  api_key: 'keypool'

# Fallback when primary fails (429, 503, overload)
fallback_model:
  provider: ''
  base_url: 'http://127.0.0.1:8000/v1'
  api_key: 'keypool'
  model: 'llama-3.3-70b-versatile'
```

Or use the CLI:

```bash
hermes config set model.default llama-3.3-70b-versatile
hermes config set model.base_url http://127.0.0.1:8000/v1
hermes config set model.api_key keypool
hermes config set model.provider ''
```

---

## Step 5 - Start Hermes

```bash
hermes
```

Hermes will now call the local proxy for all LLM requests. The proxy rotates
through your registered keys automatically.

---

## Requesting a specific model

The `model` field in any request to the proxy is forwarded to the provider. You
can override the default per-request by setting a model that the assigned key
supports:

```bash
hermes config set model.default llama3.1-8b   # faster, lower quality
hermes config set model.default qwen/qwen3-32b # groq-specific
```

Or switch at runtime inside Hermes:

```
/model llama-3.3-70b-versatile
```

---

## Overriding category per request

Send `X-Keypool-Category` header to select a different key pool:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Keypool-Category: general_purpose" \
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"hello"}]}'
```

---

## Running the proxy as a background service (macOS launchd)

Create `~/Library/LaunchAgents/com.llm-keypool.proxy.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.llm-keypool.proxy</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/venv/bin/llm-keypool</string>
    <string>proxy</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/llm-keypool-proxy.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/llm-keypool-proxy.err</string>
</dict>
</plist>
```

Replace `/path/to/venv/bin/llm-keypool` with the output of `which llm-keypool`.

```bash
launchctl load ~/Library/LaunchAgents/com.llm-keypool.proxy.plist
```

The proxy now starts automatically on login.

---

## Troubleshooting

**`Connection refused` on port 8000**
Proxy is not running. Start it with `llm-keypool proxy`.

**`all_keys_exhausted` error**
All keys are in cooldown (daily free-tier limit hit). Check status:
```bash
llm-keypool status
```
Add more keys from other providers or wait for cooldown to clear.

**`no client for provider` error**
The registered key's provider is not supported. Run `llm-keypool providers`
to see the supported list.

**Key stuck in cooldown after quota reset**
```bash
llm-keypool clear-cooldown --id <ID>
```

**Check proxy logs**
The proxy prints every request to stdout. Check the terminal where you ran
`llm-keypool proxy`.

---

## Available models by provider

| Provider | Free-tier models |
|----------|-----------------|
| Groq | llama-3.3-70b-versatile, llama-3.1-8b-instant, qwen/qwen3-32b, gemma2-9b-it |
| Cerebras | llama3.1-8b, llama3.3-70b |
| Mistral | ministral-8b-2512, mistral-small-latest |
| OpenRouter | (varies by key tier) |
| SambaNova | llama-3.3-70b |

Run `llm-keypool providers` for the full list, or `curl http://127.0.0.1:8000/v1/models`
when the proxy is running.
