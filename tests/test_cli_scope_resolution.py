import pytest

from dlzoom.exceptions import ConfigError
from dlzoom.handlers import _resolve_scope


def test_s2s_auto_defaults_to_account():
    ctx = _resolve_scope(use_s2s=True, scope_flag="auto", user_id=None, default_s2s_user=None)
    assert ctx.scope == "account"
    assert ctx.user_id is None


def test_s2s_user_scope_requires_explicit_id():
    with pytest.raises(ConfigError):
        _resolve_scope(use_s2s=True, scope_flag="user", user_id=None, default_s2s_user=None)


def test_s2s_user_scope_with_id():
    ctx = _resolve_scope(
        use_s2s=True,
        scope_flag="user",
        user_id="user@example.com",
        default_s2s_user=None,
    )
    assert ctx.scope == "user"
    assert ctx.user_id == "user@example.com"


def test_s2s_user_scope_uses_default_user():
    ctx = _resolve_scope(
        use_s2s=True,
        scope_flag="user",
        user_id=None,
        default_s2s_user="fallback@example.com",
    )
    assert ctx.scope == "user"
    assert ctx.user_id == "fallback@example.com"


def test_user_tokens_default_to_me():
    ctx = _resolve_scope(use_s2s=False, scope_flag="auto", user_id=None, default_s2s_user=None)
    assert ctx.scope == "user"
    assert ctx.user_id == "me"
