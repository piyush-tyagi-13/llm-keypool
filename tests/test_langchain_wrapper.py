"""Tests for AggregatorChat and AggregatorEmbeddings - mock-based."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

_tmp_dir = tempfile.mkdtemp()
os.environ["LLM_KEYPOOL_DB"] = str(Path(_tmp_dir) / "wrapper_test.db")

from llm_keypool.langchain_wrapper import AggregatorChat, AggregatorEmbeddings  # noqa: E402


# --- helpers ---

def _make_complete_result(text="hello", tokens=42, provider="groq", model="llama-3.3-70b"):
    from types import SimpleNamespace
    result = SimpleNamespace(text=text, tokens_used=tokens, error=None, embeddings=None)
    key_data = {"provider": provider, "model": model}
    return result, key_data


def _make_embed_result(embeddings=None, provider="jina", model="jina-embeddings-v3"):
    from types import SimpleNamespace
    embs = embeddings or [[0.1, 0.2, 0.3]]
    result = SimpleNamespace(embeddings=embs, tokens_used=10, error=None, text=None)
    key_data = {"provider": provider, "model": model}
    return result, key_data


def _make_error_result(error="quota exceeded"):
    from types import SimpleNamespace
    result = SimpleNamespace(text=None, tokens_used=0, error=error, embeddings=None)
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
        assert params["category"] == "general_purpose"

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

    def test_custom_category(self):
        chat = AggregatorChat(category="embedding")
        assert chat.category == "embedding"

    def test_default_params(self):
        chat = AggregatorChat()
        assert chat.max_tokens == 4096
        assert chat.temperature == 0.7
        assert chat.rotate_every == 5


# --- AggregatorEmbeddings ---

class TestAggregatorEmbeddings:

    @patch("llm_keypool.providers.dispatch.embed", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_embed_documents(self, mock_rotator, mock_embed):
        mock_embed.return_value = _make_embed_result([[0.1, 0.2], [0.3, 0.4]])
        mock_rotator.return_value = MagicMock()

        emb = AggregatorEmbeddings()
        result = emb.embed_documents(["text one", "text two"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2]

    @patch("llm_keypool.providers.dispatch.embed", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_embed_query(self, mock_rotator, mock_embed):
        mock_embed.return_value = _make_embed_result([[0.5, 0.6, 0.7]])
        mock_rotator.return_value = MagicMock()

        emb = AggregatorEmbeddings()
        result = emb.embed_query("search query")

        assert result == [0.5, 0.6, 0.7]

    @patch("llm_keypool.providers.dispatch.embed", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_embed_error_raises(self, mock_rotator, mock_embed):
        mock_embed.return_value = _make_error_result("no embedding keys")
        mock_rotator.return_value = MagicMock()

        emb = AggregatorEmbeddings()
        with pytest.raises(RuntimeError, match="llm-keypool embed error"):
            emb.embed_documents(["text"])

    def test_default_category(self):
        emb = AggregatorEmbeddings()
        assert emb.category == "embedding"

    def test_custom_category(self):
        emb = AggregatorEmbeddings(category="general_purpose")
        assert emb.category == "general_purpose"

    @patch("llm_keypool.providers.dispatch.embed", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_embed_single_text_returns_flat_list(self, mock_rotator, mock_embed):
        mock_embed.return_value = _make_embed_result([[1.0, 2.0, 3.0]])
        mock_rotator.return_value = MagicMock()

        emb = AggregatorEmbeddings()
        result = emb.embed_query("single")
        assert isinstance(result, list)
        assert isinstance(result[0], float)
