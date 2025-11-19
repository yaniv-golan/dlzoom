import json
from pathlib import Path

from dlzoom.downloader import Downloader


def _make_timeline_file(tmp_path: Path) -> Path:
    p = tmp_path / "timeline.json"
    data = {
        "timeline": [
            {"ts": "00:00:10.000", "users": [{"username": "Alice", "zoom_userid": "Z_A"}]},
            {"ts": "00:00:12.000", "users": [{"username": "Bob", "zoom_userid": "Z_B"}]},
        ]
    }
    p.write_text(json.dumps(data))
    return p


def test_downloader_generates_stj_by_default(monkeypatch, tmp_path):
    # Prepare
    d = Downloader(output_dir=tmp_path, access_token="token", output_name="meeting")
    timeline_path = _make_timeline_file(tmp_path)

    # Monkeypatch download_file to return our local timeline path
    monkeypatch.setattr(Downloader, "download_file", lambda *a, **k: timeline_path)

    # Spy on writer to ensure it is invoked and writes to expected path
    calls = {}

    def fake_writer(timeline_path, output_path, **opts):
        calls["timeline_path"] = Path(timeline_path)
        calls["output_path"] = Path(output_path)
        output_path.write_text("{}\n")
        return output_path

    monkeypatch.setenv("DLZOOM_SPEAKERS", "1")
    monkeypatch.setitem(
        __import__("sys").modules,
        "dlzoom.stj_minimizer",
        __import__("types").SimpleNamespace(write_minimal_stj_from_file=fake_writer),
    )

    files = d.download_transcripts_and_chat(
        recording_files=[
            {
                "file_extension": "JSON",
                "file_type": "TIMELINE",
                "download_url": "https://zoom.us/rec/download/foo",
            }
        ],
        meeting_topic="Topic",
        instance_start=None,
        show_progress=False,
        skip_transcript=True,
        skip_chat=True,
        skip_timeline=False,
    )

    assert files["timeline"][0] == timeline_path
    assert files["speakers"][0].name == "meeting_speakers.stjson"
    # Ensure STJ was written with expected base name
    assert calls["output_path"].name == "meeting_speakers.stjson"
    assert calls["output_path"].exists()


def test_downloader_stj_without_output_name_uses_unique_suffix(monkeypatch, tmp_path):
    d = Downloader(output_dir=tmp_path, access_token="token")
    timeline_path = _make_timeline_file(tmp_path)
    monkeypatch.setattr(Downloader, "download_file", lambda *a, **k: timeline_path)

    def fake_writer(timeline_path, output_path, **opts):
        Path(output_path).write_text("{}\n")
        return output_path

    monkeypatch.setenv("DLZOOM_SPEAKERS", "1")
    monkeypatch.setitem(
        __import__("sys").modules,
        "dlzoom.stj_minimizer",
        __import__("types").SimpleNamespace(write_minimal_stj_from_file=fake_writer),
    )

    files = d.download_transcripts_and_chat(
        recording_files=[
            {
                "file_extension": "JSON",
                "file_type": "TIMELINE",
                "download_url": "https://zoom.us/rec/download/foo",
                "id": "abc123",
            }
        ],
        meeting_topic="Topic",
        instance_start=None,
        show_progress=False,
        skip_transcript=True,
        skip_chat=True,
        skip_timeline=False,
    )

    assert files["speakers"][0].name == "timeline_speakers_abc123.stjson"


def test_downloader_stj_template_name_dedupes(monkeypatch, tmp_path):
    existing = tmp_path / "meeting_speakers.stjson"
    existing.write_text("{}")

    d = Downloader(output_dir=tmp_path, access_token="token", output_name="meeting")
    timeline_path = _make_timeline_file(tmp_path)
    monkeypatch.setattr(Downloader, "download_file", lambda *a, **k: timeline_path)

    def fake_writer(timeline_path, output_path, **opts):
        Path(output_path).write_text("{}\n")
        return output_path

    monkeypatch.setenv("DLZOOM_SPEAKERS", "1")
    monkeypatch.setitem(
        __import__("sys").modules,
        "dlzoom.stj_minimizer",
        __import__("types").SimpleNamespace(write_minimal_stj_from_file=fake_writer),
    )

    files = d.download_transcripts_and_chat(
        recording_files=[
            {
                "file_extension": "JSON",
                "file_type": "TIMELINE",
                "download_url": "https://zoom.us/rec/download/foo",
            }
        ],
        meeting_topic="Topic",
        instance_start=None,
        show_progress=False,
        skip_transcript=True,
        skip_chat=True,
        skip_timeline=False,
    )

    assert files["speakers"][0].name == "meeting_speakers_2.stjson"


def test_downloader_skip_speakers(monkeypatch, tmp_path):
    d = Downloader(output_dir=tmp_path, access_token="token", output_name="meeting")
    timeline_path = _make_timeline_file(tmp_path)
    monkeypatch.setattr(Downloader, "download_file", lambda *a, **k: timeline_path)

    wrote = {"called": False}

    def fake_writer(*a, **k):
        wrote["called"] = True

    monkeypatch.setitem(
        __import__("sys").modules,
        "dlzoom.stj_minimizer",
        __import__("types").SimpleNamespace(write_minimal_stj_from_file=fake_writer),
    )

    files = d.download_transcripts_and_chat(
        recording_files=[
            {
                "file_extension": "JSON",
                "file_type": "TIMELINE",
                "download_url": "https://zoom.us/rec/download/foo",
            }
        ],
        meeting_topic="Topic",
        instance_start=None,
        show_progress=False,
        skip_transcript=True,
        skip_chat=True,
        skip_timeline=False,
        skip_speakers=True,
    )

    assert wrote["called"] is False
    assert files["speakers"] == []


def test_downloader_env_skip_speakers_case_insensitive(monkeypatch, tmp_path):
    d = Downloader(output_dir=tmp_path, access_token="token", output_name="meeting")
    timeline_path = _make_timeline_file(tmp_path)
    monkeypatch.setattr(Downloader, "download_file", lambda *a, **k: timeline_path)

    wrote = {"called": False}

    def fake_writer(*a, **k):
        wrote["called"] = True

    monkeypatch.setitem(
        __import__("sys").modules,
        "dlzoom.stj_minimizer",
        __import__("types").SimpleNamespace(write_minimal_stj_from_file=fake_writer),
    )
    monkeypatch.setenv("DLZOOM_SPEAKERS", "FALSE ")

    files = d.download_transcripts_and_chat(
        recording_files=[
            {
                "file_extension": "JSON",
                "file_type": "TIMELINE",
                "download_url": "https://zoom.us/rec/download/foo",
            }
        ],
        meeting_topic="Topic",
        instance_start=None,
        show_progress=False,
        skip_transcript=True,
        skip_chat=True,
        skip_timeline=False,
    )

    assert wrote["called"] is False
    assert files["speakers"] == []
