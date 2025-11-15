from pathlib import Path

from click.testing import CliRunner

from dlzoom.cli import cli as dlzoom_cli

from .cli_test_utils import DummyConfig, DummyUserClient


def setup_user_cli(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(lambda cls, _tmp=tmp_path: _tmp),
    )
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)

    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", DummyUserClient)

    created = {}

    def fake_config(*args, **kwargs):
        cfg = DummyConfig(tmp_path)
        created["cfg"] = cfg
        return cfg

    monkeypatch.setattr("dlzoom.cli.Config", fake_config)
    return created


def test_output_dir_and_log_file_expand(monkeypatch, tmp_path):
    created_cfg = setup_user_cli(monkeypatch, tmp_path)

    observed = {}

    def fake_download_mode(**kwargs):
        observed["log_file"] = kwargs["log_file"]

    monkeypatch.setattr("dlzoom.cli._h._handle_download_mode", fake_download_mode)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli,
        [
            "download",
            "123456789",
            "--output-dir",
            "~/custom",
            "--log-file",
            "~/logs/run.jsonl",
        ],
    )

    assert result.exit_code == 0, result.output
    assert created_cfg["cfg"].output_dir == Path(tmp_path / "custom")
    assert observed["log_file"] == Path(tmp_path / "logs" / "run.jsonl")


def test_existing_output_dir_and_log_file_allowed(monkeypatch, tmp_path):
    created_cfg = setup_user_cli(monkeypatch, tmp_path)

    observed = {}

    def fake_download_mode(**kwargs):
        observed["log_file"] = kwargs["log_file"]

    monkeypatch.setattr("dlzoom.cli._h._handle_download_mode", fake_download_mode)

    existing_dir = tmp_path / "existing"
    existing_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "existing.jsonl"
    log_file.write_text("[]")

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli,
        [
            "download",
            "123456789",
            "--output-dir",
            str(existing_dir),
            "--log-file",
            str(log_file),
        ],
    )

    assert result.exit_code == 0, result.output
    assert created_cfg["cfg"].output_dir == existing_dir
    assert observed["log_file"] == log_file
