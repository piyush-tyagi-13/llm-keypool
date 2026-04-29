from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from llm_keypool.key_store import KeyStore

app = typer.Typer(
    help="llm-keypool - free-tier API key pool manager",
    no_args_is_help=True,
)
console = Console()


def _load_provider_configs() -> dict:
    config_path = Path(__file__).parent / "config" / "providers.json"
    with open(config_path) as f:
        return json.load(f)["providers"]


@app.command()
def status():
    """Show all registered keys and their current status."""
    store = KeyStore()
    keys = store.get_all_keys()
    now = datetime.now(timezone.utc).isoformat()

    if not keys:
        console.print("[yellow]No keys registered.[/yellow]")
        console.print("Run: [cyan]llm-keypool add --provider groq --key gsk_...[/cyan]")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("ID",       style="dim",  width=4)
    table.add_column("Provider", min_width=14)
    table.add_column("Category", min_width=16)
    table.add_column("Model",    min_width=22)
    table.add_column("Active",   width=7)
    table.add_column("Req Today", width=10, justify="right")
    table.add_column("Cooldown Until", min_width=22)

    for k in keys:
        in_cooldown = bool(k["cooldown_until"] and k["cooldown_until"] > now)
        active_str  = "[green]yes[/green]" if k["is_active"] else "[red]no[/red]"
        cooldown_str = (
            f"[yellow]{k['cooldown_until'][:19]}[/yellow]"
            if in_cooldown else "[dim]-[/dim]"
        )
        table.add_row(
            str(k["id"]),
            k["provider"],
            k["category"],
            k["model"] or "[dim]default[/dim]",
            active_str,
            str(k["requests_today"]),
            cooldown_str,
            style="" if k["is_active"] else "dim",
        )

    console.print(table)
    console.print(f"[dim]{len(keys)} key(s) total[/dim]")


@app.command()
def add(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name (groq, cerebras, mistral, ...)"),
    key: str = typer.Option(..., "--key", "-k", help="API key string"),
    category: str = typer.Option("general_purpose", "--category", "-c", help="Category: general_purpose or embedding"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name (uses provider default if omitted)"),
):
    """Register a new API key for a provider."""
    configs = _load_provider_configs()
    provider = provider.lower().strip()

    if provider not in configs:
        console.print(f"[red]Unknown provider '{provider}'[/red]")
        console.print(f"Supported: {', '.join(sorted(configs.keys()))}")
        raise typer.Exit(1)

    store = KeyStore()
    result = store.register_key(
        provider=provider,
        api_key=key,
        category=category,
        model=model or None,
        extra_params={},
    )

    if result["success"]:
        console.print(f"[green]✓[/green] {result['message']}")
    else:
        console.print(f"[red]✗[/red] {result['message']}")
        raise typer.Exit(1)


@app.command()
def deactivate(
    id: int = typer.Option(..., "--id", help="Key ID from 'llm-keypool status'"),
):
    """Deactivate a key (revoked or expired). Does not delete it."""
    store = KeyStore()
    key = store.get_key_by_id(id)
    if not key:
        console.print(f"[red]Key ID {id} not found[/red]")
        raise typer.Exit(1)

    if not key["is_active"]:
        console.print(f"[yellow]Key {id} ({key['provider']}) already inactive[/yellow]")
        return

    store.deactivate_key(id)
    console.print(f"[green]✓[/green] Key {id} ({key['provider']}) deactivated")


@app.command(name="clear-cooldown")
def clear_cooldown(
    id: int = typer.Option(..., "--id", help="Key ID from 'llm-keypool status'"),
):
    """Clear a key's cooldown (e.g. after quota reset confirmed)."""
    store = KeyStore()
    key = store.get_key_by_id(id)
    if not key:
        console.print(f"[red]Key ID {id} not found[/red]")
        raise typer.Exit(1)

    store.clear_cooldown(id)
    console.print(f"[green]✓[/green] Cooldown cleared for key {id} ({key['provider']})")


@app.command()
def providers():
    """List all supported providers."""
    configs = _load_provider_configs()

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Provider",       min_width=16)
    table.add_column("Categories",     min_width=20)
    table.add_column("Default Model",  min_width=26)
    table.add_column("OpenAI Compat",  width=14, justify="center")

    for name, cfg in sorted(configs.items()):
        cats    = ", ".join(cfg.get("category", []))
        default = cfg.get("default_model") or cfg.get("default_embedding_model", "-")
        compat  = "[green]yes[/green]" if cfg.get("openai_compatible") else "[dim]no[/dim]"
        table.add_row(name, cats, default or "[dim]-[/dim]", compat)

    console.print(table)



@app.command()
def gui():
    """Launch the Textual TUI."""
    try:
        from llm_keypool.tui import run
    except ImportError:
        console.print("[red]Textual not installed.[/red] Run: pip install 'llm-keypool\\[gui]'")
        raise typer.Exit(1)
    run()
