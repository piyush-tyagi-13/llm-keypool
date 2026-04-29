"""Tests for CLI commands via Typer test runner."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from llm_keypool.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own DB via env var."""
    db = tmp_path / "cli_test.db"
    monkeypatch.setenv("LLM_KEYPOOL_DB", str(db))
    yield db


def test_status_empty():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "No keys registered" in result.output


def test_add_key_success():
    result = runner.invoke(app, [
        "add",
        "--provider", "groq",
        "--key", "gsk_testkey123",
        "--category", "general_purpose",
    ])
    assert result.exit_code == 0
    assert "groq" in result.output.lower()


def test_add_key_unknown_provider():
    result = runner.invoke(app, [
        "add",
        "--provider", "unknown_provider_xyz",
        "--key", "some_key",
    ])
    assert result.exit_code != 0
    assert "unknown" in result.output.lower() or "Unknown" in result.output


def test_add_key_then_status_shows_it():
    runner.invoke(app, [
        "add", "--provider", "groq", "--key", "gsk_test", "--category", "general_purpose",
    ])
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "groq" in result.output


def test_add_key_with_model():
    result = runner.invoke(app, [
        "add",
        "--provider", "groq",
        "--key", "gsk_testkey",
        "--model", "llama-3.1-8b-instant",
    ])
    assert result.exit_code == 0


def test_add_duplicate_key_fails():
    runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_same"])
    result = runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_same"])
    assert result.exit_code != 0
    assert "already" in result.output.lower()


def test_deactivate_key():
    runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_deact_test"])
    result = runner.invoke(app, ["deactivate", "--id", "1"])
    assert result.exit_code == 0
    assert "deactivated" in result.output.lower()


def test_deactivate_nonexistent_key():
    result = runner.invoke(app, ["deactivate", "--id", "9999"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_clear_cooldown():
    runner.invoke(app, ["add", "--provider", "groq", "--key", "gsk_cooldown_test"])
    result = runner.invoke(app, ["clear-cooldown", "--id", "1"])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()


def test_clear_cooldown_nonexistent():
    result = runner.invoke(app, ["clear-cooldown", "--id", "9999"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_providers_lists_known_providers():
    result = runner.invoke(app, ["providers"])
    assert result.exit_code == 0
    for p in ["groq", "mistral", "openrouter", "cohere"]:
        assert p in result.output


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "llm-keypool" in result.output.lower() or "key pool" in result.output.lower()


def test_status_shows_registered_key_details():
    runner.invoke(app, [
        "add", "--provider", "groq", "--key", "gsk_status_test",
        "--model", "llama-3.3-70b-versatile",
    ])
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "groq" in result.output
    assert "llama-3.3-70b" in result.output  # Rich may truncate long model names in table
