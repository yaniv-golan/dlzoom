"""
STJ minimalizer: Convert Zoom timeline JSON to minimal STJ diarization JSON.

Generates a compact STJ file that contains only speaker segments
(start, end, speaker_id, empty text). Designed to be default-on and
safe to run post-timeline download.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _parse_hhmmss_ms(ts: str) -> float:
    """Parse HH:MM:SS.mmm string to seconds (float).

    Accepts variants like HH:MM:SS, HH:MM:SS.m, HH:MM:SS.mm, HH:MM:SS.mmm
    """
    try:
        # Fast path when format is HH:MM:SS.mmm
        h, mm_str, s = ts.split(":")
        sec = float(s)
        return int(h) * 3600 + int(mm_str) * 60 + sec
    except Exception:
        # Fallback: extract numerical parts
        match = re.match(r"^(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$", ts.strip())
        if not match:
            raise ValueError(f"Invalid timestamp: {ts!r}")
        hh, mm, ss, ms = match.groups()
        base = int(hh) * 3600 + int(mm) * 60 + int(ss)
        if ms:
            frac = float(f"0.{ms}")
        else:
            frac = 0.0
        return base + frac


def _slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")
    s = re.sub(r"-+", "-", s)
    return s.lower() or "speaker"


@dataclass(frozen=True)
class _Speaker:
    id: str
    name: str


def _choose_speaker_id(users: list[dict[str, Any]] | None, mode: str) -> str | None:
    if not users:
        return None
    if len(users) > 1 and mode == "multiple":
        return "multiple"
    u = users[0]
    zid = (u.get("zoom_userid") or "").strip()
    if zid:
        return zid
    uid = u.get("user_id")
    if uid is not None and str(uid).strip() != "":
        return f"uid:{uid}"
    uname = (u.get("username") or "speaker").strip()
    return _slugify(uname)


def _build_speakers(
    entries: Iterable[dict[str, Any]], *, include_unknown: bool, mode: str
) -> list[_Speaker]:
    # Deterministic map of id -> name with collision handling for slugified names
    id_to_name: dict[str, str] = {}
    slug_counts: dict[str, int] = {}

    def add_user(u: dict[str, Any]) -> None:
        zid = (u.get("zoom_userid") or "").strip()
        if zid:
            id_to_name.setdefault(zid, str(u.get("username") or zid))
            return
        uid = u.get("user_id")
        if uid is not None and str(uid).strip() != "":
            key = f"uid:{uid}"
            id_to_name.setdefault(key, str(u.get("username") or key))
            return
        uname = (u.get("username") or "speaker").strip()
        base = _slugify(uname)
        # disambiguate
        if base in id_to_name:
            slug_counts[base] = slug_counts.get(base, 1) + 1
            key = f"{base}-{slug_counts[base]}"
        else:
            slug_counts[base] = 1
            key = base
        id_to_name.setdefault(key, uname)

    for e in entries:
        users = e.get("users") or []
        if not isinstance(users, list):
            continue
        for u in users:
            if isinstance(u, dict):
                add_user(u)

    # Add synthetic speakers if used by policy
    if mode == "multiple":
        id_to_name.setdefault("multiple", "Multiple speakers")
    if include_unknown:
        id_to_name.setdefault("unknown", "Unknown")

    # Deterministic order: by name, then id
    speakers = [_Speaker(id=k, name=v) for k, v in id_to_name.items()]
    speakers.sort(key=lambda sp: (sp.name.lower(), sp.id))
    return speakers


def _merge_and_filter_segments(
    segments: list[tuple[float, float, str]], *, min_segment_sec: float, merge_gap_sec: float
) -> list[tuple[float, float, str]]:
    if not segments:
        return []
    # Sort by start time
    segments.sort(key=lambda t: t[0])

    merged: list[tuple[float, float, str]] = []
    for s, e, sid in segments:
        if e <= s:
            continue  # drop zero/negative length
        if not merged:
            merged.append((s, e, sid))
            continue
        ps, pe, pid = merged[-1]
        if pid == sid and s - pe <= merge_gap_sec:
            # merge
            merged[-1] = (ps, max(pe, e), pid)
        else:
            merged.append((s, e, sid))

    # Drop short segments or try to fuse if neighbors are same speaker
    result: list[tuple[float, float, str]] = []
    for i, (s, e, sid) in enumerate(merged):
        dur = e - s
        if dur + 1e-9 >= min_segment_sec:
            result.append((s, e, sid))
            continue
        # attempt fuse with previous if same speaker
        if result and result[-1][2] == sid:
            ps, pe, pid = result[-1]
            result[-1] = (ps, max(pe, e), pid)
            continue
        # attempt fuse with next if same speaker
        if i + 1 < len(merged) and merged[i + 1][2] == sid:
            ns, ne, nid = merged[i + 1]
            merged[i + 1] = (min(s, ns), max(e, ne), nid)
            continue
        # else drop
        # intentionally do nothing
    return result


def timeline_to_minimal_stj(
    timeline: dict,
    *,
    duration_sec: float | None = None,
    mode: str = "first",
    min_segment_sec: float = 1.0,
    merge_gap_sec: float = 1.5,
    include_unknown: bool = False,
    timeline_source: str | None = None,
) -> dict:
    """Convert Zoom timeline JSON to minimal STJ dict.

    Parameters mirror the design plan. Only diarization segments are emitted.
    """
    entries = []
    source_name = None
    # Prefer timeline_refine when available
    if isinstance(timeline.get("timeline_refine"), list) and timeline["timeline_refine"]:
        entries = timeline["timeline_refine"]
        source_name = "timeline_refine"
    elif isinstance(timeline.get("timeline"), list) and timeline["timeline"]:
        entries = timeline["timeline"]
        source_name = "timeline"
    else:
        entries = []

    if timeline_source:
        source_name = timeline_source

    # Build speakers registry
    speakers_list = _build_speakers(entries, include_unknown=include_unknown, mode=mode)
    used_speakers: set[str] = set()

    # Build raw segments
    raw_segments: list[tuple[float, float, str]] = []
    for i, e in enumerate(entries):
        ts = e.get("ts")
        try:
            s = _parse_hhmmss_ms(str(ts))
        except Exception:
            continue
        if i + 1 < len(entries):
            e2 = entries[i + 1]
            try:
                end = _parse_hhmmss_ms(str(e2.get("ts")))
            except Exception:
                end = s
        else:
            end = duration_sec if duration_sec is not None else s
        sid = _choose_speaker_id(e.get("users"), mode)
        if sid is None:
            if include_unknown:
                sid = "unknown"
            else:
                continue
        raw_segments.append((s, end, sid))
        used_speakers.add(sid)

    segments = _merge_and_filter_segments(
        raw_segments, min_segment_sec=min_segment_sec, merge_gap_sec=merge_gap_sec
    )

    # Deterministic rounding
    rounded_segments = []
    for s, e, sid in segments:
        s = round(s, 3)
        e = round(e, 3)
        if e <= s:
            continue
        rounded_segments.append((s, e, sid))

    # Prepare speakers array with only referenced speakers to keep minimal
    # but keep synthetic ids if policy uses them and they appear in used_speakers
    speakers = [{"id": sp.id, "name": sp.name} for sp in speakers_list if sp.id in used_speakers]
    # Ensure order stability by sort by name then id (already sorted in build)

    # Metadata
    try:
        from dlzoom import __version__ as _dlzoom_version
    except Exception:
        _dlzoom_version = ""

    metadata: dict[str, Any] = {
        "transcriber": {"name": "dlzoom", "version": _dlzoom_version},
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "extensions": {"dlzoom": {"mode": "diarization_only", "transcription_pending": True}},
    }
    source: dict[str, Any] = {"extensions": {"zoom": {"has_timeline": bool(entries)}}}
    if duration_sec is not None:
        source["duration"] = float(duration_sec)
    source["languages"] = ["und"]
    if source_name:
        source["extensions"]["zoom"]["timeline_source"] = source_name
    metadata["source"] = source

    stj = {
        "stj": {
            "version": "0.6.0",
            "metadata": metadata,
            "transcript": {
                "speakers": speakers,
                "segments": [
                    {"start": s, "end": e, "speaker_id": sid, "text": ""}
                    for (s, e, sid) in rounded_segments
                ],
            },
        }
    }
    return stj


def write_minimal_stj_from_file(
    timeline_path: Path,
    output_path: Path,
    *,
    duration_sec: float | None = None,
    mode: str = "first",
    min_segment_sec: float = 1.0,
    merge_gap_sec: float = 1.5,
    include_unknown: bool = False,
) -> Path:
    """Read a Zoom timeline JSON file and write minimal STJ to output_path."""
    try:
        with open(timeline_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to read timeline JSON: {timeline_path}: {e}")

    stj = timeline_to_minimal_stj(
        data,
        duration_sec=duration_sec,
        mode=mode,
        min_segment_sec=min_segment_sec,
        merge_gap_sec=merge_gap_sec,
        include_unknown=include_unknown,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return output_path
