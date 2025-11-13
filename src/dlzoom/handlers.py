"""
Handlers for dlzoom CLI commands.

This module contains heavier helper functions extracted from cli.py to reduce
complexity in the Click command definitions. Behavior is unchanged.
"""

from __future__ import annotations

import json as _json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from rich.console import Console

from dlzoom.audio_extractor import AudioExtractor
from dlzoom.downloader import Downloader, DownloadError
from dlzoom.exceptions import (
    DlzoomError,
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


def json_dumps(data: Any) -> str:
    return _json.dumps(data, indent=2)


def _handle_check_availability(
    client: ZoomClient | ZoomUserClient,
    selector: RecordingSelector,
    meeting_id: str,
    recording_id: str | None,
    formatter: OutputFormatter,
    wait: int | None,
    json_mode: bool = False,
) -> None:
    """Handle --check-availability mode: Check if recording is ready."""
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
                            print(_json.dumps(result, indent=2))
                        else:
                            formatter.output_success(
                                f"Recording is ready ({len(recording_files)} files)"
                            )
                        return
                    else:
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
                            }
                            print(_json.dumps(result, indent=2))
                            return

                        if not wait:
                            formatter.output_info(
                                "Recording is still processing. Use --wait to wait "
                                "until it's ready."
                            )
                            return

                        elapsed = time.time() - start_time
                        remaining = max(0, max_wait_seconds - int(elapsed))

                        if elapsed >= max_wait_seconds:
                            if json_mode:
                                result = {
                                    "status": "success",
                                    "command": "check_availability",
                                    "meeting_id": meeting_id,
                                    "recording_uuid": recording_uuid,
                                    "available": False,
                                    "recording_status": "processing",
                                    "has_audio": has_audio,
                                    "audio_type": audio_type,
                                    "processing_time_remaining": 0,
                                }
                                print(_json.dumps(result, indent=2))
                            else:
                                formatter.output_info(
                                    "Recording is still processing (wait timed out)"
                                )
                            return

                        if not json_mode:
                            formatter.output_info(
                                "Recording is processing; checking again in "
                                f"{poll_interval} seconds (time left: "
                                f"{remaining // 60}m {remaining % 60}s)"
                            )
                        time.sleep(poll_interval)
                        continue

            if json_mode:
                error = {
                    "status": "error",
                    "error": {
                        "code": "RECORDING_NOT_FOUND",
                        "message": "Recording not found",
                    },
                }
                print(_json.dumps(error, indent=2))
                return
            formatter.output_error("Recording not found")
            return

        except ZoomAPIError as e:
            if json_mode:
                print(
                    _json.dumps(
                        {
                            "status": "error",
                            "error": {"code": "ZOOM_API_ERROR", "message": str(e)},
                        },
                        indent=2,
                    )
                )
                return
            formatter.output_error(f"Zoom API error: {e}")
            return


def _handle_batch_download(
    client: ZoomClient | ZoomUserClient,
    selector: RecordingSelector,
    from_date: str | None,
    to_date: str | None,
    output_dir: Path,
    skip_transcript: bool,
    skip_chat: bool,
    skip_timeline: bool,
    skip_speakers: bool | None,
    speakers_mode: str,
    stj_min_segment_sec: float,
    stj_merge_gap_sec: float,
    include_unknown: bool,
    formatter: OutputFormatter,
    verbose: bool,
    debug: bool,
    json_mode: bool,
    filename_template: str | None,
    folder_template: str | None,
) -> None:
    """Batch download helper used by the `download` command when a date range is supplied."""

    # Query user recordings across the date window
    items: list[dict[str, Any]] = []
    next_token = None
    while True:
        resp = client.get_user_recordings(
            user_id="me",
            from_date=from_date,
            to_date=to_date,
            page_size=300,
            next_page_token=next_token,
        )
        meetings = resp.get("meetings", [])
        for m in meetings:
            items.append(m)
        next_token = resp.get("next_page_token")
        if not next_token:
            break

    if not items:
        if json_mode:
            print(
                json_dumps(
                    {
                        "status": "success",
                        "command": "batch-download",
                        "from_date": from_date,
                        "to_date": to_date,
                        "total_meetings": 0,
                        "results": [],
                    }
                )
            )
            return
        formatter.output_info("No recordings found in the specified date range")
        return

    # Sort items by start time (newest first)
    def _parse_start_time(rec: dict[str, Any]) -> float:
        try:
            start = rec.get("start_time", "")
            return datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    items.sort(key=_parse_start_time, reverse=True)

    total_meetings = len(items)
    success_count = 0
    failed_count = 0
    results: list[dict[str, Any]] = []

    for m in items:
        meeting_id = m.get("id") or m.get("meeting_id")
        meeting_topic = m.get("topic", "Zoom Recording")
        start_time = m.get("start_time")
        try:
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
                skip_speakers=skip_speakers,
                speakers_mode=speakers_mode,
                stj_min_segment_sec=stj_min_segment_sec,
                stj_merge_gap_sec=stj_merge_gap_sec,
                include_unknown=include_unknown,
                dry_run=False,
                log_file=None,
                formatter=formatter,
                verbose=verbose,
                debug=debug,
                json_mode=False,  # suppress individual JSON
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
            "results": results,
        }
        print(_json.dumps(batch_result, indent=2))
    else:
        console.print("\n[bold]Batch download complete:[/bold]")
        console.print(f"  Success: {success_count}/{total_meetings}")
        if failed_count > 0:
            console.print(f"  Failed: {failed_count}/{total_meetings}")


def _handle_download_mode(
    client: ZoomClient | ZoomUserClient,
    selector: RecordingSelector,
    meeting_id: str,
    recording_id: str | None,
    output_dir: Path,
    output_name: str,
    skip_transcript: bool,
    skip_chat: bool,
    skip_timeline: bool,
    skip_speakers: bool | None,
    speakers_mode: str,
    stj_min_segment_sec: float,
    stj_merge_gap_sec: float,
    include_unknown: bool,
    dry_run: bool,
    log_file: Path | None,
    formatter: OutputFormatter,
    verbose: bool,
    debug: bool,
    json_mode: bool,
    wait: int | None,
    filename_template: str | None = None,
    folder_template: str | None = None,
) -> None:
    """Handle download mode: Download recordings."""

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
    downloader = Downloader(output_dir, access_token, output_name)
    extractor = AudioExtractor()
    downloaded_files: list[Path] = []

    audio_file = selector.select_best_audio(recording_files)
    if not audio_file:
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

    audio_file_size = int(audio_file.get("file_size", 0) or 0)
    audio_extracted_from_video = False
    source_file_type = audio_file.get("file_extension", "").upper()
    # Check for audio-only files (M4A extension or audio_only file type)
    audio_only_available = any(
        f.get("file_extension", "").upper() == "M4A" or f.get("file_type") == "audio_only"
        for f in recording_files
    )

    if audio_file:
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

        if audio_path.suffix.lower() == ".mp4":
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
        downloaded_files.extend([f for f in transcript_files.values() if f])

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
    formatter.output_success(f"Metadata saved: {metadata_path}")

    # Write structured log if requested
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                for file_path in downloaded_files:
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

    formatter.output_success(f"Downloaded {len(downloaded_files)} file(s) to {output_dir}")

    if json_mode:
        files_dict = {"metadata": str(metadata_path.absolute())}
        audio_files = [f for f in downloaded_files if f.suffix.lower() == ".m4a"]
        if audio_files:
            files_dict["audio"] = str(audio_files[0].absolute())
        transcript_files_list = [f for f in downloaded_files if f.suffix.lower() == ".vtt"]
        if transcript_files_list:
            files_dict["transcript"] = str(transcript_files_list[0].absolute())
        chat_files = [
            f for f in downloaded_files if f.suffix.lower() == ".txt" and "chat" in f.name.lower()
        ]
        if chat_files:
            files_dict["chat"] = str(chat_files[0].absolute())

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
