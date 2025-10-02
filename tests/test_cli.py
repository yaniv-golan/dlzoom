"""
Tests for CLI input validation and security
"""

import click
import pytest

from dlzoom.cli import validate_meeting_id


class TestMeetingIdValidation:
    """Test meeting ID validation to prevent injection attacks"""

    def test_valid_numeric_meeting_id_9_digits(self):
        """Valid 9-digit numeric meeting ID"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        result = validate_meeting_id(ctx, param, "123456789")
        assert result == "123456789"

    def test_valid_numeric_meeting_id_10_digits(self):
        """Valid 10-digit numeric meeting ID"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        result = validate_meeting_id(ctx, param, "1234567890")
        assert result == "1234567890"

    def test_valid_numeric_meeting_id_11_digits(self):
        """Valid 11-digit numeric meeting ID"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        result = validate_meeting_id(ctx, param, "12345678901")
        assert result == "12345678901"

    def test_valid_numeric_meeting_id_12_digits(self):
        """Valid 12-digit numeric meeting ID - real example"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        result = validate_meeting_id(ctx, param, "123456789")
        assert result == "123456789"

    def test_valid_uuid_format_alphanumeric(self):
        """Valid UUID with alphanumeric characters"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        result = validate_meeting_id(ctx, param, "abc123XYZ")
        assert result == "abc123XYZ"

    def test_valid_uuid_format_with_base64_chars(self):
        """Valid UUID with base64 special characters (URL-safe base64)"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        # Note: Zoom uses URL-safe base64 which uses - and _ instead of + and /
        result = validate_meeting_id(ctx, param, "abc123_-XYZ")
        assert result == "abc123_-XYZ"

    def test_invalid_numeric_too_short(self):
        """Numeric meeting ID with less than 9 digits should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        with pytest.raises(click.BadParameter, match="must be 9-12 digits, got 8 digits"):
            validate_meeting_id(ctx, param, "12345678")

    def test_invalid_numeric_too_long(self):
        """Numeric meeting ID with more than 12 digits should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        with pytest.raises(click.BadParameter, match="must be 9-12 digits, got 13 digits"):
            validate_meeting_id(ctx, param, "1234567890123")

    def test_invalid_empty_meeting_id(self):
        """Empty meeting ID should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        with pytest.raises(click.BadParameter, match="Meeting ID cannot be empty"):
            validate_meeting_id(ctx, param, "")

    def test_invalid_path_traversal_double_dots(self):
        """Meeting ID with .. (path traversal) should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        with pytest.raises(click.BadParameter, match="path traversal attempt detected"):
            validate_meeting_id(ctx, param, "../etc/passwd")

    def test_invalid_path_traversal_forward_slash(self):
        """Meeting ID with / should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        with pytest.raises(click.BadParameter, match="path traversal attempt detected"):
            validate_meeting_id(ctx, param, "/etc/passwd")

    def test_invalid_path_traversal_backslash(self):
        """Meeting ID with \\ should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        with pytest.raises(click.BadParameter, match="path traversal attempt detected"):
            validate_meeting_id(ctx, param, "..\\windows\\system32")

    def test_invalid_uuid_too_long(self):
        """UUID exceeding 100 characters should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        long_uuid = "a" * 101
        with pytest.raises(click.BadParameter, match="exceeds maximum length"):
            validate_meeting_id(ctx, param, long_uuid)

    def test_invalid_characters_special_chars(self):
        """Meeting ID with invalid special characters should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        with pytest.raises(click.BadParameter, match="Invalid meeting ID format"):
            validate_meeting_id(ctx, param, "meeting@123")

    def test_invalid_characters_spaces(self):
        """Meeting ID with spaces should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        with pytest.raises(click.BadParameter, match="Invalid meeting ID format"):
            validate_meeting_id(ctx, param, "123 456 789")

    def test_invalid_characters_semicolon(self):
        """Meeting ID with semicolon (command injection attempt) should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        # Contains "/" so will be caught by path traversal check
        with pytest.raises(click.BadParameter, match="path traversal attempt detected"):
            validate_meeting_id(ctx, param, "123456789; rm -rf /")

    def test_invalid_characters_pipe(self):
        """Meeting ID with pipe (command injection attempt) should fail"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        # Contains "/" so will be caught by path traversal check
        with pytest.raises(click.BadParameter, match="path traversal attempt detected"):
            validate_meeting_id(ctx, param, "123456789 | cat /etc/passwd")

    def test_valid_uuid_boundary_100_chars(self):
        """UUID with exactly 100 characters should pass"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        uuid_100 = "a" * 100
        result = validate_meeting_id(ctx, param, uuid_100)
        assert result == uuid_100

    def test_valid_numeric_all_valid_lengths(self):
        """Test all valid numeric meeting ID lengths (9-12)"""
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])

        for length in range(9, 13):
            meeting_id = "1" * length
            result = validate_meeting_id(ctx, param, meeting_id)
            assert result == meeting_id
