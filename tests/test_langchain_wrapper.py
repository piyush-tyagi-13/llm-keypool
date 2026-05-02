"""Tests for AggregatorChat - mock-based."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

_tmp_dir = tempfile.mkdtemp()
os.environ["LLM_KEYPOOL_DB"] = str(Path(_tmp_dir) / "wrapper_test.db")

from llm_keypool.langchain_wrapper import AggregatorChat  # noqa: E402


# --- helpers ---

def _make_complete_result(text="hello", tokens=42, provider="groq", model="llama-3.3-70b"):
    from types import SimpleNamespace
    result = SimpleNamespace(text=text, tokens_used=tokens, error=None, remaining_requests=100)
    key_data = {
        "provider": provider, "model": model, "key_id": 1,
        "requests_today": 5, "tokens_used_today": 200,
    }
    return result, key_data


def _make_error_result(error="quota exceeded"):
    from types import SimpleNamespace
    result = SimpleNamespace(text=None, tokens_used=0, error=error)
    key_data = {"provider": "groq", "model": "llama-3.3-70b"}
    return result, key_data


# --- AggregatorChat ---

class TestAggregatorChat:

    def test_llm_type(self):
        chat = AggregatorChat()
        assert chat._llm_type == "llm_keypool"

    def test_identifying_params(self):
        chat = AggregatorChat(category="general_purpose")
        params = chat._identifying_params
        assert "keypool/general_purpose" in params["model"]
        assert params["capabilities"] == ["general_purpose"]

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_generate_success(self, mock_rotator, mock_complete):
        mock_complete.return_value = _make_complete_result(text="Paris", tokens=20)
        mock_rotator.return_value = MagicMock()

        chat = AggregatorChat()
        messages = [HumanMessage(content="What is the capital of France?")]
        result = chat._generate(messages)

        assert len(result.generations) == 1
        assert result.generations[0].message.content == "Paris"

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_generate_includes_provider_metadata(self, mock_rotator, mock_complete):
        mock_complete.return_value = _make_complete_result(provider="mistral", model="mistral-large-latest")
        mock_rotator.return_value = MagicMock()

        chat = AggregatorChat()
        result = chat._generate([HumanMessage(content="hello")])

        meta = result.generations[0].message.response_metadata
        assert meta["provider"] == "mistral"
        assert meta["model"] == "mistral-large-latest"

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_generate_token_usage(self, mock_rotator, mock_complete):
        mock_complete.return_value = _make_complete_result(tokens=150)
        mock_rotator.return_value = MagicMock()

        chat = AggregatorChat()
        result = chat._generate([HumanMessage(content="hello")])

        usage = result.generations[0].message.usage_metadata
        assert usage["total_tokens"] == 150

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_generate_error_raises(self, mock_rotator, mock_complete):
        mock_complete.return_value = _make_error_result("all keys exhausted")
        mock_rotator.return_value = MagicMock()

        chat = AggregatorChat()
        with pytest.raises(RuntimeError, match="llm-keypool error"):
            chat._generate([HumanMessage(content="hello")])

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_system_message_forwarded(self, mock_rotator, mock_complete):
        mock_complete.return_value = _make_complete_result()
        mock_rotator.return_value = MagicMock()

        chat = AggregatorChat()
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello"),
        ]
        chat._generate(messages)

        call_args = mock_complete.call_args
        msgs = call_args.kwargs.get("messages") or call_args.args[2]
        roles = [m["role"] for m in msgs]
        assert "system" in roles
        assert "user" in roles

    def test_default_params(self):
        chat = AggregatorChat()
        assert chat.max_tokens == 4096
        assert chat.temperature == 0.7
        assert chat.rotate_every == 5

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_response_metadata_includes_quota_fields(self, mock_rotator, mock_complete):
        mock_complete.return_value = _make_complete_result(tokens=50, provider="groq")
        mock_rotator.return_value = MagicMock()

        chat = AggregatorChat()
        result = chat._generate([HumanMessage(content="hello")])

        meta = result.generations[0].message.response_metadata
        assert "requests_today" in meta
        assert "tokens_used_today" in meta
        assert "remaining_requests" in meta
        assert "key_id" in meta
        assert meta["remaining_requests"] == 100
        assert meta["key_id"] == 1

    def test_pool_status_returns_list(self, tmp_path, monkeypatch):
        import os
        monkeypatch.setenv("LLM_KEYPOOL_DB", str(tmp_path / "ps_test.db"))
        from llm_keypool.key_store import KeyStore
        store = KeyStore()
        store.register_key("groq", "key1", "general_purpose", "llama-3.3-70b-versatile", {})

        chat = AggregatorChat(category="general_purpose")
        status = chat.pool_status()

        assert len(status) == 1
        assert status[0]["provider"] == "groq"
        assert "requests_today" in status[0]
        assert "tokens_used_today" in status[0]
        assert "is_available" in status[0]
        assert status[0]["is_available"] is True
