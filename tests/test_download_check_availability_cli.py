from click.testing import CliRunner

from dlzoom.cli import cli as dlzoom_cli
from dlzoom.exceptions import RecordingNotFoundError

from .cli_test_utils import setup_user_cli


def test_cli_check_availability_success(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)

    calls = {}

    def fake_handle(*args, **kwargs):
        calls["meeting_id"] = args[2]

    monkeypatch.setattr("dlzoom.cli._h._handle_check_availability", fake_handle)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["download", "123456789", "--check-availability"])
    assert result.exit_code == 0, result.output
    assert calls["meeting_id"] == "123456789"


def test_cli_check_availability_failure(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)

    def fake_handle(*args, **kwargs):
        raise RecordingNotFoundError("missing", details="123456789")

    monkeypatch.setattr("dlzoom.cli._h._handle_check_availability", fake_handle)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["download", "123456789", "--check-availability"])
    assert result.exit_code != 0
    assert "RECORDING_NOT_FOUND" in result.output
