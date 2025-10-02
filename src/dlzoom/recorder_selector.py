"""
Recording selector - chooses best recording from multiple instances
"""

import logging
from typing import Any


class RecordingSelector:
    """Select best recording from meeting instances"""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def select_best_audio(self, recording_files: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Select best audio recording with priority order"""
        # Priority: M4A audio_only > M4A other types > MP4 video

        self.logger.info(f"Selecting best audio from {len(recording_files)} recording files")

        # Check for audio_only (any format)
        for file in recording_files:
            if file.get("file_type") == "audio_only":
                file_ext = file.get("file_extension")
                if file_ext != "M4A":
                    self.logger.warning(
                        f"Zoom bug: audio_only returned as {file_ext}, expected M4A"
                    )
                self.logger.info(f"Selected audio_only file: {file_ext} (highest priority)")
                return file

        # Check for other M4A files
        for file in recording_files:
            if file.get("file_extension") == "M4A":
                file_type = file.get("file_type", "unknown")
                self.logger.info(f"Selected M4A file (type: {file_type})")
                return file

        # Fallback to MP4 video (will need extraction)
        for file in recording_files:
            if file.get("file_extension") == "MP4":
                self.logger.info("Selected MP4 video file (will extract audio)")
                return file

        self.logger.warning("No suitable audio file found (no M4A or MP4)")
        return None

    def select_most_recent_instance(self, instances: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Select most recent meeting instance"""
        if not instances:
            return None

        # Sort by start_time descending
        sorted_instances = sorted(instances, key=lambda x: x.get("start_time", ""), reverse=True)

        return sorted_instances[0]

    def filter_by_uuid(self, instances: list[dict[str, Any]], uuid: str) -> dict[str, Any] | None:
        """Find specific instance by UUID"""
        for instance in instances:
            if instance.get("uuid") == uuid:
                return instance
        return None

    def detect_multiple_instances(self, recordings: dict[str, Any]) -> bool:
        """Detect if recording has multiple instances (PMI/recurring)"""
        meetings = recordings.get("meetings", [])
        return len(meetings) > 1
