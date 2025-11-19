"""
Recording helpers for dlzoom CLI commands.

Key Zoom API behaviors to remember (see docs/internal/s2s-recordings-plan.md):

1. Token context matters. S2S OAuth credentials operate at account scope and
   therefore require Zoom's `/accounts/me/recordings` endpoint plus BOTH
   `account:read:admin` and `cloud_recording:read:list_account_recordings:{admin|master}`
   scopes. User OAuth tokens retain user context and should stay on
   `/users/{userId}/recordings`.
2. `user_id="me"` is only reliable for user tokens. S2S tokens have no "me"
   concept and Zoom silently falls back to the account owner, so we error early
   unless an explicit email/UUID (or configured default) is provided.
3. Zoom enforces ~30 day windows per request. `_chunk_by_month` splits long
   ranges into calendar months and prevents reusing pagination tokens across
   months. This also mitigates the documented ~10k-record response ceiling.
4. Granular scope availability varies per tenant/role. Error handlers surface
   concrete scopes, troubleshooting steps, and links back to the plan + bug
   validation report for future maintainers.

For background on the production outage this code fixes, see
BUG_VALIDATION_REPORT.md and docs/architecture.md (Recording Fetching Modes).
"""

from __future__ import annotations

import json as _json
import time
import urllib.parse
from collections.abc import Callable, Iterator
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from rich.console import Console

from dlzoom import __version__ as dlzoom_version
from dlzoom.audio_extractor import AudioExtractor
from dlzoom.downloader import Downloader, DownloadError
from dlzoom.exceptions import (
    ConfigError,
    DlzoomError,
    DownloadFailedError,
    FFmpegNotFoundError,
    InvalidRecordingIDError,
    NoAudioAvailableError,
    RecordingNotFoundError,
)
from dlzoom.output import OutputFormatter
from dlzoom.recorder_selector import RecordingSelector
from dlzoom.templates import TemplateParser
from dlzoom.zoom_client import ZoomAPIError, ZoomClient
from dlzoom.zoom_user_client import ZoomUserClient

console = Console()

ScopeLiteral = Literal["account", "user"]


@dataclass(frozen=True)
class ScopeContext:
    """Resolved scope information for recording enumeration."""

    scope: ScopeLiteral
    user_id: str | None
    reason: str


def _resolve_scope(
    *,
    use_s2s: bool,
    scope_flag: str | None,
    user_id: str | None,
    default_s2s_user: str | None = None,
) -> ScopeContext:
    """Resolve whether to use account-level or user-level recording scope.

    Design notes (see docs/internal/s2s-recordings-plan.md §1):
    - S2S tokens have no "me" context; default to account scope for full coverage.
    - `--scope user` with S2S requires an explicit email/UUID (or
      `ZOOM_S2S_DEFAULT_USER`). We reject `user_id="me"` outright for S2S.
    - User OAuth tokens keep the legacy `user_id="me"` behavior because Zoom
      resolves it correctly for user-context tokens.
    """

    requested_scope = (scope_flag or "auto").strip().lower()
    if requested_scope not in {"auto", "account", "user"}:
        raise ConfigError(
            "--scope must be one of 'auto', 'account', or 'user'",
            details=f"Got: {scope_flag}",
        )

    if requested_scope == "auto":
        resolved_scope = "account" if use_s2s else "user"
        reason = "auto-s2s" if use_s2s else "auto-user-token"
    else:
        resolved_scope = requested_scope  # type: ignore[assignment]
        reason = "explicit"

    # Account scope only works with S2S credentials
    if resolved_scope == "account":
        if not use_s2s:
            raise ConfigError(
                "--scope=account requires S2S credentials (ZOOM_ACCOUNT_ID/CLIENT/SECRET)",
                details="User OAuth tokens operate per user; account endpoint is unavailable.",
            )
        return ScopeContext(scope="account", user_id=None, reason=reason)

    # User scope requires determining which user to target
    cleaned_user_id = (user_id or "").strip() or None
    cleaned_default = (default_s2s_user or "").strip() or None

    if use_s2s:
        resolved_user = cleaned_user_id or cleaned_default
        if not resolved_user:
            raise ConfigError(
                "S2S tokens need --user-id or ZOOM_S2S_DEFAULT_USER when --scope=user",
                details=("Provide an explicit Zoom user email/UUID or switch to --scope=account"),
            )
        if resolved_user.lower() == "me":
            raise ConfigError(
                'user_id="me" is invalid for S2S tokens. Zoom resolves it to the account owner.',
                details="Use an explicit email/UUID or --scope=account",
            )
        return ScopeContext(scope="user", user_id=resolved_user, reason=reason)

    # User tokens default to "me" if none provided
    return ScopeContext(scope="user", user_id=cleaned_user_id or "me", reason=reason)


def _chunk_by_month(
    from_date: str | None,
    to_date: str | None,
) -> list[tuple[str | None, str | None]]:
    """Split a date window into calendar-month chunks to satisfy Zoom limits."""

    if not from_date or not to_date:
        return [(from_date, to_date)]

    start = datetime.strptime(from_date, "%Y-%m-%d").date()
    end = datetime.strptime(to_date, "%Y-%m-%d").date()
    if start > end:
        raise ConfigError("from_date must be before or equal to to_date for recording fetches")

    # Use calendar-month slices because Zoom rejects requests spanning >30 days.
    chunks: list[tuple[str | None, str | None]] = []
    current = start
    while current <= end:
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        month_end = next_month - timedelta(days=1)
        chunk_start = current
        chunk_end = month_end if month_end <= end else end
        chunks.append((chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
        current = chunk_end + timedelta(days=1)

    return chunks


def _iterate_account_recordings(
    client: ZoomClient,
    *,
    from_date: str | None,
    to_date: str | None,
    page_size: int = 300,
    debug: bool = False,
) -> Iterator[dict[str, Any]]:
    """Iterate account-wide recordings across month windows.

    Zoom enforces a ~30 day window and uses `/accounts/me/recordings` for S2S
    tokens. This helper chunks into calendar months, caps `page_size` at
    Zoom's maximum (300), and loops through `next_page_token` until exhausted.
    Always prefer `/accounts/me` over `/accounts/{accountId}` to avoid
    master/sub-account permission issues (see BUG_VALIDATION_REPORT.md).
    """

    cap = min(page_size, 300)
    chunks = _chunk_by_month(from_date, to_date)
    for chunk_from, chunk_to in chunks:
        next_token = None
        if debug:
            console.print(
                f"[dim]Requesting account recordings chunk from={chunk_from or '-'} "
                f"to={chunk_to or '-'}[/dim]"
            )
        while True:
            try:
                resp = client.get_account_recordings(
                    from_date=chunk_from,
                    to_date=chunk_to,
                    page_size=cap,
                    next_page_token=next_token,
                )
            except ZoomAPIError as exc:
                _raise_account_scope_error(exc)
            meetings = resp.get("meetings", [])
            yield from meetings
            next_token = resp.get("next_page_token")
            if not next_token:
                break


def _iterate_user_recordings(
    client: ZoomClient | ZoomUserClient,
    *,
    user_id: str,
    from_date: str | None,
    to_date: str | None,
    page_size: int = 300,
    debug: bool = False,
) -> Iterator[dict[str, Any]]:
    """Iterate user-specific recordings with consistent chunking/pagination.

    The caller must already enforce the "no user_id='me' for S2S" rule. User
    tokens pass `user_id="me"` safely while S2S callers send explicit emails
    or UUIDs.
    """

    cap = min(page_size, 300)
    chunks = _chunk_by_month(from_date, to_date)
    for chunk_from, chunk_to in chunks:
        next_token = None
        if debug:
            console.print(
                f"[dim]Requesting user recordings for {user_id} chunk from={chunk_from or '-'} "
                f"to={chunk_to or '-'}[/dim]"
            )
        while True:
            resp = client.get_user_recordings(
                user_id=user_id,
                from_date=chunk_from,
                to_date=chunk_to,
                page_size=cap,
                next_page_token=next_token,
            )
            meetings = resp.get("meetings", [])
            yield from meetings
            next_token = resp.get("next_page_token")
            if not next_token:
                break


def _raise_account_scope_error(exc: ZoomAPIError) -> None:
    """Translate account-scope permission failures into actionable errors.

    References:
    - docs/internal/s2s-recordings-plan.md §3 (detailed troubleshooting steps)
    - https://devforum.zoom.us/t/granular-scopes-not-appearing/110556
    - https://devforum.zoom.us/t/issues-with-the-cloud-recordinglist-account-recordings-master-scope/130786
    """

    scope_hint = (
        "Zoom denied access to /accounts/me/recordings. Ensure your S2S app includes both "
        "account:read:admin and cloud_recording:read:list_account_recordings:{admin|master}."
    )
    remediation = "You can also re-run with --scope=user --user-id <email> as a temporary fallback."
    api_details = f"HTTP {exc.status_code or 'unknown'} / Zoom code {exc.zoom_code or 'n/a'}"
    details = (
        f"{api_details}. {remediation} "
        "Step 1: Verify actual token scopes via `dlzoom whoami --json`. "
        "Step 2: Add account:read:admin + "
        "cloud_recording:read:list_account_recordings:{{admin|master}}. "
        "Step 3: Ensure your admin role exposes granular scopes (see Zoom devforum link). "
        "Step 4: If scopes stay hidden, create a General app (unlisted) as documented "
        "in BUG_VALIDATION_REPORT.md."
    )
    details += (
        "\nSee https://devforum.zoom.us/t/granular-scopes-not-appearing/110556 for more context."
    )
    raise ConfigError(scope_hint, details=details) from exc


def json_dumps(data: Any) -> str:
    return _json.dumps(data, indent=2)


def _format_start_time_suffix(start_time: str | None) -> str | None:
    """Return a UTC timestamp suffix suitable for filenames."""
    if not start_time:
        return None
    try:
        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    except Exception:
        return None
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)
        return dt.strftime("%Y%m%d-%H%M%S")
    except Exception:
        return None


def _derive_batch_output_name(
    *,
    meeting_id: str | None,
    start_time: str | None,
    meeting_uuid: str | None,
    base_output_name: str | None,
    user_supplied_output_name: bool,
    sanitize: Callable[[str], str],
) -> str:
    """Compute batch output_name (see docs/internal/batch-output-name-plan.md)."""
    if user_supplied_output_name and base_output_name:
        return base_output_name

    safe_meeting_id = sanitize(str(meeting_id)) if meeting_id else "recording"
    timestamp_suffix = _format_start_time_suffix(start_time)
    if timestamp_suffix:
        return sanitize(f"{safe_meeting_id}_{timestamp_suffix}")

    if meeting_uuid:
        return sanitize(f"{safe_meeting_id}_{meeting_uuid}")

    if base_output_name:
        # Fallback to CLI-provided base (typically sanitized meeting_id)
        return base_output_name

    safe_meeting_id = safe_meeting_id or "recording"
    return safe_meeting_id


def _scrub_download_url(raw_url: str | None) -> str | None:
    """Remove sensitive query parameters (e.g., access_token) from Zoom URLs."""
    if not raw_url:
        return raw_url
    try:
        parsed = urllib.parse.urlsplit(raw_url)
        if not parsed.query:
            return raw_url
        filtered = [
            (k, v)
            for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() != "access_token"
        ]
        if len(filtered) == len(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)):
            return raw_url
        new_query = urllib.parse.urlencode(filtered)
        rebuilt = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)
        )
        # Ensure trailing ? removed if query empty
        if not new_query:
            return rebuilt.rstrip("?")
        return rebuilt
    except Exception:
        return raw_url


def _build_stj_context(
    *,
    meeting_id: str | None,
    meeting_uuid: str | None,
    recording_uuid: str | None,
    meeting_topic: str,
    instance: dict[str, Any],
    recording_files: list[dict[str, Any]],
    scope: ScopeLiteral | None,
    scope_user_id: str | None,
    account_id: str | None,
    speakers_mode: str,
    stj_min_segment_sec: float,
    stj_merge_gap_sec: float,
    include_unknown: bool,
    skip_transcript: bool,
    skip_chat: bool,
    skip_timeline: bool,
    skip_speakers: bool | None,
) -> dict[str, Any]:
    """Assemble metadata context for STJ generation."""

    def _to_bool(value: bool | None) -> bool:
        return bool(value)

    has_chat = False
    has_timeline = False
    has_transcript = False
    recording_summaries: list[dict[str, Any]] = []
    for rf in recording_files:
        file_type = str(rf.get("file_type") or "").upper()
        file_ext = str(rf.get("file_extension") or "").lower()
        if file_type == "CHAT" or file_ext == "txt":
            has_chat = True
        if file_type == "TIMELINE" or (file_ext == "json" and file_type != "CHAT"):
            has_timeline = True
        if file_type in {"TRANSCRIPT", "CC"} or file_ext == "vtt":
            has_transcript = True
        recording_summaries.append(
            {
                "id": rf.get("id"),
                "recording_type": rf.get("recording_type"),
                "file_type": rf.get("file_type"),
                "file_extension": rf.get("file_extension"),
                "recording_start": rf.get("recording_start"),
                "recording_end": rf.get("recording_end"),
                "status": rf.get("status"),
                "file_size": rf.get("file_size"),
                "download_url": _scrub_download_url(rf.get("download_url")),
            }
        )

    meeting_info = {
        "id": meeting_id,
        "uuid": meeting_uuid,
        "recording_uuid": recording_uuid,
        "topic": meeting_topic,
        "start_time": instance.get("start_time"),
        "timezone": instance.get("timezone"),
        "duration": instance.get("duration"),
        "host_id": instance.get("host_id"),
        "host_email": instance.get("host_email"),
        "host_name": instance.get("host_name"),
    }

    scope_info: dict[str, Any] = {}
    if scope:
        scope_info["mode"] = scope
    if scope_user_id:
        scope_info["user_id"] = scope_user_id
    if account_id:
        scope_info["account_id"] = account_id

    cli_info = {
        "speakers_mode": speakers_mode,
        "min_segment_sec": stj_min_segment_sec,
        "merge_gap_sec": stj_merge_gap_sec,
        "include_unknown": include_unknown,
        "skip_transcript": skip_transcript,
        "skip_chat": skip_chat,
        "skip_timeline": skip_timeline,
        "skip_speakers": _to_bool(skip_speakers),
    }

    if meeting_uuid:
        source_uri = f"zoom://meetings/{meeting_id}/recordings/{meeting_uuid}"
    else:
        source_uri = f"zoom://meetings/{meeting_id}"

    context = {
        "dlzoom_version": dlzoom_version,
        "source_uri": source_uri,
        "meeting": meeting_info,
        "scope": scope_info,
        "recording_files": recording_summaries,
        "cli": cli_info,
        "flags": {
            "has_chat": has_chat,
            "has_transcript": has_transcript,
            "has_timeline": has_timeline,
        },
    }
    return context


def _handle_check_availability(
    client: ZoomClient | ZoomUserClient,
    selector: RecordingSelector,
    meeting_id: str,
    recording_id: str | None,
    formatter: OutputFormatter,
    wait: int | None,
    json_mode: bool = False,
    *,
    capture_result: bool = False,
) -> dict[str, Any] | None:
    """Handle --check-availability mode: Check if recording is ready."""
    silent_ctx = formatter.capture_silent() if (json_mode or capture_result) else nullcontext()

    with silent_ctx:
        if not capture_result:
            formatter.output_info(f"Checking availability for meeting {meeting_id}...")

        max_wait_seconds = (wait * 60) if wait else 0
        start_time = time.time()
        poll_interval = 30  # seconds

        def _raise_availability_exception(payload: dict[str, Any]) -> None:
            error = payload.get("error") or {}
            code = str(error.get("code", "")).upper()
            message = error.get("message", "Availability check failed")
            details = payload.get("meeting_id") or ""
            if code in {"RECORDING_NOT_FOUND", "INVALID_MEETING"}:
                raise RecordingNotFoundError(message, details=details)
            elif code in {"ZOOM_API_ERROR", "NETWORK_ERROR"}:
                raise DownloadFailedError(message, details=details)
            else:
                raise DownloadFailedError(message, details=message)

        def _emit_result(
            result: dict[str, Any],
            *,
            human_success: str | None = None,
            human_info: str | None = None,
            human_error: str | None = None,
        ) -> dict[str, Any]:
            if not capture_result:
                if json_mode:
                    print(_json.dumps(result, indent=2))
                else:
                    if human_error:
                        formatter.output_error(human_error)
                    elif human_success:
                        formatter.output_success(human_success)
                    elif human_info:
                        formatter.output_info(human_info)
                if result.get("status") == "error":
                    _raise_availability_exception(result)
            return result

        while True:
            try:
                recordings = client.get_meeting_recordings(meeting_id)
                meetings = recordings.get("meetings", [])

                if not meetings and recordings.get("recording_files"):
                    meetings = [recordings]

                if meetings:
                    if recording_id:
                        instance = selector.filter_by_uuid(meetings, recording_id)
                    else:
                        instance = selector.select_most_recent_instance(meetings)

                    if instance:
                        recording_files = instance.get("recording_files", [])
                        recording_uuid = instance.get("uuid")

                        all_completed = all(f.get("status") == "completed" for f in recording_files)

                        audio_file = selector.select_best_audio(recording_files)
                        has_audio = audio_file is not None
                        audio_type = (
                            audio_file.get("file_extension", "").upper() if audio_file else None
                        )

                        if all_completed:
                            success_result = {
                                "status": "success",
                                "command": "check_availability",
                                "meeting_id": meeting_id,
                                "recording_uuid": recording_uuid,
                                "available": True,
                                "recording_status": "completed",
                                "has_audio": has_audio,
                                "audio_type": audio_type,
                                "processing_time_remaining": 0,
                                "ready_to_download": True,
                            }
                            return _emit_result(
                                success_result,
                                human_success=f"Recording is ready ({len(recording_files)} files)",
                            )
                        else:
                            if not wait:
                                processing_result = {
                                    "status": "success",
                                    "command": "check_availability",
                                    "meeting_id": meeting_id,
                                    "recording_uuid": recording_uuid,
                                    "available": False,
                                    "recording_status": "processing",
                                    "has_audio": has_audio,
                                    "audio_type": audio_type,
                                    "ready_to_download": False,
                                }
                                return _emit_result(
                                    processing_result,
                                    human_info=(
                                        "Recording is still processing. "
                                        "Use --wait to wait until it's ready."
                                    ),
                                )

                            elapsed = time.time() - start_time
                            remaining = max(0, max_wait_seconds - int(elapsed))

                            if elapsed >= max_wait_seconds:
                                timeout_result = {
                                    "status": "success",
                                    "command": "check_availability",
                                    "meeting_id": meeting_id,
                                    "recording_uuid": recording_uuid,
                                    "available": False,
                                    "recording_status": "processing",
                                    "has_audio": has_audio,
                                    "audio_type": audio_type,
                                    "processing_time_remaining": 0,
                                    "ready_to_download": False,
                                }
                                return _emit_result(
                                    timeout_result,
                                    human_info="Recording is still processing (wait timed out)",
                                )

                            if not json_mode and not capture_result:
                                formatter.output_info(
                                    "Recording is processing; checking again in "
                                    f"{poll_interval} seconds (time left: "
                                    f"{remaining // 60}m {remaining % 60}s)"
                                )
                            time.sleep(poll_interval)
                            continue

                error_result = {
                    "status": "error",
                    "command": "check_availability",
                    "meeting_id": meeting_id,
                    "error": {
                        "code": "RECORDING_NOT_FOUND",
                        "message": "Recording not found",
                    },
                }
                return _emit_result(error_result, human_error="Recording not found")

            except ZoomAPIError as e:
                error_result = {
                    "status": "error",
                    "command": "check_availability",
                    "meeting_id": meeting_id,
                    "error": {"code": "ZOOM_API_ERROR", "message": str(e)},
                }
                return _emit_result(error_result, human_error=f"Zoom API error: {e}")
            except DlzoomError as e:
                error_payload: dict[str, Any] = {"code": e.code, "message": e.message}
                if e.details:
                    error_payload["details"] = e.details
                error_result = {
                    "status": "error",
                    "command": "check_availability",
                    "meeting_id": meeting_id,
                    "error": error_payload,
                }
                return _emit_result(error_result, human_error=e.message)


def _handle_batch_download(
    client: ZoomClient | ZoomUserClient,
    selector: RecordingSelector,
    from_date: str | None,
    to_date: str | None,
    output_dir: Path,
    skip_transcript: bool,
    skip_chat: bool,
    skip_timeline: bool,
    formatter: OutputFormatter,
    verbose: bool,
    debug: bool,
    json_mode: bool,
    filename_template: str | None,
    folder_template: str | None,
    *,
    scope: ScopeLiteral,
    user_id: str | None,
    page_size: int = 300,
    account_id: str | None = None,
    skip_speakers: bool | None = None,
    speakers_mode: str = "first",
    stj_min_segment_sec: float = 1.0,
    stj_merge_gap_sec: float = 1.5,
    include_unknown: bool = False,
    base_output_name: str | None = None,
    user_supplied_output_name: bool = False,
    dry_run: bool = False,
    wait: int | None = None,
    log_file: Path | None = None,
) -> None:
    """Batch download helper used by the `download` command when a date range is supplied."""

    # Scope-aware enumeration
    if scope == "account":
        if not isinstance(client, ZoomClient):
            raise ConfigError("Account scope batch downloads require S2S ZoomClient")
        meeting_iter = _iterate_account_recordings(
            client,
            from_date=from_date,
            to_date=to_date,
            page_size=page_size,
            debug=debug,
        )
    else:
        if not user_id:
            raise ConfigError("--scope=user batch downloads require --user-id or config default")
        meeting_iter = _iterate_user_recordings(
            client,
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            page_size=page_size,
            debug=debug,
        )

    sanitize_helper = TemplateParser()
    log_path = log_file.expanduser() if log_file else None
    log_path_str = str(log_path.absolute()) if log_path else None

    meetings: list[dict[str, Any]] = []
    for raw in meeting_iter:
        meeting_id = raw.get("id") or raw.get("meeting_id")
        normalized = {
            "meeting_id": str(meeting_id) if meeting_id is not None else None,
            "meeting_topic": raw.get("topic", "Zoom Recording"),
            "start_time": raw.get("start_time"),
            "meeting_uuid": raw.get("uuid"),
            "recording_count": len(raw.get("recording_files", [])),
        }
        meetings.append(normalized)

    if not meetings:
        if json_mode:
            print(
                json_dumps(
                    {
                        "status": "success",
                        "command": "batch-download",
                        "from_date": from_date,
                        "to_date": to_date,
                        "total_meetings": 0,
                        "scope": scope,
                        "user_id": user_id if scope == "user" else None,
                        "page_size": min(page_size, 300),
                        "account_id": account_id if scope == "account" else None,
                        "results": [],
                        "log_file": log_path_str,
                    }
                )
            )
            return
        formatter.output_info("No recordings found in the specified date range")
        return

    def _parse_start_time(entry: dict[str, Any]) -> float:
        try:
            start = entry.get("start_time", "")
            return datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    meetings.sort(key=_parse_start_time, reverse=True)

    total_meetings = len(meetings)
    success_count = 0
    failed_count = 0
    results: list[dict[str, Any]] = []

    for entry in meetings:
        meeting_id = entry.get("meeting_id")
        meeting_topic = entry.get("meeting_topic", "Zoom Recording")
        start_time = entry.get("start_time")
        meeting_uuid = entry.get("meeting_uuid")

        if not meeting_id:
            failed_count += 1
            if json_mode:
                results.append(
                    {
                        "meeting_id": None,
                        "meeting_topic": meeting_topic,
                        "start_time": start_time,
                        "status": "error",
                        "scope": scope,
                        "user_id": user_id if scope == "user" else None,
                        "account_id": account_id if scope == "account" else None,
                        "error": {
                            "code": "INVALID_MEETING",
                            "message": "Meeting entry missing identifier",
                        },
                    }
                )
            else:
                formatter.output_error("Encountered meeting without an ID; skipping")
            continue

        per_meeting_output_name = _derive_batch_output_name(
            meeting_id=meeting_id,
            start_time=start_time,
            meeting_uuid=meeting_uuid,
            base_output_name=base_output_name,
            user_supplied_output_name=user_supplied_output_name,
            sanitize=sanitize_helper.sanitize_filename,
        )
        try:
            _handle_download_mode(
                client=client,
                selector=selector,
                meeting_id=str(meeting_id),
                recording_id=None,
                output_dir=output_dir,
                output_name=per_meeting_output_name,
                skip_transcript=skip_transcript,
                skip_chat=skip_chat,
                skip_timeline=skip_timeline,
                dry_run=dry_run,
                log_file=log_path,
                formatter=formatter,
                verbose=verbose,
                debug=debug,
                json_mode=False,  # suppress individual JSON
                wait=wait,
                filename_template=filename_template,
                folder_template=folder_template,
                skip_speakers=skip_speakers,
                speakers_mode=speakers_mode,
                stj_min_segment_sec=stj_min_segment_sec,
                stj_merge_gap_sec=stj_merge_gap_sec,
                include_unknown=include_unknown,
                scope=scope,
                scope_user_id=user_id,
                account_id=account_id,
            )
            success_count += 1
            if json_mode:
                results.append(
                    {
                        "meeting_id": meeting_id,
                        "meeting_topic": meeting_topic,
                        "start_time": start_time,
                        "status": "success",
                        "scope": scope,
                        "user_id": user_id if scope == "user" else None,
                        "account_id": account_id if scope == "account" else None,
                    }
                )
        except Exception as e:  # keep behavior identical
            failed_count += 1
            if json_mode:
                error_info = {
                    "code": e.code if isinstance(e, DlzoomError) else "UNKNOWN_ERROR",
                    "message": str(e),
                    "details": e.details if isinstance(e, DlzoomError) else "",
                }
                results.append(
                    {
                        "meeting_id": str(meeting_id),
                        "meeting_topic": meeting_topic,
                        "start_time": start_time,
                        "status": "error",
                        "scope": scope,
                        "user_id": user_id if scope == "user" else None,
                        "account_id": account_id if scope == "account" else None,
                        "error": error_info,
                    }
                )
            else:
                formatter.output_error(f"Failed to download meeting {meeting_id}: {e}")
            if debug:
                raise

    if json_mode:
        status = (
            "success"
            if failed_count == 0
            else ("partial_success" if success_count > 0 else "error")
        )
        batch_result = {
            "status": status,
            "command": "batch-download",
            "from_date": from_date,
            "to_date": to_date,
            "total_meetings": total_meetings,
            "successful": success_count,
            "failed": failed_count,
            "scope": scope,
            "user_id": user_id if scope == "user" else None,
            "account_id": account_id if scope == "account" else None,
            "page_size": min(page_size, 300),
            "results": results,
            "log_file": log_path_str,
        }
        print(_json.dumps(batch_result, indent=2))
    else:
        console.print("\n[bold]Batch download complete:[/bold]")
        console.print(f"  Success: {success_count}/{total_meetings}")
        if failed_count > 0:
            console.print(f"  Failed: {failed_count}/{total_meetings}")
    if failed_count > 0:
        details = f"{failed_count} of {total_meetings} meetings failed"
        raise DownloadFailedError("Batch download incomplete", details=details)


def _handle_batch_check_availability(
    client: ZoomClient | ZoomUserClient,
    selector: RecordingSelector,
    from_date: str | None,
    to_date: str | None,
    formatter: OutputFormatter,
    verbose: bool,
    debug: bool,
    json_mode: bool,
    *,
    scope: ScopeLiteral,
    user_id: str | None,
    page_size: int = 300,
    account_id: str | None = None,
    wait: int | None = None,
) -> None:
    """Batch helper for --check-availability with date ranges."""

    if scope == "account":
        if not isinstance(client, ZoomClient):
            raise ConfigError("Account scope batch availability requires S2S ZoomClient")
        meeting_iter = _iterate_account_recordings(
            client,
            from_date=from_date,
            to_date=to_date,
            page_size=page_size,
            debug=debug,
        )
    else:
        if not user_id:
            raise ConfigError(
                "--scope=user batch availability requires --user-id or config default"
            )
        meeting_iter = _iterate_user_recordings(
            client,
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            page_size=page_size,
            debug=debug,
        )

    meetings: list[dict[str, Any]] = []
    for raw in meeting_iter:
        meeting_id = raw.get("id") or raw.get("meeting_id")
        meetings.append(
            {
                "meeting_id": str(meeting_id) if meeting_id is not None else None,
                "meeting_topic": raw.get("topic", "Zoom Recording"),
                "start_time": raw.get("start_time"),
                "meeting_uuid": raw.get("uuid"),
            }
        )

    if not meetings:
        if json_mode:
            print(
                json_dumps(
                    {
                        "status": "success",
                        "command": "batch-check-availability",
                        "from_date": from_date,
                        "to_date": to_date,
                        "total_meetings": 0,
                        "scope": scope,
                        "user_id": user_id if scope == "user" else None,
                        "account_id": account_id if scope == "account" else None,
                        "page_size": min(page_size, 300),
                        "results": [],
                    }
                )
            )
            return
        formatter.output_info("No recordings found in the specified date range")
        return

    def _parse_start_time(entry: dict[str, Any]) -> float:
        try:
            start = entry.get("start_time", "")
            return datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    meetings.sort(key=_parse_start_time, reverse=True)

    total_meetings = len(meetings)
    success_count = 0
    ready_count = 0
    processing_count = 0
    failed_count = 0
    results: list[dict[str, Any]] = []

    for meeting in meetings:
        meeting_id = meeting.get("meeting_id")
        meeting_topic = meeting.get("meeting_topic", "Zoom Recording")
        if meeting_id is None:
            failed_count += 1
            results.append(
                {
                    "status": "error",
                    "command": "check_availability",
                    "meeting_id": None,
                    "meeting_topic": meeting_topic,
                    "error": {
                        "code": "INVALID_MEETING",
                        "message": "Meeting entry missing identifier",
                    },
                }
            )
            continue

        availability = _handle_check_availability(
            client,
            selector,
            str(meeting_id),
            recording_id=None,
            formatter=formatter,
            wait=wait,
            json_mode=json_mode,
            capture_result=True,
        )
        if availability is None:
            availability = {
                "status": "error",
                "command": "check_availability",
                "meeting_id": str(meeting_id),
                "meeting_topic": meeting_topic,
                "error": {
                    "code": "UNKNOWN_RESULT",
                    "message": "No availability data returned",
                },
            }

        availability.setdefault("meeting_id", str(meeting_id))
        availability.setdefault("meeting_topic", meeting_topic)

        if availability.get("status") == "success":
            success_count += 1
            if availability.get("available"):
                ready_count += 1
            else:
                processing_count += 1
            if not json_mode:
                state = (
                    "ready"
                    if availability.get("available")
                    else availability.get("recording_status", "processing")
                )
                formatter.output_info(f"[{meeting_id}] status: {state}")
        else:
            failed_count += 1
            if not json_mode:
                err_msg = availability.get("error", {}).get("message", "Availability check failed")
                formatter.output_error(f"[{meeting_id}] {err_msg}")

        results.append(availability)

    if json_mode:
        status = (
            "success"
            if failed_count == 0 and processing_count == 0
            else ("partial_success" if success_count > 0 else "error")
        )
        print(
            json_dumps(
                {
                    "status": status,
                    "command": "batch-check-availability",
                    "from_date": from_date,
                    "to_date": to_date,
                    "total_meetings": total_meetings,
                    "ready": ready_count,
                    "processing": processing_count,
                    "failed": failed_count,
                    "scope": scope,
                    "user_id": user_id if scope == "user" else None,
                    "account_id": account_id if scope == "account" else None,
                    "page_size": min(page_size, 300),
                    "results": results,
                }
            )
        )
        return

    formatter.output_info(
        f"Availability check complete: {ready_count} ready, "
        f"{processing_count} still processing, {failed_count} errors "
        f"(total {total_meetings})"
    )


def _handle_download_mode(
    client: ZoomClient | ZoomUserClient,
    selector: RecordingSelector,
    meeting_id: str,
    recording_id: str | None,
    output_dir: Path,
    output_name: str | None,
    skip_transcript: bool,
    skip_chat: bool,
    skip_timeline: bool,
    dry_run: bool,
    log_file: Path | None,
    formatter: OutputFormatter,
    verbose: bool,
    debug: bool,
    json_mode: bool,
    wait: int | None,
    filename_template: str | None = None,
    folder_template: str | None = None,
    *,
    skip_speakers: bool | None = None,
    speakers_mode: str = "first",
    stj_min_segment_sec: float = 1.0,
    stj_merge_gap_sec: float = 1.5,
    include_unknown: bool = False,
    scope: ScopeLiteral | None = None,
    scope_user_id: str | None = None,
    account_id: str | None = None,
) -> None:
    """Handle download mode: Download recordings."""

    # Initialize result dictionary for JSON output
    result: dict[str, Any] = {"status": "success", "meeting_id": meeting_id}
    log_file_path: Path | None = None
    log_file_str: str | None = None
    if log_file:
        log_file_path = Path(log_file).expanduser()
        log_file_str = str(log_file_path.absolute())

    def _append_scope_fields(payload: dict[str, Any]) -> None:
        if not scope:
            return
        payload["scope"] = scope
        if scope == "user" and scope_user_id:
            payload["user_id"] = scope_user_id
        if scope == "account" and account_id:
            payload["account_id"] = account_id

    _append_scope_fields(result)
    warnings: list[str] = []

    # Enable silent mode for JSON output to suppress intermediate messages
    if json_mode:
        formatter.set_silent(True)

    # Wait for recording if --wait specified
    availability = None
    if wait:
        availability = _handle_check_availability(
            client,
            selector,
            meeting_id,
            recording_id,
            formatter,
            wait,
            json_mode,
            capture_result=True,
        )
        if availability:
            if availability.get("status") == "success" and availability.get("available"):
                formatter.output_info("Availability check completed (recording ready).")
            else:
                message = availability.get("error", {}).get("message") or availability.get(
                    "recording_status", "processing"
                )
                raise RecordingNotFoundError(
                    "Recording not ready after wait",
                    details=f"Availability result: {message}",
                )

    formatter.output_info(f"Fetching recording info for meeting {meeting_id}...")
    recordings = client.get_meeting_recordings(meeting_id)

    # Handle response structure
    meetings = recordings.get("meetings", [])
    selection_method = None

    if not meetings:
        if recordings.get("recording_files"):
            instance = recordings
            selection_method = "only_instance"
        else:
            raise RecordingNotFoundError(
                "No recording files found",
                details="The meeting may not have been recorded or the recording was deleted",
            )
    else:
        if recording_id:
            found_instance = selector.filter_by_uuid(meetings, recording_id)
            selection_method = "user_specified"
            if not found_instance:
                raise InvalidRecordingIDError(
                    f"Instance with UUID {recording_id} not found",
                    details=f"No recording instance found with UUID: {recording_id}",
                )
            instance = found_instance
        elif len(meetings) > 1:
            formatter.output_info(f"Multiple instances found ({len(meetings)}), using most recent")
            found_instance = selector.select_most_recent_instance(meetings)
            selection_method = "most_recent"
            if not found_instance:
                raise RecordingNotFoundError(
                    "Could not select most recent instance",
                    details="No valid recording found among multiple instances",
                )
            instance = found_instance
        else:
            instance = meetings[0]
            selection_method = "only_instance"

    recording_files = instance.get("recording_files", [])
    if not recording_files:
        raise RecordingNotFoundError(
            "No recording files found",
            details="The meeting may not have been recorded or the recording was deleted",
        )

    meeting_topic = instance.get("topic", "Zoom Recording")
    instance_start = instance.get("start_time")
    meeting_uuid = instance.get("uuid")

    stj_context = _build_stj_context(
        meeting_id=meeting_id,
        meeting_uuid=meeting_uuid,
        recording_uuid=meeting_uuid,
        meeting_topic=meeting_topic,
        instance=instance,
        recording_files=recording_files,
        scope=scope,
        scope_user_id=scope_user_id,
        account_id=account_id,
        speakers_mode=speakers_mode,
        stj_min_segment_sec=stj_min_segment_sec,
        stj_merge_gap_sec=stj_merge_gap_sec,
        include_unknown=include_unknown,
        skip_transcript=skip_transcript,
        skip_chat=skip_chat,
        skip_timeline=skip_timeline,
        skip_speakers=skip_speakers,
    )

    # Apply templates if provided
    if filename_template or folder_template:
        parser = TemplateParser(filename_template, folder_template)
        meeting_data = {
            "meeting_id": meeting_id,
            "meeting_uuid": meeting_uuid,
            "topic": meeting_topic,
            "start_time": instance_start,
            "host_email": instance.get("host_email"),
            "host_id": instance.get("host_id"),
            "duration": instance.get("duration"),
        }
        if filename_template:
            output_name = parser.apply_filename_template(meeting_data)
        if folder_template:
            folder_path = parser.apply_folder_template(meeting_data)
            output_dir = output_dir / folder_path
            output_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        total_size = 0
        has_audio = False
        for f in recording_files:
            # Check for M4A extension or audio_only file type
            if f.get("file_extension", "").upper() == "M4A" or f.get("file_type") == "audio_only":
                has_audio = True
            total_size += int(f.get("file_size", 0) or 0)
        if json_mode:
            dry_run_result = {
                "status": "success",
                "command": "download-dry-run",
                "meeting_id": meeting_id,
                "recording_uuid": meeting_uuid,
                "available": True,
                "has_audio": has_audio,
                "total_bytes": total_size,
            }
            if log_file_str:
                dry_run_result["log_file"] = log_file_str
            _append_scope_fields(dry_run_result)
            print(_json.dumps(dry_run_result, indent=2))
        else:
            formatter.output_info(
                "Dry run: would download "
                f"{len(recording_files)} files totaling ~"
                f"{total_size / (1024 * 1024):.1f} MB"
            )
        return

    # Get access token from client for download authentication
    # Defensive check: ensure client exposes _get_access_token (tests rely on this)
    client_has_method = hasattr(type(client), "_get_access_token") or (
        "_get_access_token" in getattr(client, "__dict__", {})
    )
    if not client_has_method:
        raise AttributeError("Client does not provide _get_access_token()")
    access_token = client._get_access_token()
    downloader = Downloader(output_dir, access_token, output_name, stj_context=stj_context)
    extractor = AudioExtractor()
    downloaded_files: list[Path] = []
    generated_files: list[Path] = []
    delivered_audio_files: list[Path] = []
    retained_video_files: list[Path] = []
    _downloaded_index: set[str] = set()
    _generated_index: set[str] = set()
    _delivered_audio_index: set[str] = set()
    _retained_video_index: set[str] = set()

    def _track_downloaded_file(path: Path | None) -> None:
        if not path:
            return
        normalized = str(path)
        if normalized not in _downloaded_index:
            downloaded_files.append(path)
            _downloaded_index.add(normalized)

    def _track_generated_file(path: Path | None) -> None:
        if not path:
            return
        normalized = str(path)
        if normalized not in _generated_index:
            generated_files.append(path)
            _generated_index.add(normalized)

    def _track_audio_file(path: Path | None) -> None:
        if not path:
            return
        normalized = str(path)
        if normalized not in _delivered_audio_index:
            delivered_audio_files.append(path)
            _delivered_audio_index.add(normalized)

    def _track_video_file(path: Path | None) -> None:
        if not path:
            return
        normalized = str(path)
        if normalized not in _retained_video_index:
            retained_video_files.append(path)
            _retained_video_index.add(normalized)

    audio_file: dict[str, Any] | None = selector.select_best_audio(recording_files)
    if audio_file is None:
        # Fallback: pick an MP4 video to extract audio from
        video_file = next(
            (f for f in recording_files if str(f.get("file_extension", "")).upper() == "MP4"),
            None,
        )
        if not video_file:
            raise NoAudioAvailableError(
                "No audio available",
                details="No suitable audio or video files found for this recording",
            )
        audio_file = video_file

    # At this point we always have an audio/MP4 file to work with.
    assert audio_file is not None

    audio_file_size = int(audio_file.get("file_size", 0) or 0)
    audio_extracted_from_video = False
    delivered_audio_path: Path | None = None
    source_file_type = audio_file.get("file_extension", "").upper()
    # Check for audio-only files (M4A extension or audio_only file type)
    audio_only_available = any(
        f.get("file_extension", "").upper() == "M4A" or f.get("file_type") == "audio_only"
        for f in recording_files
    )

    audio_download_url = audio_file.get("download_url")
    if not audio_download_url:
        raise DownloadError("Audio file has no download URL")

    audio_path: Path = downloader.download_file(
        str(audio_download_url),
        audio_file,
        meeting_topic,
        instance_start,
        show_progress=not json_mode,
    )
    _track_downloaded_file(audio_path)
    delivered_audio_path = audio_path

    if audio_path.suffix.lower() == ".mp4":
        _track_video_file(audio_path)
        if not extractor.check_ffmpeg_available():
            raise FFmpegNotFoundError(
                "ffmpeg not found",
                details=(
                    "Install ffmpeg to extract audio from MP4 files: "
                    "https://ffmpeg.org/download.html"
                ),
            )
        formatter.output_info("Extracting audio from MP4...")
        audio_m4a_path = extractor.extract_audio(audio_path, verbose=debug or verbose)
        formatter.output_success(f"Audio extracted: {audio_m4a_path}")
        formatter.output_info(f"MP4 file retained: {audio_path}")
        audio_extracted_from_video = True
        _track_generated_file(audio_m4a_path)
        delivered_audio_path = audio_m4a_path
        _track_audio_file(audio_m4a_path)
    else:
        _track_audio_file(audio_path)

    if delivered_audio_path:
        _track_audio_file(delivered_audio_path)

    if not skip_transcript or not skip_chat or not skip_timeline:
        transcript_files = downloader.download_transcripts_and_chat(
            recording_files,
            meeting_topic,
            instance_start,
            show_progress=not json_mode,
            skip_transcript=skip_transcript,
            skip_chat=skip_chat,
            skip_timeline=skip_timeline,
            skip_speakers=skip_speakers,
            speakers_mode=speakers_mode,
            stj_min_segment_sec=stj_min_segment_sec,
            stj_merge_gap_sec=stj_merge_gap_sec,
            include_unknown=include_unknown,
        )
        for category, paths in transcript_files.items():
            tracker = _track_generated_file if category == "speakers" else _track_downloaded_file
            for path in paths:
                tracker(path)

    participants: list[dict[str, Any]] = []
    if meeting_uuid and isinstance(client, ZoomClient):
        try:
            formatter.output_info("Fetching participant information...")
            participants = client.get_all_participants(meeting_uuid)
        except ZoomAPIError as e:
            formatter.output_info(f"Could not fetch participants: {e}")

    start_time_val = instance.get("start_time")
    duration = instance.get("duration")
    end_time = None
    if start_time_val and duration:
        try:
            dt_start = datetime.fromisoformat(start_time_val.replace("Z", "+00:00"))
            dt_end = dt_start + timedelta(minutes=duration)
            end_time = dt_end.isoformat().replace("+00:00", "Z")
        except Exception:
            pass

    if delivered_audio_path and delivered_audio_path.exists():
        try:
            audio_file_size = delivered_audio_path.stat().st_size
        except OSError:
            pass

    metadata = {
        "meeting_id": meeting_id,
        "meeting_uuid": meeting_uuid,
        "meeting_title": meeting_topic,
        "topic": meeting_topic,
        "start_time": start_time_val,
        "end_time": end_time,
        "duration": duration,
        "timezone": instance.get("timezone"),
        "host_id": instance.get("host_id"),
        "host_email": instance.get("host_email"),
        "recording_information": {
            "recording_id": audio_file.get("id"),
            "recording_type": audio_file.get("recording_type"),
            "recording_start": audio_file.get("recording_start"),
            "recording_end": audio_file.get("recording_end"),
            "file_size": audio_file.get("file_size"),
            "file_extension": audio_file.get("file_extension"),
            "download_url": _scrub_download_url(audio_file.get("download_url")),
            "audio_only_available": audio_only_available,
            "audio_extracted_from_video": audio_extracted_from_video,
            "source_file_type": source_file_type,
        },
        "participants": [
            {
                "name": p.get("name"),
                "user_email": p.get("user_email"),
                "join_time": p.get("join_time"),
                "leave_time": p.get("leave_time"),
                "duration": p.get("duration"),
            }
            for p in participants
        ],
        "total_participants": len(participants),
        "recording_files": [
            {
                "recording_id": f.get("id"),
                "recording_type": f.get("recording_type"),
                "file_type": f.get("file_type"),
                "file_extension": f.get("file_extension"),
                "file_size": f.get("file_size"),
                "download_url": _scrub_download_url(f.get("download_url")),
                "status": f.get("status"),
            }
            for f in recording_files
        ],
    }

    if scope:
        metadata["fetch_scope"] = scope
    if scope == "user" and scope_user_id:
        metadata["fetch_user_id"] = scope_user_id
    if scope == "account" and account_id:
        metadata["account_id"] = account_id

    if len(meetings) > 1:
        metadata["multiple_instances"] = True
        metadata["total_instances"] = len(meetings)
        metadata["selected_instance"] = selection_method
        metadata["selected_instance_uuid"] = meeting_uuid
        metadata["selected_instance_timestamp"] = instance.get("start_time")
        metadata["note"] = (
            "Multiple recordings exist for this meeting. Use "
            "'dlzoom recordings --meeting-id <id>' to see all instances."
        )
        metadata["all_instances"] = [
            {
                "uuid": m.get("uuid"),
                "start_time": m.get("start_time"),
                "duration": m.get("duration"),
                "has_recording": bool(m.get("recording_files")),
            }
            for m in meetings
        ]

    # Use meeting_id as fallback if output_name is None
    metadata_basename = output_name if output_name else meeting_id
    metadata_path = output_dir / f"{metadata_basename}_metadata.json"
    with open(metadata_path, "w") as f:
        _json.dump(metadata, f, indent=2)
    _track_generated_file(metadata_path)
    formatter.output_success(f"Metadata saved: {metadata_path}")

    # Write structured log if requested
    if log_file_path:
        try:
            log_path = log_file_path
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                for file_path in downloaded_files + generated_files:
                    log_entry = {
                        "meeting_id": meeting_id,
                        "meeting_uuid": meeting_uuid,
                        "file_path": str(file_path.absolute()),
                        "size_bytes": file_path.stat().st_size if file_path.exists() else 0,
                        "timestamp": time.time(),
                        "status": "completed",
                    }
                    f.write(_json.dumps(log_entry) + "\n")
        except OSError as e:
            warnings.append(f"Could not write log file: {e}")

    download_count = len(downloaded_files)
    created_count = len(generated_files)
    summary_message = f"Downloaded {download_count} file(s)"
    if created_count:
        summary_message += f" and created {created_count} file(s)"
    summary_message += f" to {output_dir}"
    formatter.output_success(summary_message)

    if not json_mode:

        def _display_path(path: Path) -> str:
            try:
                return str(path.relative_to(output_dir))
            except ValueError:
                return str(path)

        if downloaded_files:
            formatter.output_info("Downloaded files:")
            for path in downloaded_files:
                formatter.output_info(f"  - {_display_path(path)}")
        if generated_files:
            formatter.output_info("Created files:")
            for path in generated_files:
                formatter.output_info(f"  - {_display_path(path)}")

    if json_mode:
        files_dict: dict[str, Any] = {"metadata": str(metadata_path.absolute())}
        all_file_paths = downloaded_files + generated_files
        audio_files = delivered_audio_files or [
            f for f in downloaded_files if f.suffix.lower() == ".m4a"
        ]
        if audio_files:
            files_dict["audio"] = str(audio_files[0].absolute())
            files_dict["audio_files"] = [str(f.absolute()) for f in audio_files]
        transcript_files_list = [f for f in downloaded_files if f.suffix.lower() == ".vtt"]
        if transcript_files_list:
            files_dict["transcript"] = str(transcript_files_list[0].absolute())
            files_dict["transcripts"] = [str(f.absolute()) for f in transcript_files_list]
        chat_files = [
            f for f in downloaded_files if f.suffix.lower() == ".txt" and "chat" in f.name.lower()
        ]
        if chat_files:
            files_dict["chat"] = str(chat_files[0].absolute())
            files_dict["chats"] = [str(f.absolute()) for f in chat_files]
        timeline_files = [
            f for f in downloaded_files if f.suffix.lower() == ".json" and "timeline" in f.name
        ]
        if timeline_files:
            files_dict["timeline"] = str(timeline_files[0].absolute())
            files_dict["timelines"] = [str(f.absolute()) for f in timeline_files]
        speaker_files = [f for f in all_file_paths if f.suffix.lower().endswith("stjson")]
        if speaker_files:
            files_dict["speakers"] = [str(f.absolute()) for f in speaker_files]
        video_files = retained_video_files or [
            f for f in downloaded_files if f.suffix.lower() == ".mp4"
        ]
        if video_files:
            files_dict["video"] = str(video_files[0].absolute())
            files_dict["videos"] = [str(f.absolute()) for f in video_files]

        metadata_summary = {
            "meeting_title": metadata.get("meeting_title"),
            "start_time": metadata.get("start_time"),
            "end_time": metadata.get("end_time"),
            "duration": metadata.get("duration"),
            "participants_count": metadata.get("total_participants"),
            "audio_format": "M4A",
            "audio_size_bytes": audio_file_size,
            "audio_extracted_from_video": audio_extracted_from_video,
            "source_video_format": source_file_type if audio_extracted_from_video else None,
        }

        result["recording_uuid"] = str(meeting_uuid) if meeting_uuid else ""
        result["output_name"] = str(output_name)
        result["files"] = files_dict
        result["metadata_summary"] = metadata_summary
        result["downloaded_file_count"] = len(downloaded_files)
        result["created_file_count"] = len(generated_files)
        result["downloaded_files"] = [str(f.absolute()) for f in downloaded_files]
        if generated_files:
            result["created_files"] = [str(f.absolute()) for f in generated_files]
        if log_file_str:
            result["log_file"] = log_file_str
        _append_scope_fields(result)

        if len(meetings) > 1:
            multi_inst: dict[str, Any] = {
                "has_multiple": True,
                "total_count": len(meetings),
                "selected": str(selection_method) if selection_method else "",
                "selected_timestamp": str(instance.get("start_time", "")),
                "note": (
                    "Multiple recordings exist for this meeting. Use "
                    "'dlzoom recordings --meeting-id <id>' to see all instances."
                ),
            }
            result["multiple_instances"] = multi_inst

        if warnings:
            result["status"] = "partial_success"
            result["warnings"] = warnings

        print(_json.dumps(result, indent=2))
