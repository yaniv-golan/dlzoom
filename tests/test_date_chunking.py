import pytest

from dlzoom.exceptions import ConfigError
from dlzoom.handlers import _chunk_by_month


def test_chunk_by_month_handles_multi_month_span():
    chunks = _chunk_by_month("2024-01-01", "2024-03-31")
    assert chunks == [
        ("2024-01-01", "2024-01-31"),
        ("2024-02-01", "2024-02-29"),
        ("2024-03-01", "2024-03-31"),
    ]


def test_chunk_by_month_handles_non_leap_year():
    chunks = _chunk_by_month("2023-01-15", "2023-02-20")
    assert chunks == [
        ("2023-01-15", "2023-01-31"),
        ("2023-02-01", "2023-02-20"),
    ]


def test_chunk_by_month_handles_boundary_crossing():
    chunks = _chunk_by_month("2024-01-31", "2024-02-02")
    assert chunks == [
        ("2024-01-31", "2024-01-31"),
        ("2024-02-01", "2024-02-02"),
    ]


def test_chunk_by_month_handles_long_range():
    chunks = _chunk_by_month("2024-01-01", "2024-06-30")
    assert len(chunks) == 6
    assert chunks[0] == ("2024-01-01", "2024-01-31")
    assert chunks[-1] == ("2024-06-01", "2024-06-30")


def test_chunk_by_month_invalid_range_raises():
    with pytest.raises(ConfigError):
        _chunk_by_month("2024-02-10", "2024-02-01")


def test_chunk_by_month_returns_single_chunk_when_missing_dates():
    assert _chunk_by_month(None, None) == [(None, None)]
    assert _chunk_by_month("2024-01-01", None) == [("2024-01-01", None)]
