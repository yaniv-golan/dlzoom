from dlzoom.stj_minimizer import timeline_to_minimal_stj


def _synthetic_timeline():
    # Minimal synthetic structure inspired by Zoom timeline
    # Three speakers in sequence; include a multi-user timestamp and an empty users entry
    return {
        "timeline": [
            {"ts": "00:00:05.000", "users": []},
            {"ts": "00:00:10.000", "users": [{"username": "Alice", "zoom_userid": "Z_A"}]},
            {
                "ts": "00:00:12.000",
                "users": [
                    {"username": "Bob", "zoom_userid": "Z_B"},
                    {"username": "Carol", "zoom_userid": "Z_C"},
                ],
            },
            {"ts": "00:00:13.100", "users": [{"username": "Carol", "zoom_userid": "Z_C"}]},
            {"ts": "00:00:15.000", "users": []},
        ]
    }


def test_minimal_stj_basic_first_mode():
    data = _synthetic_timeline()
    stj = timeline_to_minimal_stj(data, duration_sec=16.0, mode="first")
    assert "stj" in stj and stj["stj"]["version"] == "0.6.0"
    segments = stj["stj"]["transcript"]["segments"]
    # Ensure segments have required keys and are rounded
    for seg in segments:
        assert set(["start", "end", "speaker_id", "text"]) <= set(seg.keys())
        assert isinstance(seg["start"], float) and isinstance(seg["end"], float)
        assert isinstance(seg["text"], str)

    # First non-empty users at 10s should create segment 10.0 -> 12.0 for Alice
    assert any(
        abs(s["start"] - 10.0) < 1e-6 and abs(s["end"] - 12.0) < 1e-6 and s["speaker_id"] == "Z_A"
        for s in segments
    )


def test_multiple_mode_uses_multiple_id():
    data = _synthetic_timeline()
    stj = timeline_to_minimal_stj(data, duration_sec=16.0, mode="multiple")
    segs = stj["stj"]["transcript"]["segments"]
    # Segment at 12.0 should be labeled multiple
    assert any(abs(s["start"] - 12.0) < 1e-6 and s["speaker_id"] == "multiple" for s in segs)
    # Speakers list should include synthetic "multiple"
    speakers = stj["stj"]["transcript"]["speakers"]
    ids = {sp["id"] for sp in speakers}
    assert "multiple" in ids


def test_include_unknown_includes_empty_users_segments():
    data = _synthetic_timeline()
    stj = timeline_to_minimal_stj(data, duration_sec=16.0, include_unknown=True)
    segs = stj["stj"]["transcript"]["segments"]
    assert any(s["speaker_id"] == "unknown" for s in segs)


def test_timeline_refine_precedence():
    data = _synthetic_timeline()
    # Add an alternative refine with different timing to verify precedence
    data["timeline_refine"] = [
        {"ts": "00:00:09.500", "users": [{"username": "Alice", "zoom_userid": "Z_A"}]},
        {"ts": "00:00:12.000", "users": [{"username": "Bob", "zoom_userid": "Z_B"}]},
    ]
    stj = timeline_to_minimal_stj(data, duration_sec=16.0)
    segs = stj["stj"]["transcript"]["segments"]
    # First segment should start from 9.5 (refine) rather than 10.0 (timeline)
    assert any(abs(s["start"] - 9.5) < 1e-6 for s in segs)


def test_merge_and_min_drop():
    data = {
        "timeline": [
            {"ts": "00:00:00.000", "users": [{"username": "A", "zoom_userid": "Z1"}]},
            {"ts": "00:00:00.600", "users": [{"username": "A", "zoom_userid": "Z1"}]},
            {"ts": "00:00:02.000", "users": [{"username": "A", "zoom_userid": "Z1"}]},
        ]
    }
    stj = timeline_to_minimal_stj(data, duration_sec=3.0, min_segment_sec=1.0, merge_gap_sec=1.5)
    segs = stj["stj"]["transcript"]["segments"]
    # Short initial 0.6s should be merged into longer segment or dropped
    assert segs[0]["start"] <= 0.0 + 1e-6
    assert segs[0]["end"] >= 2.0 - 1e-6
