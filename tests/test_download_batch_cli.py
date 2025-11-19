from click.testing import CliRunner

from dlzoom.cli import cli as dlzoom_cli
from dlzoom.exceptions import DownloadFailedError

from .cli_test_utils import setup_user_cli, strip_ansi


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


def test_cli_batch_download_passes_page_size(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)

    captured = {}

    def fake_batch_download(**kwargs):
        captured["page_size"] = kwargs.get("page_size")

    monkeypatch.setattr("dlzoom.cli._h._handle_batch_download", fake_batch_download)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli,
        [
            "download",
            "--from-date",
            "2024-01-01",
            "--to-date",
            "2024-01-02",
            "--scope",
            "user",
            "--user-id",
            "host@example.com",
            "--page-size",
            "42",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["page_size"] == 42


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


def test_cli_batch_check_availability_passes_page_size(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)

    captured = {}

    def fake_batch_check(**kwargs):
        captured["page_size"] = kwargs.get("page_size")

    monkeypatch.setattr("dlzoom.cli._h._handle_batch_check_availability", fake_batch_check)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli,
        [
            "download",
            "--from-date",
            "2024-01-01",
            "--to-date",
            "2024-01-02",
            "--scope",
            "user",
            "--user-id",
            "host@example.com",
            "--check-availability",
            "--page-size",
            "12",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["page_size"] == 12


def test_cli_download_requires_meeting_id_without_dates(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["download"])
    assert result.exit_code != 0
    assert "MEETING_ID argument is required" in strip_ansi(result.output)


def test_cli_download_requires_both_dates(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli,
        [
            "download",
            "--from-date",
            "2024-01-01",
        ],
    )
    assert result.exit_code != 0
    assert "Both --from-date and --to-date must be provided together" in strip_ansi(result.output)


def test_cli_download_rejects_meeting_id_with_dates(monkeypatch, tmp_path):
    setup_user_cli(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli,
        [
            "download",
            "123456789",
            "--from-date",
            "2024-01-01",
            "--to-date",
            "2024-01-02",
        ],
    )
    assert result.exit_code != 0
    assert "cannot be used together with --from-date/--to-date" in strip_ansi(result.output)
