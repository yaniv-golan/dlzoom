"""
CLI interface for dlzoom
"""

import json
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import rich_click as click
from rich.console import Console

from dlzoom import __version__
from dlzoom.audio_extractor import AudioExtractionError, AudioExtractor
from dlzoom.config import Config, ConfigError
from dlzoom.downloader import Downloader, DownloadError
from dlzoom.exceptions import (
    DlzoomError,
    FFmpegNotFoundError,
    NoAudioAvailableError,
    RecordingNotFoundError,
)
from dlzoom.logger import setup_logging
from dlzoom.output import OutputFormatter
from dlzoom.recorder_selector import RecordingSelector
from dlzoom.templates import TemplateParser
from dlzoom.zoom_client import ZoomAPIError, ZoomClient
from dlzoom.zoom_user_client import ZoomUserClient
from dlzoom.token_store import load as load_tokens, exists as tokens_exist

# Rich-click configuration
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True

console = Console()


def validate_meeting_id(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """
    Validate meeting ID format to prevent injection attacks

    Zoom meeting IDs can be:
    - Numeric: 9-12 digits (e.g., 123456789)
    - UUID: Base64-like encoded string (e.g., abc123XYZ+/=_-)

    Args:
        ctx: Click context
        param: Parameter object
        value: Meeting ID value to validate

    Returns:
        Validated meeting ID

    Raises:
        click.BadParameter: If meeting ID format is invalid
    """
    # Normalize: remove all whitespace (spaces, tabs, newlines)
    if value is None:
        raise click.BadParameter("Meeting ID cannot be empty")
    normalized_value = "".join(str(value).split())

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


@click.command()
@click.argument("meeting_id", callback=validate_meeting_id)
@click.version_option(version=__version__)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(exists=False),
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
    "--list",
    "-l",
    "list_mode",
    is_flag=True,
    help="List all recordings for this meeting with timestamps and UUIDs",
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
@click.option("--dry-run", is_flag=True, help="Show what would be downloaded without downloading")
@click.option("--password", "-p", help="Password for password-protected recordings")
@click.option(
    "--log-file",
    type=click.Path(exists=False),
    help="Write structured download log to specified file (JSONL format)",
)
@click.option("--config", type=click.Path(exists=True), help="Path to config file")
@click.option(
    "--filename-template", help='Custom filename template (e.g., "{topic}_{start_time:%Y%m%d}")'
)
@click.option(
    "--folder-template", help='Custom folder structure template (e.g., "{start_time:%Y/%m}")'
)
@click.option("--from-date", help="Start date for batch downloads (YYYY-MM-DD)")
@click.option("--to-date", help="End date for batch downloads (YYYY-MM-DD)")
def main(
    meeting_id: str,
    output_dir: str | None,
    output_name: str | None,
    verbose: bool,
    debug: bool,
    json_mode: bool,
    list_mode: bool,
    check_availability: bool,
    recording_id: str | None,
    wait: int | None,
    skip_transcript: bool,
    skip_chat: bool,
    skip_timeline: bool,
    dry_run: bool,
    password: str | None,
    log_file: str | None,
    config: str | None,
    filename_template: str | None,
    folder_template: str | None,
    from_date: str | None,
    to_date: str | None,
) -> None:
    """
    [bold cyan]dlzoom[/bold cyan] - Download Zoom cloud recordings

    Download audio recordings and metadata from Zoom meetings.

    MEETING_ID: Zoom meeting ID or UUID
    """
    # Setup logging
    log_level = "DEBUG" if debug else ("INFO" if verbose else "WARNING")
    setup_logging(level=log_level, verbose=debug or verbose)

    # Determine output mode
    output_mode = "json" if json_mode else "human"
    formatter = OutputFormatter(output_mode)

    try:
        # Load config
        cfg = Config(env_file=config) if config else Config()

        # Choose auth mode: S2S takes precedence if configured
        use_s2s = bool(cfg.zoom_account_id and cfg.zoom_client_id and cfg.zoom_client_secret)
        user_tokens = None if use_s2s else load_tokens(cfg.tokens_path)
        if not use_s2s and user_tokens is None:
            # If neither S2S nor user tokens are available, raise config error
            raise ConfigError(
                "Missing Zoom credentials. Either set S2S env vars (ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET) or sign in with: dlzoom-login"
            )

        # Override output dir if specified
        if output_dir:
            cfg.output_dir = Path(output_dir)

        # Default output name to meeting_id, then sanitize for filesystem safety
        if not output_name:
            output_name = meeting_id
            try:
                from dlzoom.templates import TemplateParser

                parser = TemplateParser()
                output_name = parser._sanitize_filename(output_name)
            except Exception:
                # Fallback minimal sanitization if TemplateParser isn't available
                import re as _re

                unsafe_chars = r'[<>:"/\\|?*]'
                safe_name = _re.sub(unsafe_chars, "_", str(output_name))
                safe_name = _re.sub(r"[_\s]+", "_", safe_name).strip("_. ")
                output_name = safe_name

        # Initialize client per auth mode
        if use_s2s:
            cfg.validate()
            client = ZoomClient(
                str(cfg.zoom_account_id), str(cfg.zoom_client_id), str(cfg.zoom_client_secret)
            )
        else:
            client = ZoomUserClient(user_tokens, str(cfg.tokens_path))  # type: ignore[arg-type]
        selector = RecordingSelector()

        # Handle batch download mode (from_date/to_date)
        if from_date or to_date:
            _handle_batch_download(
                client=client,
                selector=selector,
                from_date=from_date,
                to_date=to_date,
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
            )
            return

        # Handle --list mode
        if list_mode:
            _handle_list_mode(client, selector, meeting_id, recording_id, formatter, json_mode)
            return

        # Handle --check-availability mode
        if check_availability:
            _handle_check_availability(
                client, selector, meeting_id, recording_id, formatter, wait, json_mode
            )
            return

        # Default: Download mode
        _handle_download_mode(
            client=client,
            selector=selector,
            meeting_id=meeting_id,
            recording_id=recording_id,
            output_dir=cfg.output_dir,
            output_name=output_name,
            skip_transcript=skip_transcript,
            skip_chat=skip_chat,
            skip_timeline=skip_timeline,
            dry_run=dry_run,
            password=password,
            log_file=Path(log_file) if log_file else None,
            formatter=formatter,
            verbose=verbose,
            debug=debug,
            json_mode=json_mode,
            wait=wait,
            filename_template=filename_template,
            folder_template=folder_template,
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

    except ConfigError as e:
        # Always log full traceback at DEBUG level for debugging
        logging.getLogger(__name__).debug("ConfigError exception caught:", exc_info=True)

        if json_mode:
            error_result = {
                "status": "error",
                "error": {
                    "code": "CONFIG_ERROR",
                    "message": str(e),
                    "details": "Check configuration file or environment variables",
                },
            }
            print(json.dumps(error_result, indent=2))
        else:
            formatter.output_error(str(e))

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


def _handle_list_mode(
    client: ZoomClient,
    selector: RecordingSelector,
    meeting_id: str,
    recording_id: str | None,
    formatter: OutputFormatter,
    json_mode: bool = False,
) -> None:
    """Handle --list mode: List all recordings for meeting"""

    # Enable silent mode if JSON to suppress intermediate messages
    if json_mode:
        formatter.set_silent(True)

    formatter.output_info(f"Fetching recordings for meeting {meeting_id}...")
    recordings = client.get_meeting_recordings(meeting_id)

    meetings = recordings.get("meetings", [])

    if not meetings:
        # Single meeting response
        if recordings.get("recording_files"):
            meetings = [recordings]
        else:
            formatter.output_error("No recordings found")
            sys.exit(1)

    # Output as JSON if json_mode
    if json_mode:
        import json

        result = {
            "status": "success",
            "command": "list",
            "meeting_id": meeting_id,
            "total_instances": len(meetings),
            "instances": [
                {
                    "uuid": m.get("uuid"),
                    "start_time": m.get("start_time"),
                    "duration": m.get("duration"),
                    "has_recording": bool(m.get("recording_files")),
                    "recording_status": (
                        m.get("recording_files", [{}])[0].get("status", "completed")
                        if m.get("recording_files")
                        else "not_found"
                    ),
                    "recording_files": [
                        f.get("recording_type") or f.get("file_type")
                        for f in m.get("recording_files", [])
                    ],
                }
                for m in meetings
            ],
        }
        print(json.dumps(result, indent=2))
        return

    # Output list of recordings (human-readable)
    console.print(f"\n[bold]Recordings for Meeting {meeting_id}[/bold]")
    console.print(f"Total instances: {len(meetings)}\n")

    for idx, meeting in enumerate(meetings, 1):
        console.print(f"[cyan]{idx}.[/cyan] {meeting.get('topic', 'N/A')}")
        console.print(f"   UUID: {meeting.get('uuid', 'N/A')}")
        console.print(f"   Start: {meeting.get('start_time', 'N/A')}")
        console.print(f"   Duration: {meeting.get('duration', 0)} minutes")
        console.print(f"   Files: {len(meeting.get('recording_files', []))}")
        console.print()


def _handle_check_availability(
    client: ZoomClient,
    selector: RecordingSelector,
    meeting_id: str,
    recording_id: str | None,
    formatter: OutputFormatter,
    wait: int | None,
    json_mode: bool = False,
) -> None:
    """Handle --check-availability mode: Check if recording is ready"""
    import json
    import time

    # Enable silent mode if JSON to suppress intermediate messages
    if json_mode:
        formatter.set_silent(True)

    formatter.output_info(f"Checking availability for meeting {meeting_id}...")

    max_wait_seconds = (wait * 60) if wait else 0
    start_time = time.time()
    poll_interval = 30  # seconds

    while True:
        try:
            recordings = client.get_meeting_recordings(meeting_id)
            meetings = recordings.get("meetings", [])

            if not meetings:
                if recordings.get("recording_files"):
                    meetings = [recordings]

            if meetings:
                # Select instance
                if recording_id:
                    instance = selector.filter_by_uuid(meetings, recording_id)
                else:
                    instance = selector.select_most_recent_instance(meetings)

                if instance:
                    recording_files = instance.get("recording_files", [])
                    recording_uuid = instance.get("uuid")

                    # Check if all files are completed
                    all_completed = all(f.get("status") == "completed" for f in recording_files)

                    # Find audio file info
                    audio_file = selector.select_best_audio(recording_files)
                    has_audio = audio_file is not None
                    audio_type = (
                        audio_file.get("file_extension", "").upper() if audio_file else None
                    )

                    if all_completed:
                        if json_mode:
                            result = {
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
                            print(json.dumps(result, indent=2))
                        else:
                            formatter.output_success(
                                f"Recording is ready ({len(recording_files)} files)"
                            )
                        return
                    else:
                        # Still processing
                        if not wait and json_mode:
                            result = {
                                "status": "success",
                                "command": "check_availability",
                                "meeting_id": meeting_id,
                                "recording_uuid": recording_uuid,
                                "available": False,
                                "recording_status": "processing",
                                "has_audio": has_audio,
                                "audio_type": audio_type,
                                "processing_time_remaining": None,
                                "ready_to_download": False,
                            }
                            print(json.dumps(result, indent=2))
                            sys.exit(1)
                        else:
                            formatter.output_info("Recording is still processing...")

        except ZoomAPIError as e:
            if "not found" in str(e).lower():
                if not wait and json_mode:
                    result = {
                        "status": "error",
                        "command": "check_availability",
                        "meeting_id": meeting_id,
                        "available": False,
                        "recording_status": "not_found",
                        "ready_to_download": False,
                        "error": {
                            "code": "RECORDING_NOT_FOUND",
                            "message": "Recording not found",
                            "details": str(e),
                        },
                    }
                    print(json.dumps(result, indent=2))
                    sys.exit(1)
                else:
                    formatter.output_info("Recording not found yet...")
            else:
                raise

        # Check if we should wait
        if wait:
            elapsed = time.time() - start_time
            if elapsed >= max_wait_seconds:
                if json_mode:
                    result = {
                        "status": "error",
                        "command": "check_availability",
                        "meeting_id": meeting_id,
                        "error": {
                            "code": "TIMEOUT",
                            "message": f"Timeout after {wait} minutes",
                            "details": (
                                "Recording did not become available within the specified wait time"
                            ),
                        },
                    }
                    print(json.dumps(result, indent=2))
                else:
                    formatter.output_error(f"Timeout after {wait} minutes")
                sys.exit(1)

            formatter.output_info(f"Waiting {poll_interval} seconds...")
            time.sleep(poll_interval)
        else:
            formatter.output_info("Recording not ready yet")
            sys.exit(1)


def _handle_batch_download(
    client: ZoomClient,
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
    filename_template: str | None = None,
    folder_template: str | None = None,
) -> None:
    """Handle batch download mode: Download multiple meetings by date range"""
    import json

    # Enable silent mode if JSON to suppress intermediate messages
    if json_mode:
        formatter.set_silent(True)

    # Initialize results tracking for JSON output
    results = []

    formatter.output_info(
        f"Fetching recordings from {from_date or 'beginning'} to {to_date or 'now'}..."
    )

    # Fetch all recordings in date range
    recordings_data = client.get_user_recordings(user_id="me", from_date=from_date, to_date=to_date)

    meetings = recordings_data.get("meetings", [])

    if not meetings:
        if json_mode:
            result: dict[str, Any] = {
                "status": "success",
                "command": "batch-download",
                "from_date": from_date,
                "to_date": to_date,
                "total_meetings": 0,
                "successful": 0,
                "failed": 0,
                "results": [],
            }
            print(json.dumps(result, indent=2))
        else:
            formatter.output_info("No recordings found in specified date range")
        return

    total_meetings = len(meetings)
    if not json_mode:
        console.print(f"\n[bold]Found {total_meetings} meeting(s) to download[/bold]\n")

    success_count = 0
    failed_count = 0

    # Download each meeting (suppress individual JSON output in batch mode)
    for idx, meeting in enumerate(meetings, 1):
        meeting_id = meeting.get("id")
        meeting_topic = meeting.get("topic", "Unknown")
        start_time = meeting.get("start_time", "")

        if not json_mode:
            console.print(
                f"[cyan]Downloading meeting {idx}/{total_meetings}:[/cyan] {meeting_topic}"
            )

        try:
            # Use meeting_id as output_name for batch downloads (unless template overrides)
            # Disable json_mode for individual downloads in batch mode
            _handle_download_mode(
                client=client,
                selector=selector,
                meeting_id=str(meeting_id),
                recording_id=None,
                output_dir=output_dir,
                output_name=str(meeting_id),
                skip_transcript=skip_transcript,
                skip_chat=skip_chat,
                skip_timeline=skip_timeline,
                dry_run=False,
                password=None,
                log_file=None,
                formatter=formatter,
                verbose=verbose,
                debug=debug,
                json_mode=False,  # Always False in batch mode to suppress individual JSON
                wait=None,
                filename_template=filename_template,
                folder_template=folder_template,
            )
            success_count += 1

            if json_mode:
                results.append(
                    {
                        "meeting_id": str(meeting_id),
                        "meeting_topic": meeting_topic,
                        "start_time": start_time,
                        "status": "success",
                    }
                )
        except Exception as e:
            failed_count += 1

            if json_mode:
                from dlzoom.exceptions import DlzoomError

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
                        "error": error_info,
                    }
                )
            else:
                formatter.output_error(f"Failed to download meeting {meeting_id}: {e}")

            if debug:
                raise

    # Output final results
    if json_mode:
        if failed_count == 0:
            status = "success"
        elif success_count > 0:
            status = "partial_success"
        else:
            status = "error"

        batch_result = {
            "status": status,
            "command": "batch-download",
            "from_date": from_date,
            "to_date": to_date,
            "total_meetings": total_meetings,
            "successful": success_count,
            "failed": failed_count,
            "results": results,
        }
        print(json.dumps(batch_result, indent=2))
    else:
        # Print summary
        console.print("\n[bold]Batch download complete:[/bold]")
        console.print(f"  Success: {success_count}/{total_meetings}")
        if failed_count > 0:
            console.print(f"  Failed: {failed_count}/{total_meetings}")


def _handle_download_mode(
    client: ZoomClient,
    selector: RecordingSelector,
    meeting_id: str,
    recording_id: str | None,
    output_dir: Path,
    output_name: str,
    skip_transcript: bool,
    skip_chat: bool,
    skip_timeline: bool,
    dry_run: bool,
    password: str | None,
    log_file: Path | None,
    formatter: OutputFormatter,
    verbose: bool,
    debug: bool,
    json_mode: bool,
    wait: int | None,
    filename_template: str | None = None,
    folder_template: str | None = None,
) -> None:
    """Handle download mode: Download recordings"""
    import json as json_lib
    import time

    # Initialize result dictionary for JSON output
    result: dict[str, Any] = {"status": "success", "meeting_id": meeting_id}
    warnings: list[str] = []

    # Enable silent mode for JSON output to suppress intermediate messages
    if json_mode:
        formatter.set_silent(True)

    # Wait for recording if --wait specified
    if wait:
        _handle_check_availability(
            client, selector, meeting_id, recording_id, formatter, wait, json_mode
        )

    formatter.output_info(f"Fetching recording info for meeting {meeting_id}...")
    recordings = client.get_meeting_recordings(meeting_id)

    # Handle response structure
    meetings = recordings.get("meetings", [])
    selection_method = None  # Track how instance was selected

    if not meetings:
        # Single meeting response
        if recordings.get("recording_files"):
            instance = recordings
            selection_method = "only_instance"
        else:
            raise RecordingNotFoundError(
                "No recording files found",
                details="The meeting may not have been recorded or the recording was deleted",
            )
    else:
        # Multiple instances
        if recording_id:
            found_instance = selector.filter_by_uuid(meetings, recording_id)
            selection_method = "user_specified"
            if not found_instance:
                formatter.output_error(f"Instance with UUID {recording_id} not found")
                sys.exit(1)
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

    # Get recording files
    recording_files = instance.get("recording_files", [])
    if not recording_files:
        raise RecordingNotFoundError(
            "No recording files found",
            details="The meeting may not have been recorded or the recording was deleted",
        )

    meeting_topic = instance.get("topic", "Zoom Recording")
    instance_start = instance.get("start_time")
    meeting_uuid = instance.get("uuid")

    # Apply templates if provided
    if filename_template or folder_template:
        parser = TemplateParser(filename_template, folder_template)

        # Build meeting data for templates
        meeting_data = {
            "meeting_id": meeting_id,
            "meeting_uuid": meeting_uuid,
            "topic": meeting_topic,
            "start_time": instance_start,
            "host_email": instance.get("host_email"),
            "host_id": instance.get("host_id"),
            "duration": instance.get("duration"),
        }

        # Apply filename template
        if filename_template:
            output_name = parser.apply_filename_template(meeting_data)

        # Apply folder template
        if folder_template:
            folder_path = parser.apply_folder_template(meeting_data)
            output_dir = output_dir / folder_path
            output_dir.mkdir(parents=True, exist_ok=True)

    # Dry run mode
    if dry_run:
        total_size = 0
        files_list = []

        for file_info in recording_files:
            file_type = file_info.get("file_type", "unknown")
            file_ext = file_info.get("file_extension", "unknown")
            file_size = file_info.get("file_size", 0)
            total_size += file_size

            # Check if would be skipped
            will_skip = (file_type in ["TRANSCRIPT", "CC"] and skip_transcript) or (
                file_type == "CHAT" and skip_chat
            )

            if json_mode:
                files_list.append(
                    {
                        "file_type": file_type,
                        "file_extension": file_ext,
                        "file_size_bytes": file_size,
                        "file_size_mb": round(file_size / 1024 / 1024, 2),
                        "will_skip": will_skip,
                    }
                )
            else:
                if will_skip:
                    console.print(
                        f"  [dim]- {file_type} ({file_ext}): "
                        f"{file_size / 1024 / 1024:.2f} MB (skipped)[/dim]"
                    )
                else:
                    console.print(f"  - {file_type} ({file_ext}): {file_size / 1024 / 1024:.2f} MB")

        if json_mode:
            dry_run_result: dict[str, Any] = {
                "status": "success",
                "command": "download",
                "dry_run": True,
                "meeting_id": meeting_id,
                "meeting_topic": meeting_topic,
                "output_name": output_name,
                "output_directory": str(output_dir.absolute()),
                "files_to_download": files_list,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
            }
            print(json_lib.dumps(dry_run_result, indent=2))
        else:
            console.print(f"\n[bold]Dry Run: Would download for meeting {meeting_id}[/bold]")
            console.print(f"Topic: {meeting_topic}")
            console.print(f"Output name: {output_name}")
            console.print(f"Output directory: {output_dir}")
            console.print("\n[bold]Files to download:[/bold]")
            console.print(f"\n[bold]Total size: {total_size / 1024 / 1024:.2f} MB[/bold]")

        return

    # Initialize downloader and extractor
    downloader = Downloader(
        output_dir,
        client._get_access_token(),
        output_name=output_name,
        overwrite=True,  # Always overwrite per PLAN.md
    )
    extractor = AudioExtractor()

    # Download files
    formatter.output_info("Downloading recording files...")

    downloaded_files = []
    audio_file = selector.select_best_audio(recording_files)

    if not audio_file:
        raise NoAudioAvailableError(
            "No audio file available for this recording",
            details="Neither M4A (audio_only) nor MP4 (video) file found",
        )

    # Track recording details for metadata and JSON output
    recording_uuid = instance.get("uuid")
    audio_file_size = audio_file.get("file_size", 0)
    audio_extracted_from_video = False
    source_file_type = audio_file.get("file_extension", "").upper()
    audio_only_available = any(
        f.get("file_type") == "M4A" or f.get("file_extension", "").upper() == "M4A"
        for f in recording_files
    )

    if audio_file:
        # Download audio file
        audio_download_url = audio_file.get("download_url")
        if not audio_download_url:
            raise DownloadError("Audio file has no download URL")

        audio_path = downloader.download_file(
            str(audio_download_url),
            audio_file,
            meeting_topic,
            instance_start,
            show_progress=not json_mode,
        )
        downloaded_files.append(audio_path)

        # Extract audio if MP4
        if audio_path.suffix.lower() == ".mp4":
            if not extractor.check_ffmpeg_available():
                raise FFmpegNotFoundError(
                    "ffmpeg not found",
                    details="Install ffmpeg to extract audio from MP4 files: https://ffmpeg.org/download.html",
                )

            formatter.output_info("Extracting audio from MP4...")
            audio_m4a_path = extractor.extract_audio(audio_path, verbose=debug or verbose)
            formatter.output_success(f"Audio extracted: {audio_m4a_path}")

            # Track that audio was extracted from video
            audio_extracted_from_video = True

            # Delete MP4 after extraction per PLAN.md
            audio_path.unlink()
            formatter.output_info(f"Deleted MP4 file: {audio_path}")

    # Download transcripts, chat, and timeline by default (unless skipped)
    if not skip_transcript or not skip_chat or not skip_timeline:
        transcript_files = downloader.download_transcripts_and_chat(
            recording_files,
            meeting_topic,
            instance_start,
            show_progress=not json_mode,
            skip_transcript=skip_transcript,
            skip_chat=skip_chat,
            skip_timeline=skip_timeline,
        )
        downloaded_files.extend([f for f in transcript_files.values() if f])

    # Fetch participants
    participants = []
    if meeting_uuid:
        try:
            formatter.output_info("Fetching participant information...")
            participants = client.get_all_participants(meeting_uuid)
        except ZoomAPIError as e:
            formatter.output_info(f"Could not fetch participants: {e}")

    # Calculate end_time from start_time + duration
    start_time = instance.get("start_time")
    duration = instance.get("duration")  # in minutes
    end_time = None

    if start_time and duration:
        try:
            # Parse ISO format: 2025-01-15T10:00:00Z
            dt_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            dt_end = dt_start + timedelta(minutes=duration)
            end_time = dt_end.isoformat().replace("+00:00", "Z")
        except Exception:
            # If parsing fails, leave end_time as None
            pass

    # Create metadata JSON
    metadata = {
        "meeting_id": meeting_id,
        "meeting_uuid": meeting_uuid,
        "meeting_title": meeting_topic,
        "topic": meeting_topic,
        "start_time": start_time,
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
            "download_url": audio_file.get("download_url"),
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
                "download_url": f.get("download_url"),
                "status": f.get("status"),
            }
            for f in recording_files
        ],
    }

    # Add multiple instances info if applicable
    if len(meetings) > 1:
        metadata["multiple_instances"] = True
        metadata["total_instances"] = len(meetings)
        metadata["selected_instance"] = selection_method
        metadata["selected_instance_uuid"] = meeting_uuid
        metadata["selected_instance_timestamp"] = instance.get("start_time")
        metadata["note"] = "Multiple recordings exist for this meeting. Use --list to see all."
        metadata["all_instances"] = [
            {
                "uuid": m.get("uuid"),
                "start_time": m.get("start_time"),
                "duration": m.get("duration"),
                "has_recording": bool(m.get("recording_files")),
            }
            for m in meetings
        ]

    # Write metadata JSON
    metadata_path = output_dir / f"{output_name}_metadata.json"
    with open(metadata_path, "w") as f:
        json_lib.dump(metadata, f, indent=2)
    formatter.output_success(f"Metadata saved: {metadata_path}")

    # Write structured log if requested
    if log_file:
        with open(log_file, "a") as f:
            for file_path in downloaded_files:
                log_entry = {
                    "meeting_id": meeting_id,
                    "meeting_uuid": meeting_uuid,
                    "file_path": str(file_path.absolute()),
                    "size_bytes": file_path.stat().st_size if file_path.exists() else 0,
                    "timestamp": time.time(),
                    "status": "completed",
                }
                f.write(json_lib.dumps(log_entry) + "\n")

    formatter.output_success(f"Downloaded {len(downloaded_files)} file(s) to {output_dir}")

    # Output structured JSON if json_mode
    if json_mode:
        # Build files dictionary with absolute paths
        files_dict = {"metadata": str(metadata_path.absolute())}

        # Find audio file (m4a)
        audio_files = [f for f in downloaded_files if f.suffix.lower() == ".m4a"]
        if audio_files:
            files_dict["audio"] = str(audio_files[0].absolute())

        # Find transcript file (vtt)
        transcript_files_list = [f for f in downloaded_files if f.suffix.lower() == ".vtt"]
        if transcript_files_list:
            files_dict["transcript"] = str(transcript_files_list[0].absolute())

        # Find chat file (txt)
        chat_files = [
            f for f in downloaded_files if f.suffix.lower() == ".txt" and "chat" in f.name.lower()
        ]
        if chat_files:
            files_dict["chat"] = str(chat_files[0].absolute())

        # Build metadata summary with corrected field names
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

        # Build final result with required top-level fields
        result["recording_uuid"] = str(recording_uuid) if recording_uuid else ""
        result["output_name"] = str(output_name)
        result["files"] = files_dict
        result["metadata_summary"] = metadata_summary

        # Add multiple_instances section ONLY if multiple exist
        if len(meetings) > 1:
            multi_inst: dict[str, Any] = {
                "has_multiple": True,
                "total_count": len(meetings),
                "selected": str(selection_method) if selection_method else "",
                "selected_timestamp": str(instance.get("start_time", "")),
                "note": "Multiple recordings exist for this meeting. Use --list to see all.",
            }
            result["multiple_instances"] = multi_inst

        # Add warnings if any
        if warnings:
            result["status"] = "partial_success"
            result["warnings"] = warnings

        # Output single JSON object
        print(json_lib.dumps(result, indent=2))


if __name__ == "__main__":
    main()
