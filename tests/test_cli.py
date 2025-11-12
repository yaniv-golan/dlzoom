import click
import pytest

from dlzoom.cli import validate_meeting_id
from dlzoom.templates import TemplateParser


class TestValidateMeetingId:
    def _ctx_param(self):
        ctx = click.Context(click.Command("test"))
        param = click.Argument(["meeting_id"])
        return ctx, param

    def test_validate_meeting_id_with_spaces(self):
        ctx, param = self._ctx_param()

        # Single spaces
        assert validate_meeting_id(ctx, param, "882 9060 9309") == "88290609309"

        # Multiple spaces
        assert validate_meeting_id(ctx, param, "882  9060  9309") == "88290609309"

        # Leading/trailing spaces
        assert validate_meeting_id(ctx, param, " 88290609309 ") == "88290609309"

        # Mixed whitespace
        assert validate_meeting_id(ctx, param, "882\n9060\t9309") == "88290609309"

    def test_validate_meeting_id_uuid_with_spaces(self):
        ctx, param = self._ctx_param()

        # UUID with spaces (and forward slashes)
        assert validate_meeting_id(ctx, param, "/abc def 123") == "/abcdef123"
        assert validate_meeting_id(ctx, param, " /abc123== ") == "/abc123=="

    def test_validate_meeting_id_uuid_with_forward_slashes(self):
        ctx, param = self._ctx_param()

        # UUID starting with /
        assert validate_meeting_id(ctx, param, "/abc123def456==") == "/abc123def456=="

        # UUID with // (double slash)
        assert validate_meeting_id(ctx, param, "//abc123def") == "//abc123def"

        # UUID with / in the middle
        assert validate_meeting_id(ctx, param, "abc/123/def") == "abc/123/def"

    def test_validate_meeting_id_only_spaces(self):
        ctx, param = self._ctx_param()

        with pytest.raises(click.BadParameter, match="cannot be empty"):
            validate_meeting_id(ctx, param, "   ")

    def test_validate_meeting_id_security_path_traversal(self):
        ctx, param = self._ctx_param()

        # Path traversal with ..
        with pytest.raises(click.BadParameter, match="path traversal"):
            validate_meeting_id(ctx, param, "../etc/passwd")

        # Path traversal with spaces (obfuscation attempt)
        with pytest.raises(click.BadParameter, match="path traversal"):
            validate_meeting_id(ctx, param, ".. /etc/passwd")

        # Backslashes (Windows paths)
        with pytest.raises(click.BadParameter, match="path traversal"):
            validate_meeting_id(ctx, param, "..\\windows\\system32")

        # UUID with .. should fail
        with pytest.raises(click.BadParameter, match="path traversal"):
            validate_meeting_id(ctx, param, "/abc../def")

    def test_validate_meeting_id_forward_slash_without_dots_is_safe(self):
        ctx, param = self._ctx_param()

        # These should all pass - they're legitimate UUIDs with alphanumeric content
        assert validate_meeting_id(ctx, param, "/abc/def") == "/abc/def"
        assert validate_meeting_id(ctx, param, "//abc123") == "//abc123"
        assert validate_meeting_id(ctx, param, "abc/123/def") == "abc/123/def"

    def test_validate_meeting_id_reject_degenerate_uuids(self):
        ctx, param = self._ctx_param()

        # These should fail - no alphanumeric content or too short
        with pytest.raises(click.BadParameter):
            validate_meeting_id(ctx, param, "/")  # Just a slash

        with pytest.raises(click.BadParameter):
            validate_meeting_id(ctx, param, "==")  # Just padding

        with pytest.raises(click.BadParameter):
            validate_meeting_id(ctx, param, "//")  # Just slashes

        with pytest.raises(click.BadParameter):
            validate_meeting_id(ctx, param, "+")  # Single character


class TestOutputNameSanitization:
    def test_output_name_sanitization(self):
        parser = TemplateParser()

        # UUIDs with slashes should be sanitized
        assert parser._sanitize_filename("/abc123") == "abc123"
        assert parser._sanitize_filename("abc/def") == "abc_def"
        assert parser._sanitize_filename("//abc//def//") == "abc_def"
