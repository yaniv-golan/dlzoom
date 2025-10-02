"""
Audio extraction from video files using ffmpeg
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from dlzoom.exceptions import AudioExtractionError


class AudioExtractor:
    """Extract audio from video files (MP4 -> M4A)"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._ffmpeg_path: Optional[str] = None

    def check_ffmpeg_available(self) -> bool:
        """Check if ffmpeg is available in system PATH"""
        if self._ffmpeg_path is None:
            self._ffmpeg_path = shutil.which("ffmpeg")
        return self._ffmpeg_path is not None

    def extract_audio(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
        verbose: bool = False,
        audio_quality: Optional[int] = None
    ) -> Path:
        """
        Extract audio from MP4 video to M4A format

        Args:
            input_path: Path to input MP4 file
            output_path: Optional output path (defaults to input_path with .m4a extension)
            verbose: Show ffmpeg progress output
            audio_quality: Optional audio quality for AAC encoding (0-9).
                          0 = highest quality (~256kbps), 9 = lowest (~45kbps).
                          If None (default), copies audio stream without re-encoding (fastest).

        Returns:
            Path to extracted audio file

        Raises:
            AudioExtractionError: If ffmpeg not available or extraction fails
        """
        if not self.check_ffmpeg_available():
            raise AudioExtractionError(
                "ffmpeg not found in PATH. Please install ffmpeg to extract audio from video files."
            )

        if not input_path.exists():
            raise AudioExtractionError(f"Input file not found: {input_path}")

        # Default output path
        if output_path is None:
            output_path = input_path.with_suffix(".m4a")

        # Create temp file for extraction (use .tmp prefix instead of suffix)
        temp_output = output_path.parent / f".tmp.{output_path.name}"

        try:
            # Build ffmpeg command
            # -i: input file
            # -vn: no video
            # -acodec: audio codec
            # -q:a: audio quality (for VBR encoding)
            # -y: overwrite output file
            cmd = [
                self._ffmpeg_path or "ffmpeg",
                "-i",
                str(input_path),
                "-vn",  # No video
            ]

            if audio_quality is not None:
                # Validate quality range
                if not 0 <= audio_quality <= 9:
                    raise AudioExtractionError(
                        f"audio_quality must be between 0-9, got {audio_quality}"
                    )
                # Re-encode with AAC and specified quality
                cmd.extend([
                    "-acodec", "aac",  # AAC codec
                    "-q:a", str(audio_quality),  # VBR quality
                ])
                self.logger.info(f"Re-encoding audio with AAC quality {audio_quality}")
            else:
                # Copy audio codec without re-encoding (faster)
                cmd.extend([
                    "-acodec", "copy",  # Copy audio codec (no re-encoding)
                ])

            cmd.extend([
                "-y",  # Overwrite output
                str(temp_output),
            ])

            # Run ffmpeg
            if verbose:
                self.logger.info(f"Extracting audio: {input_path.name} -> {output_path.name}")
                # Show ffmpeg output
                subprocess.run(cmd, check=True, capture_output=False)
            else:
                # Suppress ffmpeg output
                subprocess.run(cmd, check=True, capture_output=True, text=True)

            # Move temp file to final location (atomic operation)
            try:
                # os.replace() is atomic on POSIX systems
                os.replace(str(temp_output), str(output_path))
            except OSError:
                # Fallback for cross-filesystem moves
                shutil.move(str(temp_output), str(output_path))

            self.logger.info(f"Audio extracted successfully: {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            # Clean up temp file on error
            if temp_output.exists():
                temp_output.unlink()

            error_msg = f"ffmpeg extraction failed: {e}"
            if hasattr(e, "stderr") and e.stderr:
                error_msg += f"\nffmpeg error: {e.stderr}"

            self.logger.error(error_msg)
            raise AudioExtractionError(error_msg) from e

        except Exception as e:
            # Clean up temp file on any error
            if temp_output.exists():
                temp_output.unlink()

            raise AudioExtractionError(f"Audio extraction failed: {e}") from e

    def extract_audio_if_needed(self, file_path: Path, verbose: bool = False) -> Path:
        """
        Extract audio from MP4 if needed, return path to M4A file

        If file is already M4A, returns original path.
        If file is MP4, extracts audio and returns new path.

        Args:
            file_path: Path to audio/video file
            verbose: Show extraction progress

        Returns:
            Path to M4A audio file
        """
        if file_path.suffix.lower() == ".m4a":
            return file_path

        if file_path.suffix.lower() == ".mp4":
            return self.extract_audio(file_path, verbose=verbose)

        raise AudioExtractionError(
            f"Unsupported file format: {file_path.suffix}. Expected .m4a or .mp4",
            details="Only M4A and MP4 files are supported",
        )
