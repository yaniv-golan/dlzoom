"""
dlzoom-login: Authenticate via hosted auth service, open browser, poll, and store tokens.
"""

from __future__ import annotations

import json
import time
import webbrowser
from typing import Optional

import requests
import rich_click as click
from rich.console import Console

from dlzoom.config import Config
from dlzoom.token_store import Tokens, save as save_tokens


console = Console()


def _normalize_auth_url(url: str) -> str:
    url = url.strip()
    if not url.startswith("https://"):
        raise click.BadParameter("--auth-url must start with https://")
    return url.rstrip("/")


@click.command()
@click.option("--auth-url", help="Advanced: override authentication service URL (must be https)")
def main(auth_url: Optional[str]) -> None:
    """Authenticate with Zoom. Opens your browser for approval."""
    cfg = Config()
    base_auth = _normalize_auth_url(auth_url) if auth_url else cfg.auth_url

    # Start auth
    start_url = f"{base_auth}/zoom/auth/start"
    try:
        r = requests.post(start_url, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        console.print(f"[red]Failed to start auth:[/red] {e}")
        raise SystemExit(1)

    auth_page = str(data.get("auth_url"))
    session_id = str(data.get("session_id"))
    if not auth_page or not session_id:
        console.print("[red]Auth service returned invalid response[/red]")
        raise SystemExit(1)

    console.print("Opening your browser to sign in to Zoom...")
    console.print(f"If the browser does not open, visit:\n[blue]{auth_page}[/blue]")
    try:
        webbrowser.open(auth_page)
    except Exception:
        # Ignore failures; user can copy URL
        pass

    # Polling strategy: 1s for 10s, 2s up to 2m, 5s up to 10m
    start_time = time.time()
    attempt = 0
    last_hint = 0.0
    while True:
        elapsed = time.time() - start_time
        if elapsed > 600:
            console.print("[red]Login timed out. Please run: dlzoom login again[/red]")
            raise SystemExit(1)

        poll_url = f"{base_auth}/zoom/auth/poll?id={session_id}"
        try:
            pr = requests.get(poll_url, timeout=30)
        except Exception:
            # transient; continue
            pr = None

        if pr is not None and pr.status_code == 200:
            # Poll returns either {status: "pending"} or the actual token JSON
            try:
                token_json = pr.json()
            except Exception:
                try:
                    token_json = json.loads(pr.text)
                except Exception:
                    token_json = {}

            # If no access_token present, keep polling
            access = token_json.get("access_token")
            refresh = token_json.get("refresh_token")
            if not access or not refresh:
                # Still pending or invalid payload; occasionally remind the user (start after 10s)
                nowt = time.time()
                if elapsed >= 10 and (nowt - last_hint >= 20):
                    console.print(
                        "Still waiting for approval... If the flow doesn't proceed or you saw an error page, "
                        "open this authorization link to continue:\n"
                        f"[blue]{auth_page}[/blue]\n"
                        "Then press Ctrl+C here and run 'dlzoom login' again."
                    )
                    last_hint = nowt
            else:
                now = int(time.time())
                expires_in = int(token_json.get("expires_in", 3600))
                tokens = Tokens(
                    token_type=str(token_json.get("token_type", "Bearer")),
                    access_token=str(access),
                    refresh_token=str(refresh),
                    expires_at=now + expires_in,
                    issued_at=now,
                    scope=token_json.get("scope"),
                    auth_url=base_auth,
                )
                save_tokens(cfg.tokens_path, tokens)
                console.print("[green]✓ Signed in. Tokens saved.[/green]")
                return

        if pr is not None and pr.status_code == 410:
            console.print("[red]Session expired. Please run: dlzoom login again[/red]")
            raise SystemExit(1)

        # sleep according to schedule
        if elapsed < 10:
            time.sleep(1)
        elif elapsed < 120:
            time.sleep(2)
        else:
            time.sleep(5)
