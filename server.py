import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from llm_aggregator.key_store import KeyStore
from llm_aggregator.rotator import Rotator

CONFIG_PATH = Path(__file__).parent / "llm_aggregator" / "config" / "providers.json"
with open(CONFIG_PATH) as f:
    PROVIDER_CONFIGS: dict = json.load(f)["providers"]

store = KeyStore()
rotator = Rotator(store, PROVIDER_CONFIGS)

mcp = FastMCP("llm-aggregator")

VALID_CATEGORIES = ("embedding", "general_purpose")


@mcp.tool()
def get_key(category: str) -> str:
    """
    Get the best available API key for a given model category.

    Returns JSON containing key_id, provider, api_key, base_url, model,
    openai_compatible, and extra_params (e.g. account_id for Cloudflare).

    You MUST call report_usage after each API call to keep quota state accurate.

    Args:
        category: 'embedding' or 'general_purpose'
    """
    if category not in VALID_CATEGORIES:
        return json.dumps({
            "error": f"Invalid category '{category}'",
            "valid": list(VALID_CATEGORIES),
        })

    result = rotator.get_best_key(category)
    if result:
        return json.dumps(result)

    # All keys exhausted or none registered
    all_keys = store.get_all_keys()
    cat_keys = [k for k in all_keys if k["category"] == category and k["is_active"]]
    if not cat_keys:
        return json.dumps({
            "error": "no_keys_registered",
            "message": f"No {category} keys registered. Use register_key to add one.",
        })

    earliest = rotator.get_earliest_retry(category)
    return json.dumps({
        "error": "all_keys_exhausted",
        "retry_after": earliest,
        "message": f"All {category} keys are rate-limited. Earliest retry: {earliest}",
    })


@mcp.tool()
def register_key(
    provider: str,
    api_key: str,
    category: str = "",
    model: str = "",
    extra_params: str = "{}",
) -> str:
    """
    Register an API key for a provider (one-time setup).

    Supported providers: groq, google_ai_studio, cerebras, sambanova, mistral,
    openrouter, cloudflare, cohere, jina, huggingface

    Call get_providers to see available models per provider before registering.
    If model is omitted, the provider's default model is used at get_key time.

    Cloudflare requires extra_params: '{"account_id": "your-account-id"}'
    Multi-category providers (google_ai_studio, cohere, cloudflare) require
    explicit category.

    Args:
        provider:     Provider name (see list above)
        api_key:      API key string
        category:     'embedding' or 'general_purpose' (auto-detected for single-category providers)
        model:        Specific model to use with this key (optional, uses provider default if omitted)
        extra_params: JSON string of provider-specific extras
    """
    provider = provider.lower().strip()

    if provider not in PROVIDER_CONFIGS:
        return json.dumps({
            "error": f"Unknown provider '{provider}'",
            "supported": list(PROVIDER_CONFIGS.keys()),
        })

    cfg = PROVIDER_CONFIGS[provider]
    provider_categories: list[str] = cfg.get("category", [])

    if not category:
        if len(provider_categories) == 1:
            category = provider_categories[0]
        else:
            return json.dumps({
                "error": f"Provider '{provider}' supports multiple categories. Specify category.",
                "supported_categories": provider_categories,
            })

    if category not in provider_categories:
        return json.dumps({
            "error": f"Provider '{provider}' does not support category '{category}'",
            "supported_categories": provider_categories,
        })

    # Warn if model not in known list, but allow it (user may have newer models)
    model_warning = None
    if model:
        provider_models = cfg.get("models", [])
        if isinstance(provider_models, dict):
            valid_models = provider_models.get(category, [])
        else:
            valid_models = provider_models
        if valid_models and model not in valid_models:
            model_warning = f"Model '{model}' not in known list {valid_models} - proceeding anyway"

    try:
        extra = json.loads(extra_params)
    except json.JSONDecodeError:
        return json.dumps({"error": "extra_params must be valid JSON string"})

    required_extra: list[str] = cfg.get("requires_extra", [])
    missing = [k for k in required_extra if k not in extra]
    if missing:
        return json.dumps({
            "error": f"Provider '{provider}' requires extra_params fields: {missing}",
            "example": json.dumps({k: f"your-{k}" for k in required_extra}),
        })

    result = store.register_key(provider, api_key, category, model or None, extra)
    if model_warning:
        result["warning"] = model_warning
    return json.dumps(result)


@mcp.tool()
def report_usage(
    key_id: int,
    tokens_used: int = 0,
    was_429: bool = False,
    was_error: bool = False,
) -> str:
    """
    Report the result of an API call. MUST be called after every use of a key.

    On 429: key enters cooldown, next get_key call returns a different key.
    On success: token/request counters are updated for quota tracking.

    Args:
        key_id:      key_id from the get_key response
        tokens_used: total tokens consumed (prompt + completion)
        was_429:     True if the provider returned HTTP 429
        was_error:   True if any other error occurred (key stays active)
    """
    key = store.get_key_by_id(key_id)
    if not key:
        return json.dumps({"error": f"Key ID {key_id} not found"})

    if was_429:
        cooldown_until = rotator.handle_429(key_id, key["provider"])
        return json.dumps({
            "success": True,
            "action": "key_cooled_down",
            "provider": key["provider"],
            "cooldown_until": cooldown_until,
        })

    rotator.handle_success(key_id, tokens_used)
    return json.dumps({"success": True, "action": "usage_recorded", "tokens_used": tokens_used})


@mcp.tool()
def list_keys() -> str:
    """
    List all registered keys and their current quota usage and cooldown status.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    keys = store.get_all_keys()
    if not keys:
        return json.dumps({"keys": [], "message": "No keys registered."})

    summary = []
    for k in keys:
        in_cooldown = bool(k["cooldown_until"] and k["cooldown_until"] > now)
        summary.append({
            "id": k["id"],
            "provider": k["provider"],
            "category": k["category"],
            "model": k["model"] or "(provider default)",
            "active": bool(k["is_active"]),
            "in_cooldown": in_cooldown,
            "cooldown_until": k["cooldown_until"] if in_cooldown else None,
            "requests_today": k["requests_today"],
            "requests_month": k["requests_month"],
            "tokens_today": k["tokens_used_today"],
            "tokens_month": k["tokens_used_month"],
            "last_used_at": k["last_used_at"],
            "api_key_preview": k["api_key"][:8] + "..." if len(k["api_key"]) > 8 else "***",
        })

    return json.dumps({"keys": summary, "total": len(summary)})


@mcp.tool()
def get_providers() -> str:
    """
    List all supported providers with their categories, limits, and quota reset schedules.
    Useful for knowing which providers to sign up for and what limits to expect.
    """
    result = {}
    for name, cfg in PROVIDER_CONFIGS.items():
        result[name] = {
            "categories": cfg.get("category", []),
            "base_url": cfg.get("base_url", ""),
            "openai_compatible": cfg.get("openai_compatible", False),
            "limits": cfg.get("limits", {}),
            "quota_reset": cfg.get("quota_reset", {}),
            "quota_api": cfg.get("quota_api", "none"),
            "default_model": cfg.get("default_model") or cfg.get("default_embedding_model", ""),
            "models": cfg.get("models", []),
        }
    return json.dumps(result, indent=2)


@mcp.tool()
def update_key(
    key_id: int,
    model: str = "",
    api_key: str = "",
) -> str:
    """
    Update an existing key's model or API key value in-place.

    Use this instead of deactivate + re-register when you only need to change
    the model a key uses, or rotate to a new API key string for the same provider.

    At least one of model or api_key must be provided.

    Args:
        key_id:  key_id from list_keys
        model:   New model name (empty string = no change)
        api_key: New API key string (empty string = no change)
    """
    key = store.get_key_by_id(key_id)
    if not key:
        return json.dumps({"error": f"Key ID {key_id} not found"})

    new_model = model.strip() if model.strip() else None
    new_api_key = api_key.strip() if api_key.strip() else None

    if new_model is None and new_api_key is None:
        return json.dumps({"error": "Provide at least one of model or api_key to update"})

    # Warn if model not in known list
    warning = None
    if new_model:
        cfg = PROVIDER_CONFIGS.get(key["provider"], {})
        provider_models = cfg.get("models", [])
        if isinstance(provider_models, dict):
            valid_models = provider_models.get(key["category"], [])
        else:
            valid_models = provider_models
        if valid_models and new_model not in valid_models:
            warning = f"Model '{new_model}' not in known list {valid_models} - proceeding anyway"

    store.update_key(key_id, model=new_model, api_key=new_api_key)

    result = {
        "success": True,
        "key_id": key_id,
        "provider": key["provider"],
        "updated": {},
    }
    if new_model is not None:
        result["updated"]["model"] = new_model
    if new_api_key is not None:
        result["updated"]["api_key"] = new_api_key[:8] + "..."
    if warning:
        result["warning"] = warning
    return json.dumps(result)


@mcp.tool()
def deactivate_key(key_id: int) -> str:
    """
    Permanently deactivate a key (e.g. revoked or expired).
    Use report_usage with was_429=True for temporary rate limits instead.

    Args:
        key_id: key_id from list_keys
    """
    key = store.get_key_by_id(key_id)
    if not key:
        return json.dumps({"error": f"Key ID {key_id} not found"})
    store.deactivate_key(key_id)
    return json.dumps({
        "success": True,
        "message": f"Key {key_id} ({key['provider']}) deactivated",
    })


@mcp.tool()
def clear_cooldown(key_id: int) -> str:
    """
    Manually clear a key's cooldown (e.g. after quota reset confirmed).

    Args:
        key_id: key_id from list_keys
    """
    key = store.get_key_by_id(key_id)
    if not key:
        return json.dumps({"error": f"Key ID {key_id} not found"})
    store.clear_cooldown(key_id)
    return json.dumps({
        "success": True,
        "message": f"Cooldown cleared for key {key_id} ({key['provider']})",
    })


@mcp.tool()
async def complete(
    messages: str,
    category: str = "general_purpose",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """
    Send a chat completion request through the aggregator.

    Automatically selects the best available key, rotates on 429, retries
    transparently. Caller never manages keys or providers.

    Args:
        messages:    JSON array of {role, content} objects.
                     Roles: 'system', 'user', 'assistant'.
        category:    'general_purpose' (default) or 'embedding' (use embed tool instead).
        max_tokens:  Max tokens in the response (default 1024).
        temperature: Sampling temperature 0.0-2.0 (default 0.7).

    Returns JSON: {text, provider, model, tokens_used}
    """
    from llm_aggregator.providers.dispatch import complete as _complete

    if category not in VALID_CATEGORIES:
        return json.dumps({"error": f"Invalid category '{category}'", "valid": list(VALID_CATEGORIES)})

    try:
        msgs = json.loads(messages)
        if not isinstance(msgs, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"error": "messages must be a JSON array: [{\"role\": \"user\", \"content\": \"...\"}]"})

    result, key_data = await _complete(
        rotator, category=category, messages=msgs,
        max_tokens=max_tokens, temperature=temperature,
    )

    if result.error:
        return json.dumps({"error": result.error})

    return json.dumps({
        "text": result.text,
        "provider": key_data["provider"],
        "model": key_data["model"],
        "tokens_used": result.tokens_used,
    })


@mcp.tool()
async def embed(
    texts: str,
    category: str = "embedding",
) -> str:
    """
    Generate embeddings through the aggregator.

    Automatically selects the best available embedding key, rotates on 429.

    Args:
        texts:    JSON array of strings to embed.
        category: 'embedding' (default).

    Returns JSON: {embeddings: [[float, ...], ...], provider, model, tokens_used}
    """
    from llm_aggregator.providers.dispatch import embed as _embed

    try:
        text_list = json.loads(texts)
        if not isinstance(text_list, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"error": "texts must be a JSON array of strings"})

    result, key_data = await _embed(rotator, category=category, texts=text_list)

    if result.error:
        return json.dumps({"error": result.error})

    return json.dumps({
        "embeddings": result.embeddings,
        "provider": key_data["provider"],
        "model": key_data["model"],
        "tokens_used": result.tokens_used,
        "count": len(result.embeddings),
    })


if __name__ == "__main__":
    mcp.run()
