import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

from .key_store import KeyStore
from .providers.headers import extract_cooldown


def _next_utc_midnight() -> str:
    now = datetime.now(timezone.utc)
    return (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()


def _next_first_of_month() -> str:
    now = datetime.now(timezone.utc)
    month = now.month + 1
    year  = now.year + (1 if month > 12 else 0)
    month = 1 if month > 12 else month
    return now.replace(
        year=year, month=month, day=1,
        hour=0, minute=0, second=0, microsecond=0,
    ).isoformat()


def _rolling(seconds: int) -> Callable[[], str]:
    def _inner() -> str:
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
    return _inner


_FALLBACK_STRATEGIES = {
    "daily_utc_midnight":      _next_utc_midnight,
    "first_of_calendar_month": _next_first_of_month,
    "rolling_60":              _rolling(60),
    "rolling_65":              _rolling(65),
    "rolling_120":             _rolling(120),
}
_DEFAULT_FALLBACK = _rolling(60)


def _fallback_from_config(cfg: dict) -> Callable[[], str]:
    """Read cooldown_fallback.strategy from provider config; default to rolling 60s."""
    key = cfg.get("cooldown_fallback", {}).get("strategy", "rolling_60")
    return _FALLBACK_STRATEGIES.get(key, _DEFAULT_FALLBACK)


def _score_key(key: dict, cfg: dict) -> float:
    rpd = cfg.get("limits", {}).get("rpd")
    return float(rpd - key["requests_today"]) if rpd else float(-key["requests_today"])


def _resolve_model(cfg: dict, category: str) -> str:
    models = cfg.get("models", {})
    if isinstance(models, list):
        return models[0] if models else ""
    if isinstance(models, dict):
        cat_models = models.get(category, [])
        return cat_models[0] if cat_models else ""
    return cfg.get(f"default_{category}_model") or cfg.get("default_model", "")


class Rotator:
    def __init__(self, store: KeyStore, provider_configs: dict, rotate_every: int = 5):
        self.store = store
        self.configs = provider_configs
        self.rotate_every = rotate_every

        self._order: dict[str, list[int]] = {}
        self._cursor: dict[str, int] = {}
        self._slot_count: dict[int, int] = {}
        self._loaded_categories: set[str] = set()

    def _load_state(self, category: str):
        if category in self._loaded_categories:
            return
        cursor, slot_counts = self.store.load_rotation_state(category)
        self._cursor[category] = cursor
        self._slot_count.update(slot_counts)
        self._loaded_categories.add(category)

    def _persist_state(self, category: str):
        self.store.save_rotation_state(
            category,
            self._cursor.get(category, 0),
            self._slot_count,
        )

    def _ensure_order(self, category: str, active_ids: set[int]):
        self._load_state(category)
        current = self._order.get(category, [])
        if set(current) == active_ids:
            return
        all_keys = self.store.get_all_keys()
        ordered = sorted(
            [k for k in all_keys if k["category"] == category and k["is_active"]],
            key=lambda k: _score_key(k, self.configs.get(k["provider"], {})),
            reverse=True,
        )
        self._order[category] = [k["id"] for k in ordered]
        if category not in self._cursor:
            self._cursor[category] = 0
        else:
            self._cursor[category] %= max(len(self._order[category]), 1)
        for k in ordered:
            self._slot_count.setdefault(k["id"], 0)

    def get_best_key(self, category: str) -> Optional[dict]:
        active = self.store.get_active_keys(category)
        if not active:
            return None

        active_map = {k["id"]: k for k in active}
        self._ensure_order(category, set(active_map.keys()))

        order  = self._order[category]
        cursor = self._cursor.get(category, 0) % len(order)

        reset_done = False
        for _ in range(len(order) + 1):
            key_id = order[cursor % len(order)]
            if key_id in active_map and self._slot_count.get(key_id, 0) < self.rotate_every:
                break
            cursor = (cursor + 1) % len(order)
            if not reset_done and cursor == self._cursor.get(category, 0) % len(order):
                for kid in order:
                    self._slot_count[kid] = 0
                reset_done = True
        else:
            return None

        self._cursor[category] = cursor
        best = active_map[order[cursor]]
        cfg   = self.configs.get(best["provider"], {})
        extra = json.loads(best["extra_params"] or "{}")

        base_url = cfg.get("base_url", "")
        if "{account_id}" in base_url:
            base_url = base_url.format(account_id=extra.get("account_id", ""))

        slot_pos = self._slot_count.get(best["id"], 0) + 1
        return {
            "key_id":            best["id"],
            "provider":          best["provider"],
            "api_key":           best["api_key"],
            "base_url":          base_url,
            "model":             best["model"] or _resolve_model(cfg, category),
            "category":          category,
            "openai_compatible": cfg.get("openai_compatible", True),
            "extra_params":      extra,
            "requests_today":    best["requests_today"],
            "tokens_used_today": best["tokens_used_today"],
            "cycle_position":    slot_pos,
            "rotate_every":      self.rotate_every,
        }

    def handle_429(self, key_id: int, provider: str, headers: dict | None = None) -> str:
        """
        Compute cooldown_until for a 429 response.
        Header-derived reset time takes priority; falls back to config-driven strategy.
        """
        headers = headers or {}
        cooldown = extract_cooldown(provider, headers, was_429=True)
        if cooldown is None:
            cfg = self.configs.get(provider, {})
            cooldown = _fallback_from_config(cfg)()
        self.store.record_usage(key_id, tokens=0, was_429=True, cooldown_until=cooldown)
        self._slot_count[key_id] = self._slot_count.get(key_id, 0) + 1
        self._persist_state_for_key(key_id)
        return cooldown

    def handle_success(
        self,
        key_id: int,
        tokens_used: int,
        headers: dict | None = None,
        provider: str = "",
    ):
        """
        Record a successful call. If headers indicate quota exhaustion (remaining == 0),
        set a proactive cooldown so the key is skipped until the window resets.
        """
        headers = headers or {}
        cooldown = extract_cooldown(provider, headers, was_429=False) if provider else None
        self.store.record_usage(key_id, tokens=tokens_used, was_429=False, cooldown_until=cooldown)
        self._slot_count[key_id] = self._slot_count.get(key_id, 0) + 1
        self._persist_state_for_key(key_id)

    def _persist_state_for_key(self, key_id: int):
        key = self.store.get_key_by_id(key_id)
        if key:
            self._persist_state(key["category"])

    def get_earliest_retry(self, category: str) -> Optional[str]:
        all_keys = self.store.get_all_keys()
        cooldowns = [
            k["cooldown_until"] for k in all_keys
            if k["category"] == category and k["is_active"] and k["cooldown_until"]
        ]
        return min(cooldowns) if cooldowns else None
