from click.testing import CliRunner

from dlzoom.cli import cli as dlzoom_cli
from dlzoom.exceptions import DownloadFailedError

from .cli_test_utils import setup_user_cli


def test_cli_batch_download_success(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)

    called = {}

    def fake_batch_download(**kwargs):
        called["scope"] = kwargs.get("scope")

    monkeypatch.setattr("dlzoom.cli._h._handle_batch_download", fake_batch_download)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli,
        [
            "download",
            "placeholder",
            "--from-date",
            "2024-01-01",
            "--to-date",
            "2024-01-02",
            "--scope",
            "user",
            "--user-id",
            "host@example.com",
        ],
    )
    assert result.exit_code == 0, result.output
    assert called["scope"] == "user"


def test_cli_batch_download_failure(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)

    def fake_batch_download(**kwargs):
        raise DownloadFailedError("boom", details="1 of 2 failed")

    monkeypatch.setattr("dlzoom.cli._h._handle_batch_download", fake_batch_download)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli,
        [
            "download",
            "placeholder",
            "--from-date",
            "2024-01-01",
            "--to-date",
            "2024-01-02",
            "--scope",
            "user",
            "--user-id",
            "host@example.com",
        ],
    )
    assert result.exit_code != 0
    assert "DOWNLOAD_FAILED" in result.output
