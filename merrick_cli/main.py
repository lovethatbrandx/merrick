"""Merrick CLI — manage your memory daemon from the terminal.

Usage:
    merrick status
    merrick devices
    merrick keys
    merrick keys create
    merrick memory write <content>
    merrick memory search <query>
    merrick memory export
    merrick sync
    merrick doctor
"""

from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from merrick_cli import __version__
from merrick_cli.client import MerrickClient
from merrick_cli.config import MERRICK_URL

console = Console()


def _get_client(ctx: click.Context) -> MerrickClient:
    """Retrieve the client from the click context."""
    return ctx.obj["client"]


def _handle_error(e: Exception, action: str) -> None:
    """Pretty-print an HTTP or connection error."""
    from httpx import HTTPStatusError, ConnectError, ConnectTimeout

    if isinstance(e, ConnectError):
        console.print(
            Panel(
                f"[bold red]Cannot connect to Merrick at {MERRICK_URL}[/]\n\n"
                "Is the server running? Try: [cyan]merrick doctor[/]",
                title="Connection Error",
                border_style="red",
            )
        )
    elif isinstance(e, ConnectTimeout):
        console.print(
            Panel(
                f"[bold red]Connection to Merrick timed out ({MERRICK_URL})[/]",
                title="Timeout",
                border_style="red",
            )
        )
    elif isinstance(e, HTTPStatusError):
        status = e.response.status_code
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        console.print(f"[bold red]{action} failed[/] — HTTP {status}: {detail}")
    else:
        console.print(f"[bold red]{action} failed[/]: {e}")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════
# Root group
# ═══════════════════════════════════════════════════════════════════════

@click.group()
@click.option("--url", envvar="MERRICK_URL", default=MERRICK_URL, help="Merrick server URL")
@click.version_option(version=__version__, prog_name="merrick")
@click.pass_context
def cli(ctx: click.Context, url: str) -> None:
    """Merrick — manage your memory daemon from the terminal."""
    ctx.ensure_object(dict)
    ctx.obj["client"] = MerrickClient(base_url=url)


# ═══════════════════════════════════════════════════════════════════════
# merrick status
# ═══════════════════════════════════════════════════════════════════════

@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show health status and counts."""
    client = _get_client(ctx)

    # First check if server is reachable at all
    try:
        health = client.health()
    except Exception as e:
        _handle_error(e, "Status check")
        return

    if health.get("status") != "ok":
        console.print("[bold red]Merrick is not healthy[/]")
        sys.exit(1)

    # Fetch full status
    try:
        data = client.status()
    except Exception as e:
        _handle_error(e, "Status fetch")
        return

    # Build status panel
    lines = []
    lines.append(f"[green]Merrick[/] is running")

    mem0_count = data.get("mem0_count", "?")
    honcho_sessions = data.get("honcho_sessions", "?")
    honcho_conclusions = data.get("honcho_conclusions", "?")
    sync_status = data.get("sync_status", "unknown")
    last_sync = data.get("last_sync")

    lines.append("")
    lines.append(f"  Memories (mem0):     [cyan]{mem0_count}[/]")
    lines.append(f"  Honcho sessions:     [cyan]{honcho_sessions}[/]")
    lines.append(f"  Honcho conclusions:  [cyan]{honcho_conclusions}[/]")
    lines.append(f"  Sync status:         [cyan]{sync_status}[/]")

    if last_sync:
        lines.append(f"  Last sync:           [dim]{last_sync.get('started_at', '?')}[/]")

    console.print(Panel("\n".join(lines), title="Merrick Status", border_style="green"))


# ═══════════════════════════════════════════════════════════════════════
# merrick devices
# ═══════════════════════════════════════════════════════════════════════

@cli.command()
@click.pass_context
def devices(ctx: click.Context) -> None:
    """List all provisioned devices."""
    client = _get_client(ctx)

    try:
        data = client.list_devices()
    except Exception as e:
        _handle_error(e, "List devices")
        return

    device_list = data.get("devices", [])
    if not device_list:
        console.print("[dim]No devices provisioned yet.[/]")
        return

    table = Table(title="Devices", box=box.ROUNDED, show_lines=True)
    table.add_column("Device ID", style="cyan", no_wrap=True)
    table.add_column("Honcho Peer ID", style="green")
    table.add_column("Mem0 User ID", style="magenta")
    table.add_column("Last Seen", style="dim")

    for d in device_list:
        table.add_row(
            d.get("device_id", "?"),
            d.get("honcho_peer_id", "?"),
            d.get("mem0_user_id", "?"),
            d.get("last_seen", "never"),
        )

    console.print(table)
    console.print(f"\n  [dim]{len(device_list)} device(s)[/]")


# ═══════════════════════════════════════════════════════════════════════
# merrick keys
# ═══════════════════════════════════════════════════════════════════════

@cli.group()
@click.pass_context
def keys(ctx: click.Context) -> None:
    """Manage API keys."""


@keys.command("list")
@click.pass_context
def keys_list(ctx: click.Context) -> None:
    """List all API keys."""
    client = _get_client(ctx)

    try:
        data = client.list_keys()
    except Exception as e:
        _handle_error(e, "List keys")
        return

    key_list = data.get("keys", [])
    if not key_list:
        console.print("[dim]No API keys yet.[/]")
        return

    table = Table(title="API Keys", box=box.ROUNDED, show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Prefix", style="dim")
    table.add_column("Device ID", style="green")
    table.add_column("Agent", style="magenta")
    table.add_column("Permissions")
    table.add_column("Active", justify="center")

    for k in key_list:
        active = k.get("active", True)
        active_str = "[green]Yes[/]" if active else "[red]No[/]"
        perms = ", ".join(k.get("permissions", []))
        table.add_row(
            k.get("key_name", "?"),
            k.get("key_prefix", "?"),
            k.get("device_id", "?"),
            k.get("agent_slug", "-") or "-",
            perms,
            active_str,
        )

    console.print(table)
    console.print(f"\n  [dim]{len(key_list)} key(s)[/]")


@keys.command("create")
@click.option("--device-id", prompt="Device ID", help="Device to bind the key to")
@click.option("--name", prompt="Key name", help="Human-readable name for this key")
@click.option("--agent", default=None, help="Agent slug (optional)")
@click.option(
    "--permissions",
    default="read,write",
    help="Comma-separated permissions (default: read,write)",
)
@click.pass_context
def keys_create(
    ctx: click.Context,
    device_id: str,
    name: str,
    agent: str | None,
    permissions: str,
) -> None:
    """Create a new API key. The secret is shown ONCE."""
    client = _get_client(ctx)
    perm_list = [p.strip() for p in permissions.split(",") if p.strip()]

    try:
        data = client.create_key(
            device_id=device_id,
            key_name=name,
            agent_slug=agent,
            permissions=perm_list,
        )
    except Exception as e:
        _handle_error(e, "Create key")
        return

    secret = data.get("secret", "")
    console.print()
    console.print(
        Panel(
            f"[bold green]Key created successfully![/]\n\n"
            f"  Name:    [cyan]{data.get('key_name', '?')}[/]\n"
            f"  ID:      [dim]{data.get('id', '?')}[/]\n"
            f"  Prefix:  [dim]{data.get('key_prefix', '?')}[/]\n\n"
            f"[bold yellow]Your secret key (copy it now — it won't be shown again):[/]\n\n"
            f"  [bold white]{secret}[/]",
            title="API Key Created",
            border_style="yellow",
        )
    )


# ═══════════════════════════════════════════════════════════════════════
# merrick memory
# ═══════════════════════════════════════════════════════════════════════

@cli.group()
@click.pass_context
def memory(ctx: click.Context) -> None:
    """Manage memories."""


@memory.command("write")
@click.argument("content")
@click.option("--source", default="cli", help="Source tag (default: cli)")
@click.option("--user-id", default=None, help="User ID to associate with")
@click.pass_context
def memory_write(ctx: click.Context, content: str, source: str, user_id: str | None) -> None:
    """Write a memory to Merrick."""
    client = _get_client(ctx)

    try:
        data = client.write_memory(content=content, source=source, user_id=user_id)
    except Exception as e:
        _handle_error(e, "Write memory")
        return

    status = data.get("status", "unknown")
    mem0_ok = data.get("results", {}).get("mem0", {}).get("success", False)
    honcho_ok = data.get("results", {}).get("honcho", {}).get("success", False)

    color = "green" if status == "ok" else "yellow"
    console.print(
        f"[{color}]Memory written[/] — "
        f"mem0: {'[green]OK[/]' if mem0_ok else '[red]FAIL[/]'}, "
        f"honcho: {'[green]OK[/]' if honcho_ok else '[red]FAIL[/]'}"
    )


@memory.command("search")
@click.argument("query")
@click.option("--limit", default=10, help="Max results (default: 10)")
@click.pass_context
def memory_search(ctx: click.Context, query: str, limit: int) -> None:
    """Search memories by query."""
    client = _get_client(ctx)

    try:
        data = client.query_memories(query=query)
    except Exception as e:
        _handle_error(e, "Search memories")
        return

    results = data.get("results", [])
    count = data.get("count", len(results))

    if not results:
        console.print("[dim]No results found.[/]")
        return

    # Truncate if needed
    shown = results[:limit]

    table = Table(title=f"Search Results — \"{query}\"", box=box.ROUNDED, show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Source", style="cyan", width=8)
    table.add_column("Content")

    for i, r in enumerate(shown, 1):
        source = r.get("source", "?")
        data_text = r.get("data", "(empty)")
        # Truncate long memories for display
        if len(data_text) > 200:
            data_text = data_text[:197] + "..."
        table.add_row(str(i), source, data_text)

    console.print(table)
    console.print(f"\n  [dim]{count} result(s) total, showing {len(shown)}[/]")


@memory.command("export")
@click.option("--output", "-o", default=None, help="Output file path (default: stdout as JSON)")
@click.option("--category-id", default=None, help="Filter by category UUID")
@click.pass_context
def memory_export(ctx: click.Context, output: str | None, category_id: str | None) -> None:
    """Export all memories as JSON."""
    client = _get_client(ctx)

    try:
        data = client.export_json(category_id=category_id)
    except Exception as e:
        _handle_error(e, "Export memories")
        return

    memories = data.get("memories", [])
    count = data.get("count", len(memories))

    json_str = json.dumps({"memories": memories, "count": count}, indent=2, default=str)

    if output:
        with open(output, "w") as f:
            f.write(json_str)
        console.print(f"[green]Exported[/] {count} memories to [cyan]{output}[/]")
    else:
        console.print(json_str)


# ═══════════════════════════════════════════════════════════════════════
# merrick sync
# ═══════════════════════════════════════════════════════════════════════

@cli.command()
@click.pass_context
def sync(ctx: click.Context) -> None:
    """Trigger a manual sync and show status."""
    client = _get_client(ctx)

    # Trigger
    try:
        trigger_data = client.trigger_sync()
    except Exception as e:
        _handle_error(e, "Trigger sync")
        return

    console.print("[green]Sync triggered.[/]")

    # Show status
    try:
        status_data = client.sync_status()
    except Exception as e:
        _handle_error(e, "Fetch sync status")
        return

    last = status_data.get("last_sync")
    running = status_data.get("running_count", 0)
    state_counts = status_data.get("sync_state_counts", [])

    lines = []
    lines.append(f"  Running syncs:  [cyan]{running}[/]")
    if last:
        lines.append(f"  Last sync:      [dim]{last.get('started_at', '?')}[/]")
        lines.append(f"  Last status:    [cyan]{last.get('status', '?')}[/]")
    if state_counts:
        lines.append("  Sync state:")
        for sc in state_counts:
            lines.append(f"    {sc.get('source', '?')} → {sc.get('target', '?')}: [cyan]{sc.get('cnt', 0)}[/]")

    console.print(Panel("\n".join(lines) or "  [dim]No sync data yet.[/]", title="Sync Status", border_style="blue"))


# ═══════════════════════════════════════════════════════════════════════
# merrick doctor
# ═══════════════════════════════════════════════════════════════════════

@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Check if Merrick is running and diagnose issues."""
    client = _get_client(ctx)

    console.print("[bold]Merrick Doctor[/]\n")

    # 1. Check Merrick health
    console.print("  Checking Merrick... ", end="")
    try:
        health = client.health()
        if health.get("status") == "ok":
            console.print("[green]OK[/]")
        else:
            console.print(f"[red]UNHEALTHY[/] — {health}")
    except Exception as e:
        console.print(f"[red]UNREACHABLE[/]")
        console.print(f"    [dim]{e}[/]")
        console.print(
            f"\n  [bold yellow]Merrick is not running at {MERRICK_URL}[/]\n"
            "  Start it with: [cyan]python app.py[/] or [cyan]docker compose up[/]"
        )
        return

    # 2. Check status (which probes mem0, honcho, etc.)
    console.print("  Checking services... ", end="")
    try:
        status_data = client.status()
    except Exception as e:
        console.print(f"[red]FAILED[/]")
        console.print(f"    [dim]{e}[/]")
        return

    # Parse individual service health from status
    mem0_count = status_data.get("mem0_count")
    honcho_sessions = status_data.get("honcho_sessions")
    honcho_conclusions = status_data.get("honcho_conclusions")

    services_ok = True

    if mem0_count == "error":
        console.print("[red]mem0: ERROR[/]")
        services_ok = False
    else:
        console.print(f"  [green]mem0:[/] {mem0_count} memories")

    if honcho_sessions == "error":
        console.print("  [red]Honcho: ERROR[/]")
        services_ok = False
    else:
        console.print(f"  [green]Honcho:[/] {honcho_sessions} sessions, {honcho_conclusions} conclusions")

    # 3. Check devices
    console.print("  Checking devices... ", end="")
    try:
        devices_data = client.list_devices()
        count = devices_data.get("count", 0)
        console.print(f"[green]{count} device(s)[/]")
    except Exception as e:
        console.print(f"[yellow]Could not list devices: {e}[/]")

    # 4. Check keys
    console.print("  Checking API keys... ", end="")
    try:
        keys_data = client.list_keys()
        count = len(keys_data.get("keys", []))
        console.print(f"[green]{count} key(s)[/]")
    except Exception as e:
        console.print(f"[yellow]Could not list keys: {e}[/]")

    # Summary
    console.print()
    if services_ok:
        console.print("[green]All systems operational.[/]")
    else:
        console.print("[yellow]Some services reported errors. Check the logs.[/]")


# ═══════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
