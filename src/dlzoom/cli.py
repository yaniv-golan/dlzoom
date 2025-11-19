"""
dlzoom – unified CLI entrypoint (Click group)

Subcommands:
- download: previous main functionality to list/check/download recordings
- login: authenticate via hosted auth service
- logout: remove local tokens
- whoami: show authenticated Zoom user (S2S for now)
"""

import json
import logging
import re
import sys
from datetime import UTC, date, datetime, timedelta
from datetime import timezone as _timezone
from pathlib import Path
from typing import Any, cast

import rich_click as click
from click.core import ParameterSource
from rich.console import Console

import dlzoom.handlers as _h
from dlzoom import __version__
from dlzoom.audio_extractor import AudioExtractionError
from dlzoom.config import Config, ConfigError
from dlzoom.downloader import DownloadError
from dlzoom.exceptions import DlzoomError
from dlzoom.logger import setup_logging
from dlzoom.login import main as login_main
from dlzoom.logout import main as logout_main
from dlzoom.output import OutputFormatter
from dlzoom.recorder_selector import RecordingSelector
from dlzoom.token_store import load as load_tokens
from dlzoom.whoami import main as whoami_main
from dlzoom.zoom_client import ZoomAPIError, ZoomClient
from dlzoom.zoom_user_client import ZoomUserAPIError, ZoomUserClient

# Rich-click configuration
# Switch to text markup (use_rich_markup is deprecated)
click.rich_click.TEXT_MARKUP = "rich"
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True

console = Console()
timezone = _timezone  # Back-compat for tests expecting module-level timezone


def _missing_credentials_message(cfg: Config) -> str:
    """Return a detailed guidance string for missing credentials."""
    default_config_path = cfg.config_dir / "config.json"
    return (
        "Not authenticated.\n"
        "• For user OAuth: run 'dlzoom login'\n"
        f"• For S2S OAuth: set ZOOM_ACCOUNT_ID/ZOOM_CLIENT_ID/ZOOM_CLIENT_SECRET or create "
        f"{default_config_path}"
    )


def _autoload_dotenv() -> None:
    """Automatically load a local .env file for CLI usage.

    Notes:
    - Skipped when the environment variable DLZOOM_NO_DOTENV is set (e.g., tests).
    - Does not override existing environment variables.
    - Searches from the current working directory upwards for a .env file.
    """
    import os

    try:
        if os.getenv("DLZOOM_NO_DOTENV"):
            return
        from dotenv import find_dotenv, load_dotenv

        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            load_dotenv(dotenv_path, override=False)
    except Exception:
        # Best-effort only; never fail CLI due to dotenv load issues
        pass


# Module logger for warnings/info
logger = logging.getLogger(__name__)


def validate_meeting_id(
    ctx: click.Context, param: click.Parameter, value: str | tuple[str, ...] | None
) -> str | None:
    """
    Validate meeting ID format to prevent injection attacks

    Zoom meeting IDs can be:
    - Numeric: 9-12 digits (e.g., 123456789)
    - UUID: Base64-like encoded string (e.g., abc123XYZ+/=_-)

    Args:
        ctx: Click context
        param: Parameter object
        value: Meeting ID value to validate (can be a tuple if nargs=-1)

    Returns:
        Validated meeting ID or None if value is None

    Raises:
        click.BadParameter: If meeting ID format is invalid
    """
    # Normalize: remove whitespace, strip URL fragments, and decode percent-encoding
    if value is None or (isinstance(value, tuple) and len(value) == 0):
        # Allow None for optional option usage; required arguments should not pass None.
        return None

    # If value is a tuple (from nargs=-1), join the parts
    if isinstance(value, tuple):
        raw = " ".join(str(v) for v in value).strip()
    else:
        raw = str(value).strip()

    # If user pasted a URL or an encoded UUID, strip fragment/query and decode
    # Examples handled:
    #   RhZSl5I9QyiJeDvddOqPPQ%3D%3D#/
    #   https://zoom.us/rec/.../recordings/<uuid>%3D%3D?foo=bar
    if "#" in raw:
        raw = raw.split("#", 1)[0]
    if "?" in raw:
        raw = raw.split("?", 1)[0]
    raw = raw.rstrip("/")
    try:
        from urllib.parse import unquote as _unquote

        # Decode up to two times to handle double-encoded UUIDs safely
        decoded_once = _unquote(raw)
        decoded_twice = _unquote(decoded_once)
        # Choose the shorter if decoding actually changed it, else keep once
        raw = decoded_twice if decoded_twice != decoded_once else decoded_once
    except Exception:
        # Best effort: ignore decoding errors
        pass

    normalized_value = "".join(raw.split())

    if not normalized_value:
        raise click.BadParameter("Meeting ID cannot be empty")

    # Check for path traversal attempts on normalized value
    # Allow forward slashes for UUIDs, but block .. and backslashes
    if ".." in normalized_value or "\\" in normalized_value:
        raise click.BadParameter(
            "Meeting ID contains invalid characters (path traversal attempt detected)"
        )

    # Check if numeric meeting ID (9-12 digits)
    if normalized_value.isdigit():
        if 9 <= len(normalized_value) <= 12:
            return normalized_value
        else:
            raise click.BadParameter(
                f"Numeric meeting ID must be 9-12 digits, got {len(normalized_value)} digits"
            )

    # Check if UUID format (alphanumeric plus base64 characters)
    # Zoom UUIDs can contain: a-z, A-Z, 0-9, +, /, =, _, -
    # Require at least one alphanumeric and minimum length
    uuid_pattern = r"^(?=.*[A-Za-z0-9])[A-Za-z0-9+/=_-]{2,100}$"
    if re.match(uuid_pattern, normalized_value):
        if len(normalized_value) <= 100:  # Reasonable max length for UUID
            return normalized_value
        else:
            raise click.BadParameter("Meeting ID exceeds maximum length (100 characters)")

    # Invalid format
    raise click.BadParameter(
        f"Invalid meeting ID format: {normalized_value!r}. "
        "Expected numeric ID (9-12 digits) or UUID (alphanumeric with +/=_- characters)"
    )


@click.group(help="dlzoom – Download Zoom cloud recordings")
@click.version_option(version=__version__)
def cli() -> None:
    """Top-level Click group."""
    # Ensure .env is loaded for all subcommands invoked via the CLI.
    _autoload_dotenv()


# Register subcommands from other modules
cli.add_command(login_main, name="login")
cli.add_command(logout_main, name="logout")
cli.add_command(whoami_main, name="whoami")


def _validate_date(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    if value is None:
        return None
    import re as _re
    from datetime import datetime as _dt

    if not _re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise click.BadParameter(f"Date must be YYYY-MM-DD, got: {value}")
    try:
        _dt.strptime(value, "%Y-%m-%d")
    except ValueError as e:
        raise click.BadParameter(f"Invalid date: {e}")
    return value


def _utc_today() -> date:
    """Return today's date in UTC (date portion only)."""
    return datetime.now(UTC).date()


def _calc_range(range_opt: str) -> tuple[str, str]:
    today = _utc_today()
    if range_opt == "today":
        f = t = today
    elif range_opt == "yesterday":
        f = t = today - timedelta(days=1)
    elif range_opt == "last-7-days":
        f, t = today - timedelta(days=6), today
    elif range_opt == "last-30-days":
        f, t = today - timedelta(days=29), today
    else:
        raise click.BadParameter(f"Invalid range: {range_opt}")
    return f.strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d")


@cli.command(name="recordings", help="Browse recordings by date or list instances for a meeting")
@click.option("--from-date", callback=_validate_date, help="Start date (YYYY-MM-DD)")
@click.option("--to-date", callback=_validate_date, help="End date (YYYY-MM-DD)")
@click.option(
    "--range",
    "range_opt",
    type=click.Choice(["today", "yesterday", "last-7-days", "last-30-days"]),
    help="Quick date range shortcut (mutually exclusive with --from-date/--to-date)",
)
@click.option(
    "--meeting-id",
    callback=validate_meeting_id,
    help="Exact meeting ID or UUID to list instances (replaces 'download --list')",
)
@click.option("--topic", help="Substring filter on topic (user-wide mode only)")
@click.option(
    "--limit",
    type=int,
    default=1000,
    show_default=True,
    help="Max results (0 = unlimited)",
)
@click.option(
    "--page-size",
    type=int,
    default=300,
    show_default=True,
    help="[Advanced] Number of results per API request (Zoom max 300)",
)
@click.option(
    "--scope",
    "scope_opt",
    type=click.Choice(["auto", "account", "user"], case_sensitive=False),
    default="auto",
    show_default=True,
    help=(
        "Recording scope. "
        "account=/accounts/me (S2S only, requires account:read:admin + "
        "cloud_recording:read:list_account_recordings:{admin|master}); "
        "user=/users/{userId} (S2S requires --user-id or ZOOM_S2S_DEFAULT_USER); "
        "auto=account for S2S, user otherwise."
    ),
)
@click.option(
    "--user-id",
    "user_id_opt",
    help=(
        "Zoom user email or UUID for --scope=user. Required for S2S tokens (or set "
        "ZOOM_S2S_DEFAULT_USER); user OAuth tokens default to 'me'."
    ),
)
@click.option("--json", "-j", "json_mode", is_flag=True, help="JSON output mode")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--debug", "-d", is_flag=True, help="Debug output")
@click.option("--config", type=click.Path(exists=True), help="Path to config file")
def recordings(
    from_date: str | None,
    to_date: str | None,
    range_opt: str | None,
    meeting_id: str | None,
    topic: str | None,
    limit: int,
    page_size: int,
    scope_opt: str,
    user_id_opt: str | None,
    json_mode: bool,
    verbose: bool,
    debug: bool,
    config: str | None,
) -> None:
    # Setup logging and formatter
    log_level = "DEBUG" if debug else ("INFO" if verbose else "WARNING")
    setup_logging(level=log_level, verbose=debug or verbose)
    output_mode = "json" if json_mode else "human"
    formatter = OutputFormatter(output_mode)
    if json_mode:
        formatter.set_silent(True)

    # Mutual exclusivity checks
    if meeting_id and any([range_opt, from_date, to_date, topic]):
        error_msg = "--meeting-id cannot be used with --range, --from-date, --to-date, or --topic"
        if json_mode:
            formatter.output_error(error_msg)
            raise SystemExit(1)
        raise click.UsageError(error_msg)
    if range_opt and (from_date or to_date):
        error_msg = "--range cannot be used with --from-date or --to-date"
        if json_mode:
            formatter.output_error(error_msg)
            raise SystemExit(1)
        raise click.UsageError(error_msg)

    # Dates
    if range_opt:
        from_date, to_date = _calc_range(range_opt)
    if from_date and to_date:
        from datetime import datetime

        fdt = datetime.strptime(from_date, "%Y-%m-%d")
        tdt = datetime.strptime(to_date, "%Y-%m-%d")
        if fdt > tdt:
            error_msg = "--from-date must be before or equal to --to-date"
            if json_mode:
                formatter.output_error(error_msg)
                raise SystemExit(1)
            raise click.UsageError(error_msg)
    elif from_date or to_date:
        error_msg = "Both --from-date and --to-date must be provided together"
        if json_mode:
            formatter.output_error(error_msg)
            raise SystemExit(1)
        raise click.UsageError(error_msg)

    # Debug visibility of effective date window
    if debug:
        msg = (
            f"[dim]Effective date range: from={from_date or '-'} to={to_date or '-'} "
            "(UTC dates, Zoom API filters on UTC)[/dim]"
        )
        console.print(msg)

    def _run_recordings_workflow() -> None:
        # Load config and choose client
        cfg = Config(env_file=config) if config else Config()
        auth_mode = cfg.get_auth_mode()
        use_s2s = auth_mode == "s2s"
        tokens = None if use_s2s else load_tokens(cfg.tokens_path)
        if not use_s2s and tokens is None:
            raise ConfigError(_missing_credentials_message(cfg))
        if debug or verbose:
            console.print(f"[dim]Using {auth_mode.upper()} authentication[/dim]")

        effective_page_size = page_size
        if effective_page_size <= 0:
            raise click.BadParameter("--page-size must be greater than zero.")

        if effective_page_size > 300:
            logging.warning(
                "page_size %s exceeds Zoom API limit of 300, capping to 300", effective_page_size
            )
            effective_page_size = 300

        client: ZoomClient | ZoomUserClient
        if use_s2s:
            client = ZoomClient(
                str(cfg.zoom_account_id),
                str(cfg.zoom_client_id),
                str(cfg.zoom_client_secret),
            )
            client.base_url = cfg.zoom_api_base_url.rstrip("/")
            client.token_url = cfg.zoom_oauth_token_url or client.token_url
        else:
            client = ZoomUserClient(tokens, str(cfg.tokens_path))  # type: ignore[arg-type]
            if hasattr(client, "base_url"):
                client.base_url = cfg.zoom_api_base_url.rstrip("/")

        scope_ctx: _h.ScopeContext | None = None
        if not meeting_id:
            # See docs/internal/s2s-recordings-plan.md (§1-2) for scope rules.
            scope_ctx = _h._resolve_scope(
                use_s2s=use_s2s,
                scope_flag=scope_opt,
                user_id=user_id_opt,
                default_s2s_user=cfg.s2s_default_user,
            )
            if debug or verbose:
                scope_debug_user = scope_ctx.user_id or "-"
                console.print(
                    f"[dim]Scope resolved to {scope_ctx.scope} "
                    f"(source={scope_ctx.reason}, user={scope_debug_user})[/dim]"
                )

        # Meeting-scoped mode
        if meeting_id:
            try:
                result = client.get_meeting_recordings(meeting_id)
            except (ZoomAPIError, ZoomUserAPIError) as e:
                if json_mode:
                    print(
                        _h.json_dumps(
                            {
                                "status": "error",
                                "error": {
                                    "code": "MEETING_LOOKUP_FAILED",
                                    "message": str(e),
                                },
                            }
                        )
                    )
                    return
                formatter.output_error(f"Failed to fetch recordings: {e}")
                raise SystemExit(1)

            meetings = result.get("meetings", [])
            if not meetings and result.get("recording_files"):
                meetings = [result]
            if not meetings:
                payload = {
                    "status": "success",
                    "command": "recordings-instances",
                    "meeting_id": meeting_id,
                    "total_instances": 0,
                    "instances": [],
                }
                if json_mode:
                    print(_h.json_dumps(payload))
                    return
                formatter.output_info("No recordings found")
                return

            if json_mode:
                payload = {
                    "status": "success",
                    "command": "recordings-instances",
                    "meeting_id": meeting_id,
                    "total_instances": len(meetings),
                    "instances": [
                        {
                            "uuid": m.get("uuid"),
                            "start_time": m.get("start_time"),
                            "duration": m.get("duration"),
                            "recording_files": [
                                f.get("recording_type") or f.get("file_type")
                                for f in m.get("recording_files", [])
                            ],
                        }
                        for m in meetings
                    ],
                }
                print(_h.json_dumps(payload))
                return

            console.print(f"\n[bold]Recordings for Meeting {meeting_id}[/bold]")
            console.print(f"Total instances: {len(meetings)}\n")
            for idx, m in enumerate(meetings, 1):
                console.print(f"[cyan]{idx}.[/cyan] {m.get('topic', 'N/A')}")
                console.print(f"   UUID: {m.get('uuid', 'N/A')}")
                console.print(f"   Start: {m.get('start_time', 'N/A')}")
                console.print(f"   Duration: {m.get('duration', 0)} minutes")
                console.print(f"   Files: {len(m.get('recording_files', []))}")
                console.print()
            return

        # Account-/user-wide mode
        if scope_ctx is None:
            raise ConfigError("Missing scope resolution for recordings command")

        resolved_scope = scope_ctx.scope
        resolved_user_id = scope_ctx.user_id

        items: list[dict[str, Any]] = []
        fetched = 0

        account_client: ZoomClient | None = None
        if resolved_scope == "account":
            account_client = cast(ZoomClient, client)
            meeting_iter = _h._iterate_account_recordings(
                account_client,
                from_date=from_date,
                to_date=to_date,
                page_size=effective_page_size,
                debug=debug,
            )
        else:
            if not resolved_user_id:
                raise ConfigError("--scope=user requires a user identifier")
            meeting_iter = _h._iterate_user_recordings(
                client,
                user_id=resolved_user_id,
                from_date=from_date,
                to_date=to_date,
                page_size=effective_page_size,
                debug=debug,
            )

        for m in meeting_iter:
            if topic and topic.lower() not in str(m.get("topic", "")).lower():
                continue
            items.append(m)
            fetched += 1
            if limit and limit > 0 and fetched >= limit:
                break

        # Recurring indicator (heuristic)
        from collections import Counter

        id_counts = Counter(m.get("id") for m in items)

        # Optional enrichment via meeting:read or S2S (gate to avoid excess calls)
        enrichment_budget = 50  # cap number of meeting lookups per command

        def _is_recurring_definitive(mid: Any) -> bool | None:
            try:
                if not mid:
                    return None
                # Only enrich if heuristic would be false (single occurrence) and budget remains
                if id_counts.get(mid, 0) > 1:
                    return None
                nonlocal enrichment_budget
                if enrichment_budget <= 0:
                    return None
                enrichment_budget -= 1
                details = client.get_meeting(str(mid))
                mtype = details.get("type")
                if isinstance(mtype, int) and mtype in (3, 8):
                    return True
                if isinstance(mtype, int):
                    return False
                return None
            except Exception:
                return None

        enriched: list[dict[str, Any]] = []
        for m in items:
            mid = m.get("id")
            rec = _is_recurring_definitive(mid)
            if rec is None:
                rec_flag = id_counts.get(mid, 0) > 1
            else:
                rec_flag = rec
            m2 = {
                "id": m.get("id"),
                "uuid": m.get("uuid"),
                "topic": m.get("topic"),
                "start_time": m.get("start_time"),
                "duration": m.get("duration"),
                "recording_count": len(m.get("recording_files", [])),
                "recurring": rec_flag,
            }
            enriched.append(m2)

        if json_mode:
            payload = {
                "status": "success",
                "command": "recordings",
                "from_date": from_date,
                "to_date": to_date,
                "total_meetings": len(enriched),
                "page_size": effective_page_size,
                "scope": resolved_scope,
                "user_id": resolved_user_id if resolved_scope == "user" else None,
                "account_id": account_client.account_id if account_client else None,
                "meetings": enriched,
            }
            print(_h.json_dumps(payload))
            return

        from rich.table import Table

        table = Table(title="Zoom Recordings")
        table.add_column("Topic", style="green")
        table.add_column("Start Time", style="blue")
        table.add_column("Duration", style="magenta")
        table.add_column("Meeting ID", style="cyan")
        table.add_column("Recurring", style="yellow")
        verbose_flag = verbose or debug
        if verbose_flag:
            table.add_column("UUID", style="white")
            table.add_column("Files", style="white")
        for r in enriched:
            row = [
                str(r.get("topic", "N/A")),
                str(r.get("start_time", "N/A")),
                str(r.get("duration", 0)),
                str(r.get("id", "")),
                "yes" if r.get("recurring") else "no",
            ]
            if verbose_flag:
                row.extend([str(r.get("uuid", "")), str(r.get("recording_count", 0))])
            table.add_row(*row)
        console.print(table)

    try:
        _run_recordings_workflow()
    except DlzoomError as e:
        logging.getLogger(__name__).debug("DlzoomError in recordings command:", exc_info=True)
        if json_mode:
            error_result = {
                "status": "error",
                "command": "recordings",
                "error": e.to_dict(),
            }
            print(json.dumps(error_result, indent=2))
        else:
            formatter.output_error(f"{e.code}: {e.message}")
            if e.details:
                formatter.output_info(e.details)
        if debug:
            raise
        raise SystemExit(1)
    except Exception as e:
        logging.getLogger(__name__).debug(
            "Unexpected exception in recordings command:", exc_info=True
        )
        if json_mode:
            error_result = {
                "status": "error",
                "command": "recordings",
                "error": {
                    "code": "UNEXPECTED_ERROR",
                    "message": str(e),
                    "details": "",
                },
            }
            print(json.dumps(error_result, indent=2))
        else:
            formatter.output_error(f"Unexpected error: {e}")
        if debug or verbose:
            raise
        raise SystemExit(1)


@cli.command(name="download", help="Download Zoom cloud recordings")
@click.argument("meeting_id", nargs=-1, callback=validate_meeting_id, required=False)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Output directory (default: current directory)",
)
@click.option("--output-name", "-n", help="Base filename for output files (default: meeting_id)")
@click.option(
    "--verbose", "-v", is_flag=True, help="Verbose mode - show detailed operation information"
)
@click.option(
    "--debug", "-d", is_flag=True, help="Debug mode - show full API responses and detailed trace"
)
@click.option(
    "--json", "-j", "json_mode", is_flag=True, help="JSON output mode - machine-readable output"
)
@click.option(
    "--check-availability",
    "-c",
    is_flag=True,
    help="Check if recording is ready (without downloading)",
)
@click.option("--recording-id", help="Select specific recording instance by UUID")
@click.option(
    "--wait", type=int, metavar="MINUTES", help="Wait for recording processing (timeout in minutes)"
)
@click.option(
    "--skip-transcript",
    is_flag=True,
    help="Skip transcript download (transcripts downloaded by default)",
)
@click.option(
    "--skip-chat", is_flag=True, help="Skip chat log download (chat logs downloaded by default)"
)
@click.option(
    "--skip-timeline", is_flag=True, help="Skip timeline download (timelines downloaded by default)"
)
@click.option(
    "--skip-speakers",
    is_flag=True,
    help="Do not generate minimal STJ speakers file (generated by default)",
)
@click.option(
    "--speakers-mode",
    type=click.Choice(["first", "multiple"]),
    default="first",
    show_default=True,
    help="When multiple users are listed for a timestamp: use first or label as multiple",
)
@click.option(
    "--stj-min-seg-sec",
    type=float,
    default=1.0,
    show_default=True,
    help="Drop segments shorter than this duration (seconds)",
)
@click.option(
    "--stj-merge-gap-sec",
    type=float,
    default=1.5,
    show_default=True,
    help="Merge adjacent same-speaker segments within this gap (seconds)",
)
@click.option(
    "--include-unknown",
    is_flag=True,
    help="Include segments with unknown speaker (otherwise drop)",
)
@click.option("--dry-run", is_flag=True, help="Show what would be downloaded without downloading")
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write structured download log to specified file (JSONL format)",
)
@click.option("--config", type=click.Path(exists=True), help="Path to config file")
@click.option(
    "--filename-template", help='Custom filename template (e.g., "{topic}_{start_time:%Y%m%d}")'
)
@click.option(
    "--folder-template", help='Custom folder structure template (e.g., "{start_time:%Y/%m}")'
)
@click.option(
    "--from-date",
    callback=_validate_date,
    help="Start date for batch downloads (YYYY-MM-DD)",
)
@click.option(
    "--to-date",
    callback=_validate_date,
    help="End date for batch downloads (YYYY-MM-DD)",
)
@click.option(
    "--scope",
    "download_scope_opt",
    type=click.Choice(["auto", "account", "user"], case_sensitive=False),
    default="auto",
    show_default=True,
    help=(
        "Recording scope (account requires S2S + account:read:admin + "
        "cloud_recording:read:list_account_recordings:{admin|master}). "
        "Used for batch fetches and stored in metadata/JSON."
    ),
)
@click.option(
    "--user-id",
    "download_user_id_opt",
    help=(
        "Zoom user email or UUID when --scope=user (required for S2S tokens unless "
        "ZOOM_S2S_DEFAULT_USER is set)."
    ),
)
@click.option(
    "--page-size",
    type=int,
    default=300,
    show_default=True,
    help="Meetings per API page when enumerating date ranges (max 300).",
)
def download(
    meeting_id: str | None,
    output_dir: Path | None,
    output_name: str | None,
    verbose: bool,
    debug: bool,
    json_mode: bool,
    check_availability: bool,
    recording_id: str | None,
    wait: int | None,
    skip_transcript: bool,
    skip_chat: bool,
    skip_timeline: bool,
    skip_speakers: bool,
    speakers_mode: str,
    stj_min_seg_sec: float,
    stj_merge_gap_sec: float,
    include_unknown: bool,
    dry_run: bool,
    log_file: Path | None,
    config: str | None,
    filename_template: str | None,
    folder_template: str | None,
    from_date: str | None,
    to_date: str | None,
    download_scope_opt: str,
    download_user_id_opt: str | None,
    page_size: int,
) -> None:
    """
    Download audio recordings and metadata from Zoom meetings."""
    # Setup logging
    log_level = "DEBUG" if debug else ("INFO" if verbose else "WARNING")
    setup_logging(level=log_level, verbose=debug or verbose)

    # Determine output mode
    output_mode = "json" if json_mode else "human"
    formatter = OutputFormatter(output_mode)

    date_mode = bool(from_date or to_date)
    if date_mode:
        if not from_date or not to_date:
            raise click.UsageError("Both --from-date and --to-date must be provided together.")
        if meeting_id:
            raise click.UsageError(
                "Meeting ID argument cannot be used together with --from-date/--to-date."
            )
    else:
        # Non date-range workflows require a meeting ID argument.
        if meeting_id is None:
            raise click.UsageError(
                "MEETING_ID argument is required unless --from-date/--to-date are provided."
            )

    try:
        # Load config
        cfg = Config(env_file=config) if config else Config()

        # Choose auth mode: S2S takes precedence if configured
        auth_mode = cfg.get_auth_mode()
        use_s2s = auth_mode == "s2s"
        user_tokens = None if use_s2s else load_tokens(cfg.tokens_path)
        if not use_s2s and user_tokens is None:
            # If neither S2S nor user tokens are available, raise config error
            raise ConfigError(_missing_credentials_message(cfg))

        # Override output dir if specified
        if output_dir:
            cfg.output_dir = Path(output_dir).expanduser()

        user_supplied_output_name = output_name is not None

        # Sanitize output name for filesystem safety
        try:
            from dlzoom.templates import TemplateParser

            parser = TemplateParser()
            if output_name is None and meeting_id:
                output_name = meeting_id
            if output_name is not None:
                output_name = parser.sanitize_filename(str(output_name))
        except Exception:
            # Fallback minimal sanitization if TemplateParser isn't available
            import re as _re

            name_source = output_name if output_name is not None else meeting_id
            if name_source is not None:
                name_to_sanitize = str(name_source)
                unsafe_chars = r'[<>:"/\\|?*]'
                safe_name = _re.sub(unsafe_chars, "_", name_to_sanitize)
                safe_name = _re.sub(r"[_\s]+", "_", safe_name).strip("_. ")
                output_name = safe_name

        # Initialize client per auth mode
        client: ZoomClient | ZoomUserClient
        if debug or verbose:
            console.print(f"[dim]Using {auth_mode.upper()} authentication[/dim]")

        if use_s2s:
            cfg.validate()
            client = ZoomClient(
                str(cfg.zoom_account_id),
                str(cfg.zoom_client_id),
                str(cfg.zoom_client_secret),
            )
            client.base_url = cfg.zoom_api_base_url.rstrip("/")
            client.token_url = cfg.zoom_oauth_token_url or client.token_url
        else:
            client = ZoomUserClient(user_tokens, str(cfg.tokens_path))  # type: ignore[arg-type]
            if hasattr(client, "base_url"):
                client.base_url = cfg.zoom_api_base_url.rstrip("/")

        # See docs/internal/s2s-recordings-plan.md for scope selection rationale.
        scope_ctx = _h._resolve_scope(
            use_s2s=use_s2s,
            scope_flag=download_scope_opt,
            user_id=download_user_id_opt,
            default_s2s_user=cfg.s2s_default_user,
        )
        if debug or verbose:
            scope_debug_user = scope_ctx.user_id or "-"
            console.print(
                f"[dim]Download scope resolved to {scope_ctx.scope} "
                f"(source={scope_ctx.reason}, user={scope_debug_user})[/dim]"
            )

        account_identifier: str | None = None
        if use_s2s:
            if cfg.zoom_account_id:
                account_identifier = str(cfg.zoom_account_id)
            elif isinstance(client, ZoomClient):
                account_identifier = getattr(client, "account_id", None)

        selector = RecordingSelector()
        ctx = click.get_current_context(silent=True)
        skip_speakers_source = (
            ctx.get_parameter_source("skip_speakers")
            if ctx is not None
            else ParameterSource.DEFAULT
        )
        resolved_skip_speakers: bool | None
        if skip_speakers_source in (ParameterSource.DEFAULT, None):
            resolved_skip_speakers = None
        else:
            resolved_skip_speakers = skip_speakers

        # Handle batch download mode (from_date/to_date)
        if from_date or to_date:
            if check_availability:
                _h._handle_batch_check_availability(
                    client=client,
                    selector=selector,
                    from_date=from_date,
                    to_date=to_date,
                    scope=scope_ctx.scope,
                    user_id=scope_ctx.user_id,
                    page_size=page_size,
                    account_id=account_identifier,
                    formatter=formatter,
                    verbose=verbose,
                    debug=debug,
                    json_mode=json_mode,
                    wait=wait,
                )
            else:
                _h._handle_batch_download(
                    client=client,
                    selector=selector,
                    from_date=from_date,
                    to_date=to_date,
                    scope=scope_ctx.scope,
                    user_id=scope_ctx.user_id,
                    page_size=page_size,
                    account_id=account_identifier,
                    output_dir=cfg.output_dir,
                    skip_transcript=skip_transcript,
                    skip_chat=skip_chat,
                    skip_timeline=skip_timeline,
                    formatter=formatter,
                    verbose=verbose,
                    debug=debug,
                    json_mode=json_mode,
                    filename_template=filename_template,
                    folder_template=folder_template,
                    skip_speakers=resolved_skip_speakers,
                    speakers_mode=speakers_mode,
                    stj_min_segment_sec=stj_min_seg_sec,
                    stj_merge_gap_sec=stj_merge_gap_sec,
                    include_unknown=include_unknown,
                    base_output_name=output_name,
                    user_supplied_output_name=user_supplied_output_name,
                    dry_run=dry_run,
                    wait=wait,
                    log_file=Path(log_file).expanduser() if log_file else None,
                )
            return

        # --list mode removed in v0.2.0; use `dlzoom recordings --meeting-id` instead

        # mypy helper: after returning above we know meeting_id is not None.
        assert meeting_id is not None
        single_meeting_id = cast(str, meeting_id)

        # Handle --check-availability mode
        if check_availability:
            _h._handle_check_availability(
                client, selector, single_meeting_id, recording_id, formatter, wait, json_mode
            )
            return

        # Default: Download mode
        _h._handle_download_mode(
            client=client,
            selector=selector,
            meeting_id=single_meeting_id,
            recording_id=recording_id,
            output_dir=cfg.output_dir,
            output_name=output_name,
            skip_transcript=skip_transcript,
            skip_chat=skip_chat,
            skip_timeline=skip_timeline,
            dry_run=dry_run,
            log_file=Path(log_file).expanduser() if log_file else None,
            formatter=formatter,
            verbose=verbose,
            debug=debug,
            json_mode=json_mode,
            wait=wait,
            filename_template=filename_template,
            folder_template=folder_template,
            skip_speakers=resolved_skip_speakers,
            speakers_mode=speakers_mode,
            stj_min_segment_sec=stj_min_seg_sec,
            stj_merge_gap_sec=stj_merge_gap_sec,
            include_unknown=include_unknown,
            scope=scope_ctx.scope,
            scope_user_id=scope_ctx.user_id,
            account_id=account_identifier,
        )

    except DlzoomError as e:
        # Structured error for custom exceptions
        # Always log full traceback at DEBUG level for debugging
        logging.getLogger(__name__).debug("DlzoomError exception caught:", exc_info=True)

        if json_mode:
            error_result = {
                "status": "error",
                "meeting_id": meeting_id if "meeting_id" in locals() else None,
                "error": e.to_dict(),
            }
            print(json.dumps(error_result, indent=2))
        else:
            formatter.output_error(f"{e.code}: {e.message}")
            if e.details:
                formatter.output_info(e.details)

        if debug:
            raise
        sys.exit(1)

    except ZoomAPIError as e:
        # Always log full traceback at DEBUG level for debugging
        logging.getLogger(__name__).debug("ZoomAPIError exception caught:", exc_info=True)

        if json_mode:
            error_result = {
                "status": "error",
                "meeting_id": meeting_id if "meeting_id" in locals() else None,
                "error": {"code": "ZOOM_API_ERROR", "message": str(e), "details": ""},
            }
            print(json.dumps(error_result, indent=2))
        else:
            formatter.output_error(f"Zoom API error: {e}")
        if debug:
            raise
        sys.exit(1)

    except (DownloadError, AudioExtractionError) as e:
        # Always log full traceback at DEBUG level for debugging
        logging.getLogger(__name__).debug(f"{type(e).__name__} exception caught:", exc_info=True)

        if json_mode:
            error_code = (
                "DOWNLOAD_ERROR" if isinstance(e, DownloadError) else "AUDIO_EXTRACTION_ERROR"
            )
            error_result = {
                "status": "error",
                "meeting_id": meeting_id if "meeting_id" in locals() else None,
                "error": {"code": error_code, "message": str(e), "details": ""},
            }
            print(json.dumps(error_result, indent=2))
        else:
            formatter.output_error(str(e))
        if debug:
            raise
        sys.exit(1)

    except Exception as e:
        # Always log full traceback at DEBUG level for debugging
        logging.getLogger(__name__).debug("Unexpected exception caught:", exc_info=True)

        if json_mode:
            error_result = {
                "status": "error",
                "error": {
                    "code": "UNEXPECTED_ERROR",
                    "message": str(e),
                    "details": "An unexpected error occurred",
                },
            }
            print(json.dumps(error_result, indent=2))
        else:
            formatter.output_error(f"Unexpected error: {e}")
        if debug or verbose:
            raise
        sys.exit(1)


# _handle_list_mode removed in v0.2.0; use `dlzoom recordings --meeting-id` instead


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
