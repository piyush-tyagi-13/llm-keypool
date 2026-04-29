import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# DB lives at ~/.llm-keypool/keys.db by default; override via LLM_KEYPOOL_DB env var
_NEW_DB_DEFAULT = Path.home() / ".llm-keypool" / "keys.db"
_OLD_DB_DEFAULT = Path.home() / ".llm-aggregator" / "keys.db"

def _resolve_db_path() -> Path:
    env = os.environ.get("LLM_KEYPOOL_DB") or os.environ.get("LLM_AGGREGATOR_DB")
    if env:
        return Path(env)
    if not _NEW_DB_DEFAULT.exists() and _OLD_DB_DEFAULT.exists():
        import shutil
        _NEW_DB_DEFAULT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_OLD_DB_DEFAULT, _NEW_DB_DEFAULT)
    return _NEW_DB_DEFAULT

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    api_key TEXT NOT NULL,
    category TEXT NOT NULL,
    model TEXT,
    extra_params TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1,
    tokens_used_today INTEGER NOT NULL DEFAULT 0,
    tokens_used_month INTEGER NOT NULL DEFAULT 0,
    requests_today INTEGER NOT NULL DEFAULT 0,
    requests_month INTEGER NOT NULL DEFAULT 0,
    last_429_at TEXT,
    cooldown_until TEXT,
    daily_reset_date TEXT,
    monthly_reset_month TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT,
    UNIQUE(provider, api_key)
);

CREATE TABLE IF NOT EXISTS rotation_state (
    category TEXT PRIMARY KEY,
    cursor INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rotation_slot_counts (
    key_id INTEGER NOT NULL PRIMARY KEY,
    slot_count INTEGER NOT NULL DEFAULT 0
);
"""

MIGRATIONS = [
    "ALTER TABLE api_keys ADD COLUMN model TEXT",
]


class KeyStore:
    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or _resolve_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            for migration in MIGRATIONS:
                try:
                    conn.execute(migration)
                except sqlite3.OperationalError:
                    pass

    # --- key management ---

    def register_key(
        self,
        provider: str,
        api_key: str,
        category: str,
        model: Optional[str],
        extra_params: dict,
    ) -> dict:
        with self._conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO api_keys (provider, api_key, category, model, extra_params) VALUES (?, ?, ?, ?, ?)",
                    (provider, api_key, category, model or None, json.dumps(extra_params)),
                )
                return {"success": True, "message": f"Key registered for {provider} ({category}) model={model or 'default'}"}
            except sqlite3.IntegrityError:
                return {"success": False, "message": f"Key already registered for {provider}. Deactivate existing key first."}

    def get_active_keys(self, category: str) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM api_keys
                   WHERE category = ? AND is_active = 1
                     AND (cooldown_until IS NULL OR cooldown_until < ?)
                   ORDER BY requests_today ASC""",
                (category, now),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_keys(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM api_keys ORDER BY provider, category").fetchall()
            return [dict(r) for r in rows]

    def get_key_by_id(self, key_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
            return dict(row) if row else None

    def record_usage(self, key_id: int, tokens: int, was_429: bool, cooldown_until: Optional[str] = None):
        now = datetime.now(timezone.utc).isoformat()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        month = datetime.now(timezone.utc).strftime("%Y-%m")

        with self._conn() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
            if not row:
                return
            row = dict(row)

            tokens_today   = row["tokens_used_today"] if row["daily_reset_date"] == today else 0
            requests_today = row["requests_today"]    if row["daily_reset_date"] == today else 0
            tokens_month   = row["tokens_used_month"] if row["monthly_reset_month"] == month else 0
            requests_month = row["requests_month"]    if row["monthly_reset_month"] == month else 0

            conn.execute(
                """UPDATE api_keys SET
                    tokens_used_today   = ?,
                    tokens_used_month   = ?,
                    requests_today      = ?,
                    requests_month      = ?,
                    last_used_at        = ?,
                    last_429_at         = CASE WHEN ? THEN ? ELSE last_429_at END,
                    cooldown_until      = ?,
                    daily_reset_date    = ?,
                    monthly_reset_month = ?
                WHERE id = ?""",
                (
                    tokens_today + tokens, tokens_month + tokens,
                    requests_today + 1,    requests_month + 1,
                    now,
                    was_429, now if was_429 else None,
                    cooldown_until,
                    today, month,
                    key_id,
                ),
            )

    def update_key(self, key_id: int, model: Optional[str] = None, api_key: Optional[str] = None) -> bool:
        updates = []
        params = []
        if model is not None:
            updates.append("model = ?")
            params.append(model or None)
        if api_key is not None:
            updates.append("api_key = ?")
            params.append(api_key)
        if not updates:
            return False
        params.append(key_id)
        with self._conn() as conn:
            conn.execute(f"UPDATE api_keys SET {', '.join(updates)} WHERE id = ?", params)
        return True

    def deactivate_key(self, key_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,))

    def clear_cooldown(self, key_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE api_keys SET cooldown_until = NULL WHERE id = ?", (key_id,))

    # --- rotation state persistence ---

    def save_rotation_state(self, category: str, cursor: int, slot_counts: dict[int, int]):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO rotation_state (category, cursor, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(category) DO UPDATE SET cursor=excluded.cursor, updated_at=excluded.updated_at",
                (category, cursor, now),
            )
            for key_id, count in slot_counts.items():
                conn.execute(
                    "INSERT INTO rotation_slot_counts (key_id, slot_count) VALUES (?, ?) "
                    "ON CONFLICT(key_id) DO UPDATE SET slot_count=excluded.slot_count",
                    (key_id, count),
                )

    def load_rotation_state(self, category: str) -> tuple[int, dict[int, int]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT cursor FROM rotation_state WHERE category = ?", (category,)
            ).fetchone()
            cursor = row["cursor"] if row else 0

            rows = conn.execute("SELECT key_id, slot_count FROM rotation_slot_counts").fetchall()
            slot_counts = {r["key_id"]: r["slot_count"] for r in rows}

        return cursor, slot_counts
