"""
dlzoom whoami command: prints authenticated Zoom user information.

Prefers Server-to-Server OAuth if configured; otherwise uses user OAuth
tokens saved by `dlzoom login`.
"""

import json
import logging
from typing import Any

import rich_click as click
from rich.console import Console

from dlzoom.config import Config, ConfigError
from dlzoom.exceptions import DlzoomError
from dlzoom.output import OutputFormatter
from dlzoom.zoom_client import ZoomAPIError, ZoomClient
from dlzoom.zoom_user_client import ZoomUserClient
from dlzoom.token_store import load as load_tokens


console = Console()


@click.command()
@click.option("--json", "json_mode", is_flag=True, help="JSON output mode")
@click.option("--verbose", "-v", is_flag=True, help="Verbose mode")
@click.option("--debug", "-d", is_flag=True, help="Debug mode")
def main(json_mode: bool, verbose: bool, debug: bool) -> None:
    """
    whoami - Show the authenticated Zoom user (Server-to-Server credentials required for now).
    """
    # Setup logging level
    log_level = "DEBUG" if debug else ("INFO" if verbose else "WARNING")
    logging.basicConfig(level=getattr(logging, log_level))

    formatter = OutputFormatter("json" if json_mode else "human")

    try:
        cfg = Config()

        # Prefer S2S if configured; else try user tokens
        use_s2s = bool(cfg.zoom_account_id and cfg.zoom_client_id and cfg.zoom_client_secret)
        if use_s2s:
            client: Any = ZoomClient(
                str(cfg.zoom_account_id), str(cfg.zoom_client_id), str(cfg.zoom_client_secret)
            )
            mode = "Server-to-Server OAuth"
        else:
            tokens = load_tokens(cfg.tokens_path)
            if not tokens:
                raise ConfigError(
                    "Not signed in. Run 'dlzoom login' or configure S2S credentials in your environment."
                )
            client = ZoomUserClient(tokens, str(cfg.tokens_path))
            mode = "User OAuth"

        user = client.get_current_user()

        if json_mode:
            print(json.dumps({"status": "success", "mode": mode, "user": user}, indent=2))
            return

        console.print(f"[bold]Auth:[/bold] {mode}")
        name = f"{user.get('first_name','')} {user.get('last_name','')}".strip() or "N/A"
        console.print(f"[bold]Name:[/bold] {name}")
        console.print(f"[bold]Email:[/bold] {user.get('email', 'N/A')}")
        console.print(f"[bold]User ID:[/bold] {user.get('id', 'N/A')}")
        if use_s2s:
            console.print(f"[bold]Account ID:[/bold] {user.get('account_id', 'N/A')}")

    except ConfigError as e:
        if json_mode:
            print(json.dumps({"status": "error", "error": str(e)}, indent=2))
        else:
            formatter.output_error(str(e))
        if debug:
            raise
    except ZoomAPIError as e:
        msg = f"Zoom API error: {e}"
        if json_mode:
            print(json.dumps({"status": "error", "error": msg}, indent=2))
        else:
            formatter.output_error(msg)
        if debug:
            raise
    except DlzoomError as e:
        if json_mode:
            print(json.dumps({"status": "error", "error": e.to_dict()}, indent=2))
        else:
            formatter.output_error(e.message)
            if e.details:
                formatter.output_info(e.details)
        if debug:
            raise
    except Exception as e:
        if json_mode:
            print(json.dumps({"status": "error", "error": str(e)}, indent=2))
        else:
            formatter.output_error(f"Unexpected error: {e}")
        if debug:
            raise
