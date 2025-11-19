from datetime import date

from dlzoom import cli as cli_mod


def test_calc_range_uses_utc_today(monkeypatch):
    """Range shortcuts should use UTC date to avoid timezone drift."""
    monkeypatch.setattr(cli_mod, "_utc_today", lambda: date(2025, 1, 10))

    start, end = cli_mod._calc_range("last-7-days")

    assert start == "2025-01-04"
    assert end == "2025-01-10"


def test_utc_today_requests_timezone_aware_now(monkeypatch):
    """Ensure UTC helper invokes datetime.now with timezone.utc."""
    captured = {}

    class DummyNow:
        def date(self):
            return date(2025, 2, 3)

    class DummyDatetime:
        @staticmethod
        def now(tz=None):
            captured["tz"] = tz
            return DummyNow()

    monkeypatch.setattr(cli_mod, "datetime", DummyDatetime)

    result = cli_mod._utc_today()

    assert result == date(2025, 2, 3)
    assert captured["tz"] is cli_mod.timezone.utc
