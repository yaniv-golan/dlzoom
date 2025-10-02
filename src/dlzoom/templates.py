"""
Template parsing for custom filenames and folders
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import re


class TemplateParser:
    """Parse and apply filename/folder templates"""

    def __init__(self, filename_template: Optional[str] = None, folder_template: Optional[str] = None):
        self.filename_template = filename_template
        self.folder_template = folder_template
        self.logger = logging.getLogger(__name__)

    def apply_filename_template(self, meeting_data: Dict[str, Any], file_type: str = "audio") -> str:
        """
        Apply filename template to meeting data

        Args:
            meeting_data: Dict with keys like topic, start_time, meeting_id, etc.
            file_type: Type of file (audio, transcript, chat, metadata)

        Returns:
            Formatted filename (without extension)
        """
        if not self.filename_template:
            # Default: meeting_id
            return meeting_data.get("meeting_id", "recording")

        return self._format_template(self.filename_template, meeting_data)

    def apply_folder_template(self, meeting_data: Dict[str, Any]) -> Path:
        """
        Apply folder template to meeting data

        Args:
            meeting_data: Dict with keys like topic, start_time, meeting_id, etc.

        Returns:
            Path object for folder structure
        """
        if not self.folder_template:
            # Default: current directory
            return Path(".")

        folder_str = self._format_template(self.folder_template, meeting_data)
        return Path(folder_str)

    def _format_template(self, template: str, data: Dict[str, Any]) -> str:
        """
        Format template string with data

        Supports:
        - {topic} - meeting topic
        - {meeting_id} - meeting ID
        - {host_email} - host email
        - {start_time:%Y%m%d} - formatted date/time from start_time
        - {start_time:%Y/%m/%d} - folder-style date paths

        Args:
            template: Template string with placeholders
            data: Data dictionary

        Returns:
            Formatted string
        """
        result = template

        # Handle datetime formatting: {start_time:%Y%m%d}
        datetime_pattern = r'\{start_time:([^}]+)\}'
        for match in re.finditer(datetime_pattern, result):
            format_str = match.group(1)
            start_time = data.get("start_time", "")

            if start_time:
                try:
                    # Parse ISO format: 2025-09-30T12:00:35Z
                    dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    formatted = dt.strftime(format_str)
                    result = result.replace(match.group(0), formatted)
                except (ValueError, TypeError) as e:
                    # Expected parse errors - log warning and use empty string
                    self.logger.warning(
                        f"Failed to parse date '{start_time}' with format '{format_str}' "
                        f"in template: {e}. Using empty string for {match.group(0)}"
                    )
                    result = result.replace(match.group(0), "")
                except Exception as e:
                    # Unexpected error - log error and re-raise
                    self.logger.error(
                        f"Unexpected error parsing template date placeholder {match.group(0)}: {e}"
                    )
                    raise RuntimeError(
                        f"Template parsing failed for date placeholder: {e}"
                    ) from e

        # Handle simple placeholders
        simple_placeholders = {
            "{topic}": data.get("topic", ""),
            "{meeting_id}": str(data.get("meeting_id", "")),
            "{meeting_uuid}": data.get("meeting_uuid", ""),
            "{host_email}": data.get("host_email", ""),
            "{host_id}": data.get("host_id", ""),
            "{duration}": str(data.get("duration", "")),
        }

        for placeholder, value in simple_placeholders.items():
            if placeholder in result:
                # Sanitize value for filenames
                safe_value = self._sanitize_filename(str(value))
                result = result.replace(placeholder, safe_value)

        return result

    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize string for use in filenames

        Args:
            name: String to sanitize

        Returns:
            Safe filename string
        """
        # Replace unsafe characters
        unsafe_chars = r'[<>:"/\\|?*]'
        safe_name = re.sub(unsafe_chars, "_", name)

        # Collapse multiple underscores/spaces
        safe_name = re.sub(r'[_\s]+', '_', safe_name)

        # Remove leading/trailing underscores/dots
        safe_name = safe_name.strip("_. ")

        return safe_name


class TemplateError(Exception):
    """Template parsing error"""
    pass
