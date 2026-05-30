"""
Adversarial tests for RemoteInHostKeyPolicy in connector.py.

Covers SSH-01 / SSH-02 at the Paramiko policy layer:

  SSH-01 — First connect to unknown host invokes the verifier; reject raises
            SSHException and blocks the connection.
  SSH-02 — accept_once and always_trust both allow the connection through;
            always_trust is distinguished from accept_once only by what the
            verifier (and DB layer) does — from Paramiko's perspective both
            return without raising.

Test strategy
-------------
These are *adversarial* tests targeting the exact failure modes the plan
identified:

  1. verifier returns "reject"        → SSHException raised
  2. verifier returns "accept_once"   → no exception, returns None
  3. verifier returns "always_trust"  → no exception, returns None
  4. verifier receives correct kwargs → hostname, port, key_type, fingerprint,
                                        key_blob all present and correct
  5. unexpected verifier return value → treated as reject (SSHException)
  6. verifier_fn=None guard           → _connect_with_policy falls back to
                                        standard ConnectHandler (no policy set)

No db.py import. No PyQt6 import. No network connections.
Paramiko is imported only to check SSHException and the MissingHostKeyPolicy
base class — no live SSH sessions are opened.
"""

from unittest.mock import MagicMock, patch

import paramiko
import pytest

import connector
from connector import RemoteInHostKeyPolicy, _connect_with_policy


# ── Mock Paramiko key object ───────────────────────────────────────────────────

class MockKey:
    """Minimal stand-in for a paramiko.PKey object."""

    def get_name(self):
        return "ssh-ed25519"

    @property
    def fingerprint(self):
        # Paramiko 3.x+ returns a SHA256:Base64 string from .fingerprint
        return "SHA256:AAABBBCCC"

    def asbytes(self):
        return b"fake-key-bytes"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_policy(verifier_fn, port=22):
    """Construct a RemoteInHostKeyPolicy with the given verifier and port."""
    return RemoteInHostKeyPolicy(verifier_fn, port=port)


def _call_missing(policy, hostname="10.0.0.1"):
    """Invoke missing_host_key with a MockKey and return the result."""
    return policy.missing_host_key(client=None, hostname=hostname, key=MockKey())


# ── Test 1: reject → SSHException ─────────────────────────────────────────────

def test_reject_raises_ssh_exception():
    """verifier returns 'reject' → paramiko.SSHException must be raised."""
    policy = _make_policy(lambda **kw: "reject")
    with pytest.raises(paramiko.SSHException, match="Host key rejected by user"):
        _call_missing(policy)


# ── Test 2: accept_once → no exception ────────────────────────────────────────

def test_accept_once_does_not_raise():
    """verifier returns 'accept_once' → connection allowed, no exception."""
    policy = _make_policy(lambda **kw: "accept_once")
    result = _call_missing(policy)
    # Paramiko expects missing_host_key to return None on acceptance
    assert result is None


# ── Test 3: always_trust → no exception ───────────────────────────────────────

def test_always_trust_does_not_raise():
    """verifier returns 'always_trust' → connection allowed, no exception."""
    policy = _make_policy(lambda **kw: "always_trust")
    result = _call_missing(policy)
    assert result is None


# ── Test 4: verifier receives correct keyword arguments ───────────────────────

def test_verifier_receives_correct_kwargs():
    """missing_host_key must call verifier with all required keyword arguments."""
    captured = {}

    def capture_verifier(**kw):
        captured.update(kw)
        return "accept_once"

    policy = _make_policy(capture_verifier, port=22)
    policy.missing_host_key(client=None, hostname="10.0.0.1", key=MockKey())

    assert captured["hostname"] == "10.0.0.1", f"hostname mismatch: {captured['hostname']!r}"
    assert captured["port"] == 22, f"port mismatch: {captured['port']!r}"
    assert captured["key_type"] == "ssh-ed25519", f"key_type mismatch: {captured['key_type']!r}"
    assert captured["fingerprint"] == "SHA256:AAABBBCCC", (
        f"fingerprint mismatch: {captured['fingerprint']!r}"
    )
    assert "key_blob" in captured, "key_blob missing from verifier kwargs"
    assert len(captured["key_blob"]) > 0, "key_blob must be non-empty"
    # key_blob must be valid base64 (no spaces, ends with = padding or plain base64 chars)
    import base64
    decoded = base64.b64decode(captured["key_blob"])
    assert decoded == b"fake-key-bytes", (
        f"key_blob decoded incorrectly: {decoded!r}"
    )


# ── Test 5: unexpected return value → treated as reject ───────────────────────

def test_unexpected_return_treated_as_reject():
    """Any return value other than accept_once/always_trust must raise SSHException."""
    for bad_value in ("maybe", "yes", "allow", "", None, 42, True):
        policy = _make_policy(lambda **kw: bad_value)
        with pytest.raises(paramiko.SSHException, match="Host key rejected by user"):
            _call_missing(policy)


# ── Test 6: verifier_fn=None → standard ConnectHandler, no policy set ─────────

def test_no_verifier_skips_policy():
    """_connect_with_policy with verifier_fn=None must NOT set key_policy.

    This guards against accidentally applying a broken RemoteInHostKeyPolicy
    (with _verifier_fn=None) when no verifier has been wired yet.
    """
    fake_kwargs = {
        "device_type": "cisco_ios",
        "host": "10.0.0.1",
        "port": 22,
        "username": "admin",
        "password": "secret",
        "secret": "",
        "timeout": 15,
        "system_host_keys": False,
        "use_keys": False,
        "key_file": None,
    }

    mock_conn = MagicMock()

    with patch.object(connector, "ConnectHandler", return_value=mock_conn) as mock_ch:
        result = _connect_with_policy(fake_kwargs, verifier_fn=None)

    # ConnectHandler was called once with the kwargs (no auto_connect=False)
    mock_ch.assert_called_once_with(**fake_kwargs)

    # key_policy must NOT have been set on the connection object
    assert not hasattr(mock_conn, "key_policy") or "key_policy" not in mock_conn.__dict__, (
        "key_policy must not be set when verifier_fn is None"
    )

    # _open() must NOT have been called (standard path, auto_connect handles it)
    mock_conn._open.assert_not_called()

    # The returned object is the ConnectHandler mock
    assert result is mock_conn


# ── Structural checks ──────────────────────────────────────────────────────────

def test_policy_subclasses_missing_host_key_policy():
    """RemoteInHostKeyPolicy must subclass paramiko.client.MissingHostKeyPolicy."""
    assert issubclass(RemoteInHostKeyPolicy, paramiko.client.MissingHostKeyPolicy)


def test_connector_does_not_import_db_gui_or_threading():
    """connector.py must not import db, PyQt6, or threading (architecture rule)."""
    import importlib
    import types

    # Walk the connector module's globals for any submodule that is
    # db, PyQt6, or threading
    forbidden = {"db", "PyQt6", "threading"}
    violations = []
    for name, obj in vars(connector).items():
        if isinstance(obj, types.ModuleType):
            mod_name = obj.__name__.split(".")[0]
            if mod_name in forbidden:
                violations.append(f"{name!r} → {obj.__name__!r}")

    assert not violations, (
        "connector.py must not import db, PyQt6, or threading. "
        f"Found: {violations}"
    )
