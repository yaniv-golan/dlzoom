"""
STJ minimalizer: Convert Zoom timeline JSON to minimal STJ diarization JSON.

Generates a compact STJ file that contains only speaker segments
(start, end, speaker_id, empty text). Designed to be default-on and
safe to run post-timeline download.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_SPEAKER_ID_LEN = 64


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
    extensions: dict[str, Any] | None = None


def _user_identity_key(user: dict[str, Any]) -> str:
    zid = (user.get("zoom_userid") or "").strip()
    if zid:
        return f"zoom:{zid}"
    uid = user.get("user_id")
    if uid is not None:
        uid_str = str(uid).strip()
        if uid_str:
            return f"uid:{uid_str}"
    uname = (user.get("username") or "").strip()
    if uname:
        return f"name:{uname.lower()}"
    fingerprint = json.dumps(user, sort_keys=True, default=str)
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()
    return f"anon:{digest}"


def _speaker_extensions(user: dict[str, Any]) -> dict[str, Any] | None:
    zoom_ext: dict[str, Any] = {}
    zid = (user.get("zoom_userid") or "").strip()
    if zid:
        zoom_ext["participant_id"] = zid
    uid = user.get("user_id")
    if uid is not None:
        uid_str = str(uid).strip()
        if uid_str:
            zoom_ext["user_id"] = uid_str
    if not zoom_ext:
        return None
    return {"zoom": zoom_ext}


def _display_name(user: dict[str, Any]) -> str:
    name = (user.get("username") or "").strip()
    if name:
        return name
    zid = (user.get("zoom_userid") or "").strip()
    if zid:
        return zid
    uid = user.get("user_id")
    if uid is not None:
        uid_str = str(uid).strip()
        if uid_str:
            return uid_str
    return "Speaker"


class _SpeakerRegistry:
    def __init__(self, *, include_unknown: bool, mode: str) -> None:
        self.include_unknown = include_unknown
        self.mode = mode
        self._identity_to_id: dict[str, str] = {}
        self._slug_counts: dict[str, int] = {}
        self._speakers: dict[str, _Speaker] = {}
        if mode == "multiple":
            self._speakers["multiple"] = _Speaker(id="multiple", name="Multiple speakers")
        if include_unknown:
            self._speakers["unknown"] = _Speaker(id="unknown", name="Unknown")

    def ingest(self, entries: Iterable[dict[str, Any]]) -> None:
        for entry in entries:
            users = entry.get("users") or []
            if not isinstance(users, list):
                continue
            for user in users:
                if isinstance(user, dict):
                    self._get_or_create(user)

    def _get_or_create(self, user: dict[str, Any]) -> str:
        key = _user_identity_key(user)
        if key in self._identity_to_id:
            return self._identity_to_id[key]
        name = _display_name(user)
        base_slug = _slugify(name)
        if not base_slug:
            base_slug = "speaker"
        base_slug = base_slug[:_MAX_SPEAKER_ID_LEN]
        slug = self._reserve_slug(base_slug or "speaker")
        extensions = _speaker_extensions(user)
        speaker = _Speaker(id=slug, name=name, extensions=extensions)
        self._speakers[slug] = speaker
        self._identity_to_id[key] = slug
        return slug

    def _reserve_slug(self, base: str) -> str:
        slug_base = base or "speaker"
        slug_base = slug_base[:_MAX_SPEAKER_ID_LEN]
        count = self._slug_counts.get(slug_base, 0) + 1
        self._slug_counts[slug_base] = count
        if count == 1:
            return slug_base
        suffix = f"-{count}"
        max_base_len = max(1, _MAX_SPEAKER_ID_LEN - len(suffix))
        trimmed = slug_base[:max_base_len].rstrip("-")
        if not trimmed:
            trimmed = "speaker"
        return f"{trimmed}{suffix}"

    def speaker_id_for_users(self, users: list[dict[str, Any]] | None) -> str | None:
        if not users:
            return None
        if len(users) > 1 and self.mode == "multiple":
            return "multiple"
        first = users[0]
        if not isinstance(first, dict):
            return None
        return self._get_or_create(first)

    def speakers_for_ids(self, used_ids: set[str]) -> list[dict[str, Any]]:
        selected: list[_Speaker] = [sp for sid, sp in self._speakers.items() if sid in used_ids]
        selected.sort(key=lambda sp: (sp.name.lower(), sp.id))
        result: list[dict[str, Any]] = []
        for sp in selected:
            entry: dict[str, Any] = {"id": sp.id, "name": sp.name}
            if sp.extensions:
                entry["extensions"] = sp.extensions
            result.append(entry)
        return result


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


def _apply_context_to_metadata(metadata: dict[str, Any], context: dict[str, Any]) -> None:
    source = metadata.setdefault("source", {})
    meeting = context.get("meeting") or {}
    scope = context.get("scope") or {}
    recording_files = context.get("recording_files")
    flags = context.get("flags") or {}
    cli = context.get("cli") or {}

    source_uri = context.get("source_uri")
    if source_uri:
        source["uri"] = source_uri
    duration = meeting.get("duration")
    if duration is not None and "duration" not in source:
        try:
            source["duration"] = float(duration)
        except (TypeError, ValueError):
            pass

    zoom_ext = source.setdefault("extensions", {}).setdefault("zoom", {})
    if meeting.get("id"):
        zoom_ext["meeting_id"] = meeting.get("id")
    if meeting.get("uuid"):
        zoom_ext["meeting_uuid"] = meeting.get("uuid")
    if meeting.get("recording_uuid"):
        zoom_ext["recording_uuid"] = meeting.get("recording_uuid")
    if recording_files:
        zoom_ext["recording_files"] = recording_files
        zoom_ext["recording_files_count"] = len(recording_files)
    if scope.get("mode"):
        zoom_ext["scope"] = scope.get("mode")
    if scope.get("user_id"):
        zoom_ext["scope_user_id"] = scope.get("user_id")
    if scope.get("account_id"):
        zoom_ext["account_id"] = scope.get("account_id")

    dlzoom_ext = metadata.setdefault("extensions", {}).setdefault("dlzoom", {})
    if meeting.get("topic"):
        dlzoom_ext["topic"] = meeting.get("topic")
    host = {}
    if meeting.get("host_email"):
        host["email"] = meeting.get("host_email")
    if meeting.get("host_id"):
        host["id"] = meeting.get("host_id")
    if meeting.get("host_name"):
        host["name"] = meeting.get("host_name")
    if host:
        dlzoom_ext["host"] = host
    if meeting.get("start_time"):
        dlzoom_ext["start_time"] = meeting.get("start_time")
    if meeting.get("timezone"):
        dlzoom_ext["timezone"] = meeting.get("timezone")
    if meeting.get("duration") is not None:
        dlzoom_ext["duration_minutes"] = meeting.get("duration")
    if flags:
        dlzoom_ext["flags"] = flags
    if cli:
        dlzoom_ext["cli"] = cli
    generated = context.get("generated")
    if generated:
        dlzoom_ext["generated"] = generated


def timeline_to_minimal_stj(
    timeline: dict,
    *,
    duration_sec: float | None = None,
    mode: str = "first",
    min_segment_sec: float = 1.0,
    merge_gap_sec: float = 1.5,
    include_unknown: bool = False,
    timeline_source: str | None = None,
    context: dict[str, Any] | None = None,
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

    registry = _SpeakerRegistry(include_unknown=include_unknown, mode=mode)
    registry.ingest(entries)
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
        sid = registry.speaker_id_for_users(e.get("users"))
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

    speakers = registry.speakers_for_ids(used_speakers)

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

    if context:
        _apply_context_to_metadata(metadata, context)

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
    context: dict[str, Any] | None = None,
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
        context=context,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return output_path
