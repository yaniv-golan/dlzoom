import json

import click
import pytest
from click.testing import CliRunner

from dlzoom.cli import cli as dlzoom_cli
from dlzoom.cli import validate_meeting_id
from dlzoom.exceptions import ConfigError
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

    def test_validate_meeting_id_tuple_input(self):
        ctx, param = self._ctx_param()

        # Tuple input (from nargs=-1)
        assert validate_meeting_id(ctx, param, ("852", "9282", "6718")) == "85292826718"
        assert validate_meeting_id(ctx, param, ("882", "9060", "9309")) == "88290609309"

        # Empty tuple
        assert validate_meeting_id(ctx, param, ()) is None

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
        assert parser.sanitize_filename("/abc123") == "abc123"
        assert parser.sanitize_filename("abc/def") == "abc_def"
        assert parser.sanitize_filename("//abc//def//") == "abc_def"


class TestCliConfigErrors:
    def test_download_json_config_error_uses_invalid_config_code(self, monkeypatch):
        runner = CliRunner()

        def fake_config(*args, **kwargs):
            raise ConfigError("Missing Zoom credentials", details="set env vars")

        monkeypatch.setattr("dlzoom.cli.Config", fake_config)

        result = runner.invoke(dlzoom_cli, ["download", "123456789", "--json"])
        assert result.exit_code != 0

        payload = json.loads(result.output)
        assert payload["error"]["code"] == "INVALID_CONFIG"
        assert "Missing Zoom credentials" in payload["error"]["message"]


class TestCliUserConfigDiscovery:
    def test_download_uses_user_config_file(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "dlzoom"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "zoom_account_id": "file_account",
                    "zoom_client_id": "file_client",
                    "zoom_client_secret": "file_secret",
                }
            )
        )

        # Point platformdirs to our temp config dir and clear env vars
        monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(config_dir))
        for key in ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"):
            monkeypatch.delenv(key, raising=False)

        captured: dict[str, object] = {}

        class DummyZoomClient:
            def __init__(self, account_id: str, client_id: str, client_secret: str):
                captured["creds"] = (account_id, client_id, client_secret)
                self.base_url = ""
                self.token_url = ""

        def fake_handle_download_mode(**kwargs):
            captured["handled"] = True
            captured["scope"] = kwargs.get("scope")
            captured["client"] = kwargs.get("client")

        monkeypatch.setattr("dlzoom.cli.ZoomClient", DummyZoomClient)
        monkeypatch.setattr("dlzoom.cli._h._handle_download_mode", fake_handle_download_mode)
        monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: None)
        monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")

        runner = CliRunner()
        result = runner.invoke(
            dlzoom_cli,
            [
                "download",
                "123456789",
                "--skip-transcript",
                "--skip-chat",
                "--skip-timeline",
            ],
        )

        assert result.exit_code == 0, result.output
        assert captured.get("handled") is True
        assert captured.get("creds") == ("file_account", "file_client", "file_secret")
