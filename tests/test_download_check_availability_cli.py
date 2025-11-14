from pathlib import Path

from click.testing import CliRunner
import pytest

from dlzoom.cli import cli as dlzoom_cli
from dlzoom.exceptions import RecordingNotFoundError


class DummyConfig:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.zoom_account_id = None
        self.zoom_client_id = None
        self.zoom_client_secret = None
        self.tokens_path = output_dir / "tokens.json"
        self.zoom_api_base_url = "https://api.zoom.us/v2"
        self.zoom_oauth_token_url = None
        self.s2s_default_user = None
        self.auth_url = ""


class DummyUserClient:
    def __init__(self, tokens, tokens_path):
        self.base_url = None


def _setup_user_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)

    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", DummyUserClient)

    def fake_config(*args, **kwargs):
        return DummyConfig(tmp_path)

    monkeypatch.setattr("dlzoom.cli.Config", fake_config)


def test_cli_check_availability_success(monkeypatch, tmp_path):
    _setup_user_cli(monkeypatch, tmp_path)

    calls = {}

    def fake_handle(*args, **kwargs):
        calls["meeting_id"] = args[2]

    monkeypatch.setattr("dlzoom.cli._h._handle_check_availability", fake_handle)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["download", "123456789", "--check-availability"])
    assert result.exit_code == 0, result.output
    assert calls["meeting_id"] == "123456789"


def test_cli_check_availability_failure(monkeypatch, tmp_path):
    _setup_user_cli(monkeypatch, tmp_path)

    def fake_handle(*args, **kwargs):
        raise RecordingNotFoundError("missing", details="123456789")

    monkeypatch.setattr("dlzoom.cli._h._handle_check_availability", fake_handle)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["download", "123456789", "--check-availability"])
    assert result.exit_code != 0
    assert "RECORDING_NOT_FOUND" in result.output
