"""
Output formatters for different output modes (JSON, TSV, human-readable)
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from rich.console import Console
from rich.table import Table


class OutputFormatter:
    """Format output in different modes"""

    def __init__(self, mode: str = "human"):
        """
        Initialize formatter

        Args:
            mode: Output mode (human, json, tsv)
        """
        self.mode = mode.lower()
        self.console = Console()
        self.silent = False  # Silent mode flag for JSON output

    def set_silent(self, silent: bool) -> None:
        """
        Set silent mode (suppress all output)

        Args:
            silent: True to suppress output, False to allow it
        """
        self.silent = silent

    @contextmanager
    def capture_silent(self, enabled: bool = True) -> Iterator[None]:
        """
        Temporarily toggle silent mode and restore the previous state afterwards.
        """
        previous = self.silent
        try:
            self.silent = enabled
            yield
        finally:
            self.silent = previous

    def output_recordings(self, recordings: list[dict[str, Any]]) -> None:
        """
        Output list of recordings

        Args:
            recordings: List of recording metadata
        """
        if self.mode == "json":
            self._output_json(recordings)
        elif self.mode == "tsv":
            self._output_tsv(recordings)
        else:
            self._output_human_recordings(recordings)

    def output_download_summary(
        self, downloaded_files: list[dict[str, Any]], meeting_topic: str
    ) -> None:
        """
        Output download summary

        Args:
            downloaded_files: List of downloaded file info
            meeting_topic: Meeting topic
        """
        if self.mode == "json":
            summary = {
                "meeting_topic": meeting_topic,
                "files": downloaded_files,
                "total_files": len(downloaded_files),
            }
            self._output_json(summary)
        elif self.mode == "tsv":
            self._output_tsv(downloaded_files)
        else:
            self._output_human_download_summary(downloaded_files, meeting_topic)

    def output_error(self, message: str) -> None:
        """Output error message"""
        if self.silent:
            return  # Suppress in silent mode
        if self.mode == "json":
            self._output_json({"error": message})
        else:
            self.console.print(f"[bold red]Error:[/bold red] {message}")

    def output_success(self, message: str) -> None:
        """Output success message"""
        if self.silent:
            return  # Suppress in silent mode
        if self.mode == "json":
            self._output_json({"status": "success", "message": message})
        else:
            self.console.print(f"[bold green]✓[/bold green] {message}")

    def output_info(self, message: str) -> None:
        """Output info message"""
        if self.silent:
            return  # Suppress in silent mode
        if self.mode == "json":
            self._output_json({"status": "info", "message": message})
        else:
            self.console.print(message)

    def _output_json(self, data: Any) -> None:
        """Output as JSON"""
        print(json.dumps(data, indent=2))

    def _output_tsv(self, data: list[dict[str, Any]]) -> None:
        """Output as TSV"""
        if not data:
            return

        # Get all unique keys
        keys: set[str] = set()
        for item in data:
            keys.update(item.keys())

        # Print header
        print("\t".join(sorted(keys)))

        # Print rows
        for item in data:
            values = [str(item.get(key, "")) for key in sorted(keys)]
            print("\t".join(values))

    def _output_human_recordings(self, recordings: list[dict[str, Any]]) -> None:
        """Output recordings in human-readable format"""
        if not recordings:
            self.console.print("[yellow]No recordings found[/yellow]")
            return

        table = Table(title="Zoom Recordings")
        table.add_column("Meeting ID", style="cyan")
        table.add_column("Topic", style="green")
        table.add_column("Start Time", style="blue")
        table.add_column("Duration (min)", style="magenta")
        table.add_column("Files", style="yellow")

        for recording in recordings:
            meeting_id = str(recording.get("id", ""))
            topic = recording.get("topic", "N/A")
            start_time = recording.get("start_time", "N/A")
            duration = recording.get("duration", 0)
            file_count = len(recording.get("recording_files", []))

            table.add_row(meeting_id, topic, start_time, str(duration), str(file_count))

        self.console.print(table)

    def _output_human_download_summary(
        self, downloaded_files: list[dict[str, Any]], meeting_topic: str
    ) -> None:
        """Output download summary in human-readable format"""
        self.console.print(f"\n[bold]Meeting:[/bold] {meeting_topic}")
        self.console.print(f"[bold]Downloaded files:[/bold] {len(downloaded_files)}")

        if downloaded_files:
            table = Table()
            table.add_column("File", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Size", style="yellow")

            for file_info in downloaded_files:
                filename = file_info.get("filename", "")
                file_type = file_info.get("file_type", "")
                size_mb = file_info.get("size_mb", 0)

                table.add_row(filename, file_type, f"{size_mb:.2f} MB")

            self.console.print(table)
