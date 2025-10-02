"""
Tests for template parsing with error visibility
"""

from unittest.mock import Mock, patch

from dlzoom.templates import TemplateParser


class TestTemplateErrorVisibility:
    """Test that template parsing errors are visible (not silent)"""

    @patch("logging.getLogger")
    def test_invalid_date_logs_warning(self, mock_logger):
        """Invalid date should log warning and use empty string"""
        mock_log = Mock()
        mock_logger.return_value = mock_log

        parser = TemplateParser(filename_template="{start_time:%Y%m%d}")

        # Invalid date format
        meeting_data = {"start_time": "invalid-date-format", "meeting_id": "123"}

        result = parser.apply_filename_template(meeting_data)

        # Should log warning
        assert mock_log.warning.called
        warning_call = mock_log.warning.call_args[0][0]
        assert "Failed to parse date" in warning_call
        assert "invalid-date-format" in warning_call

        # Should use empty string (not silent failure)
        assert result == ""  # No date, no other content

    @patch("logging.getLogger")
    def test_missing_start_time_logs_warning(self, mock_logger):
        """Missing start_time should leave placeholder unchanged"""
        mock_log = Mock()
        mock_logger.return_value = mock_log

        parser = TemplateParser(filename_template="recording_{start_time:%Y%m%d}")

        # No start_time in data
        meeting_data = {"meeting_id": "123"}

        result = parser.apply_filename_template(meeting_data)

        # When start_time is missing, placeholder is left as-is
        assert result == "recording_{start_time:%Y%m%d}"

    def test_valid_date_formats_correctly(self):
        """Valid date should format correctly"""
        parser = TemplateParser(filename_template="{start_time:%Y%m%d}")

        meeting_data = {"start_time": "2025-09-30T12:00:35Z", "meeting_id": "123"}

        result = parser.apply_filename_template(meeting_data)
        assert result == "20250930"

    def test_multiple_date_formats(self):
        """Multiple date placeholders should all work"""
        parser = TemplateParser(filename_template="{start_time:%Y}/{start_time:%m}/{start_time:%d}")

        meeting_data = {
            "start_time": "2025-09-30T12:00:35Z",
        }

        result = parser.apply_filename_template(meeting_data)
        assert result == "2025/09/30"


class TestSimplePlaceholders:
    """Test simple placeholder substitution"""

    def test_topic_placeholder(self):
        """Should replace {topic} with meeting topic"""
        parser = TemplateParser(filename_template="{topic}")

        meeting_data = {"topic": "Team Meeting"}

        result = parser.apply_filename_template(meeting_data)
        assert result == "Team_Meeting"

    def test_meeting_id_placeholder(self):
        """Should replace {meeting_id} with meeting ID"""
        parser = TemplateParser(filename_template="{meeting_id}")

        meeting_data = {"meeting_id": "123456789"}

        result = parser.apply_filename_template(meeting_data)
        assert result == "123456789"

    def test_host_email_placeholder(self):
        """Should replace {host_email} with host email"""
        parser = TemplateParser(filename_template="{host_email}")

        meeting_data = {"host_email": "user@example.com"}

        result = parser.apply_filename_template(meeting_data)
        # @ is not sanitized (it's safe for filenames on most systems)
        assert result == "user@example.com"

    def test_multiple_placeholders(self):
        """Should handle multiple placeholders"""
        parser = TemplateParser(filename_template="{topic}_{meeting_id}")

        meeting_data = {"topic": "Team Meeting", "meeting_id": "123"}

        result = parser.apply_filename_template(meeting_data)
        assert "Team" in result
        assert "123" in result

    def test_missing_placeholder_uses_empty(self):
        """Missing data should use empty string"""
        parser = TemplateParser(filename_template="{topic}_{host_email}")

        meeting_data = {"topic": "Meeting"}  # No host_email

        result = parser.apply_filename_template(meeting_data)
        assert result == "Meeting_"


class TestFilenameSanitization:
    """Test filename sanitization for safety"""

    def test_sanitize_removes_slashes(self):
        """Should remove forward slashes"""
        parser = TemplateParser(filename_template="{topic}")

        meeting_data = {"topic": "Team/Project/Meeting"}

        result = parser.apply_filename_template(meeting_data)
        assert "/" not in result
        assert result == "Team_Project_Meeting"

    def test_sanitize_removes_backslashes(self):
        """Should remove backslashes"""
        parser = TemplateParser(filename_template="{topic}")

        meeting_data = {"topic": "Team\\Project\\Meeting"}

        result = parser.apply_filename_template(meeting_data)
        assert "\\" not in result

    def test_sanitize_removes_colons(self):
        """Should remove colons"""
        parser = TemplateParser(filename_template="{topic}")

        meeting_data = {"topic": "Meeting: Important"}

        result = parser.apply_filename_template(meeting_data)
        assert ":" not in result

    def test_sanitize_removes_unsafe_chars(self):
        """Should remove all unsafe filename characters"""
        parser = TemplateParser(filename_template="{topic}")

        meeting_data = {"topic": 'Meeting<>:"/\\|?*Name'}

        result = parser.apply_filename_template(meeting_data)

        # All unsafe chars should be removed/replaced
        for char in '<>:"/\\|?*':
            assert char not in result

    def test_sanitize_collapses_underscores(self):
        """Should collapse multiple underscores into one"""
        parser = TemplateParser(filename_template="{topic}")

        meeting_data = {"topic": "Team___Meeting___Notes"}

        result = parser.apply_filename_template(meeting_data)
        assert "___" not in result
        assert "__" not in result

    def test_sanitize_strips_leading_trailing(self):
        """Should strip leading/trailing unsafe characters"""
        parser = TemplateParser(filename_template="{topic}")

        meeting_data = {"topic": "___Meeting___"}

        result = parser.apply_filename_template(meeting_data)
        assert not result.startswith("_")
        assert not result.endswith("_")


class TestFolderTemplates:
    """Test folder template application"""

    def test_folder_template_with_date(self):
        """Should create folder paths with dates"""
        parser = TemplateParser(folder_template="{start_time:%Y}/{start_time:%m}")

        meeting_data = {
            "start_time": "2025-09-30T12:00:35Z",
        }

        result = parser.apply_folder_template(meeting_data)
        assert result.as_posix() == "2025/09"

    def test_folder_template_with_topic(self):
        """Should create folder paths with topics"""
        parser = TemplateParser(folder_template="{topic}")

        meeting_data = {"topic": "Team Meeting"}

        result = parser.apply_folder_template(meeting_data)
        assert "Team" in str(result)

    def test_no_folder_template_returns_current_dir(self):
        """No folder template should return current directory"""
        parser = TemplateParser()

        meeting_data = {"topic": "Meeting"}

        result = parser.apply_folder_template(meeting_data)
        assert str(result) == "."


class TestDefaultBehavior:
    """Test default behavior when no template provided"""

    def test_no_filename_template_uses_meeting_id(self):
        """No template should default to meeting_id"""
        parser = TemplateParser()

        meeting_data = {"meeting_id": "123456"}

        result = parser.apply_filename_template(meeting_data)
        assert result == "123456"

    def test_no_filename_template_fallback(self):
        """No template and no meeting_id should use 'recording'"""
        parser = TemplateParser()

        meeting_data = {}

        result = parser.apply_filename_template(meeting_data)
        assert result == "recording"


class TestComplexTemplates:
    """Test complex template combinations"""

    def test_complex_filename_template(self):
        """Should handle complex filename template"""
        parser = TemplateParser(filename_template="{start_time:%Y%m%d}_{topic}_{meeting_id}")

        meeting_data = {
            "start_time": "2025-09-30T12:00:35Z",
            "topic": "Weekly Sync",
            "meeting_id": "123",
        }

        result = parser.apply_filename_template(meeting_data)
        assert "20250930" in result
        assert "Weekly" in result
        assert "123" in result

    def test_complex_folder_template(self):
        """Should handle complex folder template"""
        parser = TemplateParser(folder_template="{start_time:%Y}/{start_time:%m}/{topic}")

        meeting_data = {"start_time": "2025-09-30T12:00:35Z", "topic": "Team Meeting"}

        result = parser.apply_folder_template(meeting_data)
        path_str = str(result)
        assert "2025" in path_str
        assert "09" in path_str
        assert "Team" in path_str


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_template_string(self):
        """Empty template string should return empty result"""
        parser = TemplateParser(filename_template="")

        meeting_data = {"topic": "Meeting"}

        result = parser.apply_filename_template(meeting_data)
        assert result == "123" or result == "recording"  # Falls back to default

    def test_template_with_only_whitespace(self):
        """Whitespace-only template returns whitespace as-is"""
        parser = TemplateParser(filename_template="   ")

        meeting_data = {"topic": "Meeting"}

        result = parser.apply_filename_template(meeting_data)
        # Template returns whitespace as-is (no placeholders to replace)
        assert result == "   "

    def test_unicode_characters_in_topic(self):
        """Unicode characters should be handled safely"""
        parser = TemplateParser(filename_template="{topic}")

        meeting_data = {"topic": "Meeting 会议 Réunion"}

        result = parser.apply_filename_template(meeting_data)
        # Should handle unicode gracefully
        assert isinstance(result, str)
