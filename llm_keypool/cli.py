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

# All known capabilities
KNOWN_CAPABILITIES = [
    "general_purpose",
    "agentic",
    "fast",
    "code",
    "vision",
    "large_context",
]


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
    table.add_column("ID",           style="dim",  width=4)
    table.add_column("Provider",     min_width=14)
    table.add_column("Capabilities", min_width=22)
    table.add_column("Model",        min_width=22)
    table.add_column("Active",       width=7)
    table.add_column("Req Today",    width=10, justify="right")
    table.add_column("Cooldown Until", min_width=22)

    for k in keys:
        in_cooldown  = bool(k["cooldown_until"] and k["cooldown_until"] > now)
        active_str   = "[green]yes[/green]" if k["is_active"] else "[red]no[/red]"
        cooldown_str = (
            f"[yellow]{k['cooldown_until'][:19]}[/yellow]"
            if in_cooldown else "[dim]-[/dim]"
        )
        caps = ", ".join(store.parse_capabilities(k))
        table.add_row(
            str(k["id"]),
            k["provider"],
            caps,
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
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name (groq, cerebras, mistral, google, ...)"),
    key: str = typer.Option(..., "--key", "-k", help="API key string"),
    capabilities: str = typer.Option(
        "general_purpose",
        "--capabilities", "--cap",
        help="Comma-separated capabilities: general_purpose, agentic, fast, code, vision, large_context",
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name (uses provider default if omitted)"),
    # deprecated
    category: Optional[str] = typer.Option(None, "--category", "-c", hidden=True, help="Deprecated: use --capabilities"),
):
    """Register a new API key for a provider."""
    configs = _load_provider_configs()
    provider = provider.lower().strip()

    if provider not in configs:
        console.print(f"[red]Unknown provider '{provider}'[/red]")
        console.print(f"Supported: {', '.join(sorted(configs.keys()))}")
        raise typer.Exit(1)

    # parse capabilities
    if category and capabilities == "general_purpose":
        # user passed --category (deprecated), use it
        caps = [category.strip()]
    else:
        caps = [c.strip() for c in capabilities.split(",") if c.strip()]

    unknown = [c for c in caps if c not in KNOWN_CAPABILITIES]
    if unknown:
        console.print(f"[yellow]Warning: unknown capabilities: {', '.join(unknown)}[/yellow]")
        console.print(f"Known: {', '.join(KNOWN_CAPABILITIES)}")

    store = KeyStore()
    result = store.register_key(
        provider=provider,
        api_key=key,
        capabilities=caps,
        model=model or None,
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
    """List all supported providers and their capabilities."""
    configs = _load_provider_configs()

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Provider",      min_width=14)
    table.add_column("Capabilities",  min_width=30)
    table.add_column("Default Model", min_width=26)
    table.add_column("OpenAI Compat", width=14, justify="center")

    for name, cfg in sorted(configs.items()):
        caps    = ", ".join(cfg.get("capabilities", cfg.get("category", [])))
        default = cfg.get("default_model", "-")
        compat  = "[green]yes[/green]" if cfg.get("openai_compatible") else "[dim]no[/dim]"
        table.add_row(name, caps, default or "[dim]-[/dim]", compat)

    console.print(table)


@app.command()
def audit(
    subscriber: Optional[str] = typer.Option(None, "--subscriber", "-s", help="Filter by subscriber ID"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to look back"),
    summary: bool = typer.Option(False, "--summary", help="Show aggregate summary instead of raw rows"),
):
    """Show audit log of LLM calls by subscriber."""
    store = KeyStore()

    if summary:
        rows = store.get_audit_summary(days=days)
        if not rows:
            console.print(f"[yellow]No audit data in last {days} days.[/yellow]")
            return
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Subscriber",    min_width=22)
        table.add_column("Requests",      width=10, justify="right")
        table.add_column("Tokens In",     width=12, justify="right")
        table.add_column("Tokens Out",    width=12, justify="right")
        table.add_column("Total Tokens",  width=14, justify="right")
        table.add_column("Errors",        width=8,  justify="right")
        for r in rows:
            table.add_row(
                r["subscriber_id"],
                str(r["requests"]),
                str(r["tokens_in"] or 0),
                str(r["tokens_out"] or 0),
                str(r["tokens_total"] or 0),
                str(r["errors"] or 0),
            )
        console.print(table)
        console.print(f"[dim]Last {days} days[/dim]")
        return

    rows = store.get_audit_log(subscriber_id=subscriber, days=days)
    if not rows:
        msg = f"[yellow]No audit entries"
        if subscriber:
            msg += f" for subscriber '{subscriber}'"
        msg += f" in last {days} days.[/yellow]"
        console.print(msg)
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Time",         min_width=19)
    table.add_column("Subscriber",   min_width=20)
    table.add_column("Provider",     min_width=12)
    table.add_column("Model",        min_width=22)
    table.add_column("Tok In",       width=8,  justify="right")
    table.add_column("Tok Out",      width=8,  justify="right")
    table.add_column("ms",           width=6,  justify="right")
    table.add_column("OK",           width=5,  justify="center")

    for r in rows:
        ok = "[green]y[/green]" if r["success"] else "[red]n[/red]"
        table.add_row(
            (r["ts"] or "")[:19],
            r["subscriber_id"] or "",
            r["provider"] or "",
            r["model"] or "",
            str(r["tokens_in"] or 0),
            str(r["tokens_out"] or 0),
            str(r["latency_ms"] or 0),
            ok,
        )

    console.print(table)
    console.print(f"[dim]{len(rows)} entries, last {days} days[/dim]")


@app.command()
def gui():
    """Launch the Textual TUI."""
    try:
        from llm_keypool.tui import run
    except ImportError:
        console.print("[red]Textual not installed.[/red] Run: pip install 'llm-keypool[gui]'")
        raise typer.Exit(1)
    run()


@app.command()
def proxy(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    capabilities: str = typer.Option(
        "general_purpose",
        "--capabilities", "--cap",
        help="Comma-separated capabilities filter (default: general_purpose)",
    ),
    rotate_every: int = typer.Option(5, "--rotate-every", help="Requests per key before rotating"),
    # deprecated
    category: Optional[str] = typer.Option(None, "--category", "-c", hidden=True),
):
    """Start OpenAI-compatible proxy at http://localhost:8000/v1."""
    try:
        import uvicorn
        from llm_keypool.proxy import make_app
    except ImportError:
        console.print("[red]Proxy deps missing.[/red] Run: pip install 'llm-keypool[proxy]'")
        raise typer.Exit(1)

    if category and capabilities == "general_purpose":
        caps = [category.strip()]
    else:
        caps = [c.strip() for c in capabilities.split(",") if c.strip()]

    console.print(f"[green]llm-keypool proxy[/green] listening on [cyan]http://{host}:{port}/v1[/cyan]")
    console.print(f"Capabilities: [cyan]{', '.join(caps)}[/cyan] | Rotate every: [cyan]{rotate_every}[/cyan] requests")
    uvicorn.run(make_app(capabilities=caps, rotate_every=rotate_every), host=host, port=port)
