from click.testing import CliRunner

from dlzoom.cli import cli as dlzoom_cli

from .cli_test_utils import setup_user_cli


def test_cli_download_passes_skip_speakers_none_by_default(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)

    observed = {}

    def fake_handle_download_mode(**kwargs):
        observed["skip_speakers"] = kwargs["skip_speakers"]

    monkeypatch.setattr("dlzoom.cli._h._handle_download_mode", fake_handle_download_mode)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["download", "123456789"])
    assert result.exit_code == 0, result.output
    assert observed["skip_speakers"] is None


def test_cli_download_honors_skip_speakers_flag(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)

    observed = {}

    def fake_handle_download_mode(**kwargs):
        observed["skip_speakers"] = kwargs["skip_speakers"]

    monkeypatch.setattr("dlzoom.cli._h._handle_download_mode", fake_handle_download_mode)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["download", "123456789", "--skip-speakers"])
    assert result.exit_code == 0, result.output
    assert observed["skip_speakers"] is True
