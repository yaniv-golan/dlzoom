"""
dlzoom-logout: Remove local tokens.
"""

from __future__ import annotations

import rich_click as click
from rich.console import Console

from dlzoom.config import Config
from dlzoom.token_store import clear as clear_tokens

console = Console()


@click.command()
def main() -> None:
    """Remove local credentials. You can revoke access in Zoom at any time."""
    cfg = Config()
    clear_tokens(cfg.tokens_path)
    console.print("[green]✓ Signed out. Local tokens removed.[/green]")
    console.print(
        "You can also revoke access in Zoom: App Marketplace → Manage → Added Apps → Remove"
    )
