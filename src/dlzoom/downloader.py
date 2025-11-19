"""
File downloader with streaming, progress tracking, and retry logic
"""

import copy
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

import requests
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from dlzoom.exceptions import DownloadFailedError as DownloadError


class Downloader:
    """Download files with streaming, progress bars, and retry logic"""

    def __init__(
        self,
        output_dir: Path,
        access_token: str,
        output_name: str | None = None,
        overwrite: bool = False,
        *,
        stj_context: dict[str, Any] | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.access_token = access_token
        self.output_name = output_name
        self.overwrite = overwrite
        self.logger = logging.getLogger(__name__)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stj_context = stj_context

    def _context_for_stj(self, *, timeline_path: Path, stj_path: Path) -> dict[str, Any] | None:
        if not self.stj_context:
            return None
        ctx = copy.deepcopy(self.stj_context)
        generated = ctx.setdefault("generated", {})
        generated["timeline_path"] = str(timeline_path)
        generated["stj_output_path"] = str(stj_path)
        return ctx

    def check_disk_space(self, required_bytes: int) -> bool:
        """
        Check if sufficient disk space is available

        Args:
            required_bytes: Required space in bytes

        Returns:
            True if sufficient space available

        Raises:
            DiskSpaceError: If insufficient disk space

        Note:
            This check has a TOCTOU (Time-Of-Check-Time-Of-Use) race condition.
            Actual writes are also wrapped in try/except to catch ENOSPC errors.
        """
        try:
            stat = shutil.disk_usage(self.output_dir)
            available = stat.free
            # Add 100MB buffer
            required_with_buffer = required_bytes + (100 * 1024 * 1024)

            if available < required_with_buffer:
                from dlzoom.exceptions import DiskSpaceError

                raise DiskSpaceError(
                    f"Insufficient disk space in {self.output_dir}",
                    details=(
                        f"Required: {required_with_buffer / 1024 / 1024:.2f} MB "
                        f"(including 100 MB buffer), "
                        f"Available: {available / 1024 / 1024:.2f} MB"
                    ),
                )
            return True
        except OSError as e:
            # If we can't check disk space, log warning and proceed optimistically
            self.logger.warning(f"Could not check disk space: {e}")
            return True

    def _unique_suffix(self, file_info: dict[str, Any]) -> str:
        """Return sanitized suffix derived from recording identifiers."""
        candidates = [
            str(file_info.get("id") or ""),
            str(file_info.get("recording_id") or ""),
            str(file_info.get("recording_file_id") or ""),
        ]
        for raw in candidates:
            raw = raw.strip()
            if raw:
                safe = "".join(c if c.isalnum() else "_" for c in raw)
                return f"_{safe}"
        recording_type = file_info.get("recording_type") or file_info.get("file_type")
        if recording_type:
            safe = "".join(c if c.isalnum() else "_" for c in str(recording_type))
            return f"_{safe.lower()}"
        return ""

    def _ensure_unique_path(self, desired_path: Path) -> Path:
        """Return a unique path by appending a numeric suffix when needed."""
        if self.overwrite or not desired_path.exists():
            return desired_path

        stem = desired_path.stem
        suffix = desired_path.suffix
        counter = 2
        while True:
            candidate = desired_path.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def generate_filename(
        self, file_info: dict[str, Any], meeting_topic: str, instance_start: str | None = None
    ) -> str:
        """
        Generate safe filename from recording metadata

        Args:
            file_info: Recording file metadata
            meeting_topic: Meeting topic/name
            instance_start: Optional instance start time for recurring meetings

        Returns:
            Safe filename
        """
        # Get file type and extension
        file_type = file_info.get("file_type", "recording")
        file_ext = file_info.get("file_extension", "mp4").lower()

        # Use output_name if specified (per PLAN.md naming)
        if self.output_name:
            # For audio/video files: {output_name}.{ext}
            if file_type in [
                "MP4",
                "M4A",
                "audio_only",
                "shared_screen_with_speaker_view",
                "shared_screen_with_gallery_view",
                "active_speaker",
                "gallery_view",
            ]:
                return f"{self.output_name}.{file_ext}"
            # For transcripts: {output_name}_transcript_<id>.vtt
            elif file_type in ["TRANSCRIPT", "CC"]:
                suffix = self._unique_suffix(file_info)
                return f"{self.output_name}_transcript{suffix}.{file_ext}"
            # For chat: {output_name}_chat_<id>.txt
            elif file_type == "CHAT":
                suffix = self._unique_suffix(file_info)
                return f"{self.output_name}_chat{suffix}.{file_ext}"
            # For timeline: {output_name}_timeline_<id>.json
            elif "TIMELINE" in file_type:
                suffix = self._unique_suffix(file_info)
                return f"{self.output_name}_timeline{suffix}.{file_ext}"
            # Default
            else:
                return f"{self.output_name}_{file_type}.{file_ext}"

        # Fallback: Use meeting topic and timestamp (original logic)
        # Sanitize meeting topic
        safe_topic = "".join(
            c if c.isalnum() or c in (" ", "-", "_") else "_" for c in meeting_topic
        ).strip()

        recording_type = file_info.get("recording_type", "")

        # Build filename with unique identifier
        base_name = safe_topic
        if instance_start:
            timestamp = instance_start.replace(":", "-").replace("T", "_").split(".")[0]
            base_name = f"{base_name}_{timestamp}"

        # Add recording type if it's informative
        if recording_type and recording_type.lower() != file_type.lower():
            return f"{base_name}_{recording_type}_{file_type}.{file_ext}"

        # Use recording_id to make unique if available
        recording_id = file_info.get("id", "")
        if recording_id:
            return f"{base_name}_{file_type}_{recording_id}.{file_ext}"

        return f"{base_name}_{file_type}.{file_ext}"

    def file_exists_with_size(self, file_path: Path, expected_size: int) -> bool:
        """
        Check if file exists with expected size (deduplication)

        Args:
            file_path: Path to check
            expected_size: Expected file size in bytes

        Returns:
            True if file exists with matching size
        """
        if not file_path.exists():
            return False

        actual_size = file_path.stat().st_size
        return actual_size == expected_size

    def download_file(
        self,
        download_url: str,
        file_info: dict[str, Any],
        meeting_topic: str,
        instance_start: str | None = None,
        show_progress: bool = True,
        verify_size: bool = False,
        retry_count: int = 3,
        backoff_factor: float = 2.0,
    ) -> Path:
        """
        Download file with streaming, progress bar, retry logic, and resume capability

        Args:
            download_url: File download URL
            file_info: Recording file metadata
            meeting_topic: Meeting topic/name
            instance_start: Optional instance start time
            show_progress: Show progress bar
            verify_size: Verify file size after download (not a cryptographic
                checksum). Default False for compatibility with mocked/test
                environments.
            retry_count: Number of retry attempts
            backoff_factor: Exponential backoff factor

        Returns:
            Path to downloaded file

        Raises:
            DownloadError: If download fails after retries
        """
        # Generate filename
        filename = self.generate_filename(file_info, meeting_topic, instance_start)
        output_path = self.output_dir / filename
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

        # Check if file already exists (deduplication)
        # Defensive cast: Zoom API sometimes returns file_size as string
        try:
            expected_size = int(file_info.get("file_size", 0) or 0)
        except (ValueError, TypeError):
            expected_size = 0

        if not self.overwrite and self.file_exists_with_size(output_path, expected_size):
            self.logger.info(f"File already exists, skipping: {filename}")
            return output_path

        # Check disk space
        if expected_size > 0 and not self.check_disk_space(expected_size):
            raise DownloadError(
                f"Insufficient disk space for {filename} "
                f"(required: {expected_size / 1024 / 1024:.2f} MB)"
            )

        # Check for existing partial download
        resume_from = 0
        if temp_path.exists():
            resume_from = temp_path.stat().st_size
            if resume_from > 0:
                self.logger.info(
                    f"Found partial download, will attempt resume from {resume_from} bytes"
                )

        # Validate download URL scheme/host to prevent misuse
        try:
            from urllib.parse import urlparse

            parsed = urlparse(str(download_url))
            host = parsed.netloc.lower()
            # Allow zoom.us, zoomgov.com, and regional variants
            allowed_domains = [
                "zoom.us",
                ".zoom.us",
                "zoomgov.com",
                ".zoomgov.com",
                "zoom.com.cn",
                ".zoom.com.cn",
            ]
            is_allowed = any(
                host == domain.lstrip(".") or host.endswith(domain) for domain in allowed_domains
            )
            if parsed.scheme != "https" or not is_allowed:
                raise DownloadError(f"Refusing to download from untrusted URL: {download_url}")
        except Exception as e:
            if isinstance(e, DownloadError):
                raise
            raise DownloadError(f"Invalid download URL: {download_url}")

        # Add access token as query parameter (NOT in Authorization header)
        # This is CRITICAL for password-protected recordings
        from urllib.parse import urlencode

        separator = "&" if "?" in download_url else "?"
        url_with_token = (
            f"{download_url}{separator}" f"{urlencode({'access_token': self.access_token})}"
        )

        # Retry loop
        for attempt in range(retry_count):
            try:
                # Check if server supports resume (Accept-Ranges header)
                headers = {}
                if resume_from > 0:
                    headers["Range"] = f"bytes={resume_from}-"

                # Stream download with progress bar
                response = requests.get(url_with_token, stream=True, timeout=30, headers=headers)

                # Handle resume
                if resume_from > 0:
                    if response.status_code == 206:  # Partial Content
                        self.logger.info(
                            f"Server supports resume, continuing from {resume_from} bytes"
                        )
                        mode = "ab"  # Append mode
                    elif response.status_code == 200:
                        # Server doesn't support resume, start over
                        self.logger.warning(
                            "Server doesn't support resume (no Accept-Ranges), starting over"
                        )
                        resume_from = 0
                        mode = "wb"
                        if temp_path.exists():
                            temp_path.unlink()
                    elif response.status_code == 416:  # Range Not Satisfiable
                        # File is already complete - verify size before accepting
                        actual_size = temp_path.stat().st_size
                        if expected_size > 0 and actual_size != expected_size:
                            self.logger.warning(
                                f"416 response but size mismatch: expected {expected_size}, "
                                f"got {actual_size}. Re-downloading from start."
                            )
                            temp_path.unlink()
                            resume_from = 0
                            mode = "wb"
                            # Retry without Range header
                            continue
                        self.logger.info("Partial download is complete (verified size)")
                        temp_path.rename(output_path)
                        return output_path
                    else:
                        response.raise_for_status()
                        mode = "wb"
                else:
                    response.raise_for_status()
                    mode = "wb"

                # Get total size
                if response.status_code == 206:
                    # Partial content - parse Content-Range header
                    content_range = response.headers.get("content-range", "")
                    if content_range:
                        # Format: bytes 1024-2047/2048
                        parts = content_range.split("/")
                        if len(parts) == 2:
                            total_size = int(parts[1])
                        else:
                            total_size = (
                                int(response.headers.get("content-length", 0)) + resume_from
                            )
                    else:
                        total_size = int(response.headers.get("content-length", 0)) + resume_from
                else:
                    total_size = int(response.headers.get("content-length", 0))

                # Validate size matches metadata (adaptive tolerance)
                if expected_size > 0:
                    if total_size == 0:
                        self.logger.warning(
                            f"Server reported 0 bytes but expected {expected_size} bytes"
                        )
                    elif total_size > 0:
                        size_diff = abs(total_size - expected_size)
                        size_diff_pct = size_diff / expected_size

                        # Use smaller tolerance for small files, larger for big files
                        # 2% for files < 10MB, 5% for larger files
                        tolerance = 0.02 if expected_size < 10_000_000 else 0.05

                        if size_diff_pct > tolerance:
                            self.logger.warning(
                                f"Size mismatch (exceeds {tolerance * 100:.0f}% tolerance): "
                                f"expected {expected_size}, got {total_size} "
                                f"(diff: {size_diff_pct * 100:.1f}%)"
                            )

                # Download with or without progress
                if show_progress:
                    self._download_with_progress(
                        response, temp_path, total_size, filename, mode, resume_from
                    )
                else:
                    self._download_without_progress(response, temp_path, mode)

                # Verify size if requested
                if verify_size and expected_size > 0:
                    actual_size = temp_path.stat().st_size

                    if actual_size == 0:
                        self.logger.error(
                            f"Downloaded file is empty (0 bytes) but expected {expected_size} bytes"
                        )
                    else:
                        size_diff = abs(actual_size - expected_size)
                        size_diff_pct = size_diff / expected_size

                        # Use smaller tolerance for small files, larger for big files
                        # 2% for files < 10MB, 5% for larger files
                        tolerance = 0.02 if expected_size < 10_000_000 else 0.05

                        if size_diff_pct > tolerance:
                            self.logger.error(
                                f"Downloaded file size mismatch (exceeds "
                                f"{tolerance * 100:.0f}% tolerance): "
                                f"expected {expected_size}, got {actual_size} "
                                f"(diff: {size_diff_pct * 100:.1f}%). "
                                "File may be corrupted."
                            )
                            raise DownloadError(
                                "Downloaded file size mismatch for "
                                f"{filename}: expected {expected_size}, got {actual_size}"
                            )

                # Move temp file to final location (atomic operation)
                try:
                    # os.replace() is atomic on POSIX systems
                    os.replace(str(temp_path), str(output_path))
                except OSError:
                    # Fallback for cross-filesystem moves
                    shutil.move(str(temp_path), str(output_path))

                self.logger.info(f"Downloaded: {filename}")
                return output_path

            except Exception as e:
                # Check if URL expired (403/401 errors)
                url_expired = False
                if hasattr(e, "response") and e.response is not None:
                    if e.response.status_code in [401, 403]:
                        url_expired = True
                        self.logger.warning(
                            "Download URL may have expired (403/401 error). "
                            "Zoom download URLs are time-limited. "
                            "Re-run the download command to get a fresh URL."
                        )

                # Don't clean up temp file if URL expired - allow resume next time
                if not url_expired and temp_path.exists():
                    temp_path.unlink()

                if attempt < retry_count - 1 and not url_expired:
                    wait_time = backoff_factor * (2**attempt)
                    self.logger.warning(
                        f"Download failed (attempt {attempt + 1}/{retry_count}), "
                        f"retrying in {wait_time:.1f}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    # Sanitize error message to avoid leaking access_token from URL
                    error_msg = str(e)
                    if "access_token=" in error_msg:
                        error_msg = error_msg.split("access_token=")[0] + "access_token=[REDACTED]"

                    if url_expired:
                        raise DownloadError(
                            "Download URL expired. Re-run command to get fresh URL and resume: "
                            f"{error_msg}"
                        ) from e
                    else:
                        raise DownloadError(
                            f"Download failed after {retry_count} attempts: {error_msg}"
                        ) from e

        raise DownloadError(f"Download failed: {filename}")

    def _download_with_progress(
        self,
        response: requests.Response,
        output_path: Path,
        total_size: int,
        filename: str,
        mode: str = "wb",
        resume_from: int = 0,
    ) -> None:
        """Download with rich progress bar"""
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(
                f"Downloading {filename}", total=total_size, completed=resume_from
            )

            try:
                with open(output_path, mode) as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
            except OSError as e:
                # Handle disk full error (ENOSPC)
                if e.errno == 28:  # errno.ENOSPC
                    from dlzoom.exceptions import DiskSpaceError

                    raise DiskSpaceError(
                        f"Disk full while downloading {filename}",
                        details=f"Failed to write to {output_path}: {e}",
                    ) from e
                else:
                    raise  # Re-raise other OS errors

    def _download_without_progress(
        self, response: requests.Response, output_path: Path, mode: str = "wb"
    ) -> None:
        """Download without progress bar"""
        try:
            with open(output_path, mode) as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        except OSError as e:
            # Handle disk full error (ENOSPC)
            if e.errno == 28:  # errno.ENOSPC
                from dlzoom.exceptions import DiskSpaceError

                raise DiskSpaceError(
                    f"Disk full while downloading to {output_path}", details=f"Failed to write: {e}"
                ) from e
            else:
                raise  # Re-raise other OS errors

    def download_all_files(
        self,
        recording_files: list[dict[str, Any]],
        meeting_topic: str,
        instance_start: str | None = None,
        show_progress: bool = True,
        file_types: list[str] | None = None,
    ) -> list[Path]:
        """
        Download all recording files for a meeting

        Args:
            recording_files: List of recording file metadata
            meeting_topic: Meeting topic/name
            instance_start: Optional instance start time
            show_progress: Show progress bars
            file_types: Optional filter for file types (e.g., ["MP4", "M4A", "VTT"])

        Returns:
            List of downloaded file paths
        """
        downloaded_files = []

        for file_info in recording_files:
            # Filter by file type if specified
            if file_types:
                file_ext = file_info.get("file_extension", "").upper()
                if file_ext not in file_types:
                    continue

            download_url = file_info.get("download_url")
            if not download_url:
                self.logger.warning(f"No download URL for file: {file_info}")
                continue

            try:
                file_path = self.download_file(
                    download_url, file_info, meeting_topic, instance_start, show_progress
                )
                downloaded_files.append(file_path)
            except DownloadError as e:
                self.logger.error(f"Failed to download file: {e}")
                continue

        return downloaded_files

    def download_transcripts_and_chat(
        self,
        recording_files: list[dict[str, Any]],
        meeting_topic: str,
        instance_start: str | None = None,
        show_progress: bool = True,
        skip_transcript: bool = False,
        skip_chat: bool = False,
        skip_timeline: bool = False,
        # STJ generation controls
        skip_speakers: bool | None = None,
        speakers_mode: str = "first",
        stj_min_segment_sec: float = 1.0,
        stj_merge_gap_sec: float = 1.5,
        include_unknown: bool = False,
    ) -> dict[str, list[Path]]:
        """
        Download transcripts (VTT), chat (TXT), and timeline (JSON) files

        Args:
            recording_files: List of recording file metadata
            meeting_topic: Meeting topic
            instance_start: Optional instance start time
            show_progress: Show progress bars
            skip_transcript: Skip transcript download
            skip_chat: Skip chat download
            skip_timeline: Skip timeline download

        Returns:
            Dict with keys: vtt, txt, timeline, speakers (values are lists of Paths)
        """
        result: dict[str, list[Path]] = {"vtt": [], "txt": [], "timeline": [], "speakers": []}

        for file_info in recording_files:
            file_ext = (file_info.get("file_extension") or "").upper()
            file_type_value = (file_info.get("file_type") or "").upper()
            recording_type_value = (file_info.get("recording_type") or "").upper()
            combined_type = f"{file_type_value} {recording_type_value}"

            # VTT (closed captions/transcripts)
            if file_ext == "VTT":
                if skip_transcript:
                    self.logger.info("Skipping transcript download")
                    continue

                download_url = file_info.get("download_url")
                if not download_url:
                    self.logger.warning("VTT file has no download URL, skipping")
                    continue

                try:
                    path = self.download_file(
                        str(download_url),
                        file_info,
                        meeting_topic,
                        instance_start,
                        show_progress,
                    )
                    result["vtt"].append(path)
                except DownloadError as e:
                    self.logger.error(f"Failed to download VTT: {e}")

            # TXT (chat)
            elif file_ext == "TXT":
                if skip_chat:
                    self.logger.info("Skipping chat download")
                    continue

                download_url = file_info.get("download_url")
                if not download_url:
                    self.logger.warning("Chat file has no download URL, skipping")
                    continue

                try:
                    path = self.download_file(
                        str(download_url),
                        file_info,
                        meeting_topic,
                        instance_start,
                        show_progress,
                    )
                    result["txt"].append(path)
                except DownloadError as e:
                    self.logger.error(f"Failed to download chat: {e}")

            # JSON/TIMELINE
            elif "TIMELINE" in combined_type:
                if skip_timeline:
                    self.logger.info("Skipping timeline download")
                    continue

                download_url = file_info.get("download_url")
                if not download_url:
                    self.logger.warning("Timeline file has no download URL, skipping")
                    continue

                try:
                    path = self.download_file(
                        str(download_url),
                        file_info,
                        meeting_topic,
                        instance_start,
                        show_progress,
                    )
                    result["timeline"].append(path)

                    # Generate minimal STJ speakers file by default unless disabled
                    try:
                        # honor explicit skip_speakers if provided; else check env default
                        do_skip_speakers = False
                        if skip_speakers is None:
                            import os as _os

                            env_val = _os.getenv("DLZOOM_SPEAKERS", "1")
                            normalized = env_val.strip().lower()
                            do_skip_speakers = normalized in ("0", "false", "no", "off")
                        else:
                            do_skip_speakers = bool(skip_speakers)

                        if not do_skip_speakers:
                            from dlzoom.stj_minimizer import write_minimal_stj_from_file

                            # Compute output path using template-driven base name when available
                            if self.output_name:
                                stj_filename = f"{self.output_name}_speakers.stjson"
                            else:
                                stj_base = Path(path).stem
                                speaker_suffix = self._unique_suffix(file_info)
                                stj_filename = f"{stj_base}_speakers{speaker_suffix}.stjson"

                            stj_path = self._ensure_unique_path(self.output_dir / stj_filename)

                            self.logger.info(
                                f"Generating minimal STJ speakers file: {stj_path.name}"
                            )
                            context_payload = self._context_for_stj(
                                timeline_path=path, stj_path=stj_path
                            )
                            write_minimal_stj_from_file(
                                timeline_path=path,
                                output_path=stj_path,
                                duration_sec=None,
                                mode=speakers_mode,
                                min_segment_sec=stj_min_segment_sec,
                                merge_gap_sec=stj_merge_gap_sec,
                                include_unknown=include_unknown,
                                context=context_payload,
                            )
                            result["speakers"].append(stj_path)
                    except Exception as e:
                        self.logger.error(f"Failed to generate STJ speakers file: {e}")
                except DownloadError as e:
                    self.logger.error(f"Failed to download timeline: {e}")

        return result
