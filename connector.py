from __future__ import annotations

import base64

import paramiko
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
from db import decrypt_field


# ── Genie/pyATS optional import ────────────────────────────────────────────────
try:
    from genie.testbed import load as genie_load
    GENIE_AVAILABLE = True
except ImportError:
    GENIE_AVAILABLE = False


class RemoteInHostKeyPolicy(paramiko.client.MissingHostKeyPolicy):
    """
    Custom Paramiko host key policy that delegates the accept/reject decision
    to an injected verifier_fn callable.

    The verifier_fn is called with keyword arguments:
        hostname  — the remote hostname string
        port      — the port (captured at construction; Paramiko does not pass it)
        key_type  — e.g. 'ssh-ed25519', 'ecdsa-sha2-nistp256', 'ssh-rsa'
        fingerprint — SHA256:Base64 string (key.fingerprint property, Paramiko 3.x+)
        key_blob  — base64-encoded full public key bytes for DB storage

    The verifier_fn must return one of:
        "accept_once"  — allow this connection, do not persist to DB
        "always_trust" — allow this connection (verifier already persisted to DB)
        "reject"       — deny connection (raises paramiko.SSHException)
        <any other>    — treated as "reject" (raises paramiko.SSHException)

    If the verifier_fn raises an exception, it propagates and becomes a
    Netmiko connection error caught by FetchWorker.
    """

    def __init__(self, verifier_fn, *, port: int):
        self._verifier_fn = verifier_fn
        self._port = port

    def missing_host_key(self, client, hostname, key):
        """Called by Paramiko when a host key is not in the trusted set."""
        key_type_str = key.get_name()
        # Use .fingerprint property (SHA256:Base64) — NOT key.get_fingerprint()
        # which returns 16 raw MD5 bytes. SHA256 is the modern standard.
        fingerprint_str = key.fingerprint
        # Full public key bytes as base64 — used for exact cryptographic comparison
        # and DB storage. Raw bytes never stored directly.
        key_blob_b64 = base64.b64encode(key.asbytes()).decode("ascii")

        result = self._verifier_fn(
            hostname=hostname,
            port=self._port,
            key_type=key_type_str,
            fingerprint=fingerprint_str,
            key_blob=key_blob_b64,
        )

        if result in ("accept_once", "always_trust"):
            return  # Paramiko accepts the connection
        # "reject" or any unexpected value → deny
        raise paramiko.SSHException("Host key rejected by user")


PLATFORM_MAP = {
    "ios":    "cisco_ios",
    "iosxe":  "cisco_xe",
    "iosxr":  "cisco_xr",
    "nxos":   "cisco_nxos",
    "eos":    "arista_eos",
    "junos":  "juniper_junos",
}

NO_ENABLE_PLATFORMS = {"eos", "junos"}


def _netmiko_device(device: dict, session_key: bytes, verifier_fn=None) -> dict:
    """Build Netmiko connection dict from device record, decrypting credentials.

    verifier_fn: optional callable passed to RemoteInHostKeyPolicy. When None,
    _connect_with_policy() falls back to a standard ConnectHandler (no custom
    policy). For production use, always supply a verifier_fn.
    """
    _pw = decrypt_field(session_key, device["password"])
    _ep = decrypt_field(session_key, device.get("enable_pass", ""))
    if _pw is None:
        raise ValueError("Credential decryption failed — check session key or DB integrity")
    return {
        "device_type":      PLATFORM_MAP.get(device["platform"], "cisco_ios"),
        "host":             device["hostname"],
        "port":             device.get("port", 22),
        "username":         device["username"],
        "password":         _pw,
        "secret":           _ep or "",
        "timeout":          15,
        # system_host_keys=False: RemoteIn manages host keys via its own DB table.
        # Setting True would cause Paramiko to silently accept any host already in
        # ~/.ssh/known_hosts, bypassing RemoteInHostKeyPolicy entirely — a MITM risk.
        "system_host_keys": False,
        "use_keys":         False,  # don't use SSH key files
        "key_file":         None,   # no key file
    }


def _genie_testbed(device: dict, session_key: bytes) -> dict:
    """Build minimal pyATS testbed dict for a single device, decrypting credentials."""
    plat = device["platform"]
    os_map = {"ios": "ios", "iosxe": "iosxe", "iosxr": "iosxr", "nxos": "nxos", "eos": "eos", "junos": "junos"}
    _pw = decrypt_field(session_key, device["password"])
    _ep = decrypt_field(session_key, device.get("enable_pass", ""))
    if _pw is None:
        raise ValueError("Credential decryption failed — check session key or DB integrity")
    return {
        "devices": {
            device["name"]: {
                "os":           os_map.get(plat, "ios"),
                "platform":     plat,
                "type":         "router",
                "connections": {
                    "default": {
                        "protocol":  "ssh",
                        "ip":        device["hostname"],
                        "port":      device.get("port", 22),
                    }
                },
                "credentials": {
                    "default": {
                        "username": device["username"],
                        "password": _pw,
                    },
                    "enable": {
                        "password": _ep or "",
                    },
                },
            }
        }
    }


def _send(conn, command: str) -> tuple[str, dict | list | None]:
    """
    Send a command and attempt TextFSM parsing.
    Returns (source, data) where source is 'textfsm' or 'raw'.
    - 'textfsm': data is a list of dicts
    - 'raw':     data is a plain string
    """
    parsed = conn.send_command(command, use_textfsm=True)
    if isinstance(parsed, list):
        return "textfsm", parsed
    return "raw", parsed


def _genie_fetch(device: dict, cmd: str, session_key: bytes) -> dict | None:
    """Connect via Genie, parse cmd, disconnect. Returns parsed dict or None on failure."""
    dev = None
    try:
        tb = genie_load(_genie_testbed(device, session_key))
        dev = tb.devices[device["name"]]
        dev.connect(log_stdout=False, learn_hostname=True)
        return dev.parse(cmd)
    except Exception:
        return None
    finally:
        if dev is not None:
            try:
                dev.disconnect()
            except Exception:
                pass


def _connect_with_policy(netmiko_kwargs: dict, verifier_fn) -> ConnectHandler:
    """Open a Netmiko connection, injecting RemoteInHostKeyPolicy when a verifier is provided.

    When verifier_fn is None: falls back to standard ConnectHandler (no custom policy).
    This can occur during partial wiring or in test contexts. Production code should
    always supply a verifier_fn.

    When verifier_fn is provided:
      1. Instantiate RemoteInHostKeyPolicy with the verifier and the connection port.
      2. Build ConnectHandler with auto_connect=False (socket not yet opened).
      3. Assign conn.key_policy before the connection opens.
      4. Call conn._open() — triggers the Paramiko SSH handshake, which invokes
         missing_host_key if the host key is not already trusted.

    If missing_host_key raises paramiko.SSHException (user rejected), it propagates
    out of _open(), out of _connect_with_policy(), and is caught by FetchWorker.run()
    which emits it as error(str(exc)) to the status bar.
    """
    if verifier_fn is None:
        return ConnectHandler(**netmiko_kwargs)

    port = netmiko_kwargs.get("port", 22)
    policy = RemoteInHostKeyPolicy(verifier_fn, port=port)
    conn = ConnectHandler(**netmiko_kwargs, auto_connect=False)
    conn.key_policy = policy
    conn._open()
    return conn


# ── Public API ─────────────────────────────────────────────────────────────────

def get_interfaces(device: dict, session_key: bytes, verifier_fn=None) -> dict:
    """Return structured interface data via Genie, TextFSM, or raw CLI.

    Note: the Genie path (Linux/Mac only) uses pyATS's own SSH stack and does not
    support RemoteInHostKeyPolicy. Host key verification applies to the Netmiko path only.
    """
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show interfaces", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    kwargs = _netmiko_device(device, session_key)
    with _connect_with_policy(kwargs, verifier_fn) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show interfaces")
    return {"source": source, "data": data}


def get_routing_table(device: dict, session_key: bytes, verifier_fn=None) -> dict:
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show ip route", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    kwargs = _netmiko_device(device, session_key)
    with _connect_with_policy(kwargs, verifier_fn) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show ip route")
    return {"source": source, "data": data}


def get_bgp_neighbors(device: dict, session_key: bytes, verifier_fn=None) -> dict:
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show bgp all neighbors", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    kwargs = _netmiko_device(device, session_key)
    with _connect_with_policy(kwargs, verifier_fn) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show ip bgp neighbors")
    return {"source": source, "data": data}


def get_ospf_neighbors(device: dict, session_key: bytes, verifier_fn=None) -> dict:
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show ip ospf neighbor", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    kwargs = _netmiko_device(device, session_key)
    with _connect_with_policy(kwargs, verifier_fn) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show ip ospf neighbor")
    return {"source": source, "data": data}


def get_arp_table(device: dict, session_key: bytes, verifier_fn=None) -> dict:
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show ip arp", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    kwargs = _netmiko_device(device, session_key)
    with _connect_with_policy(kwargs, verifier_fn) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show ip arp")
    return {"source": source, "data": data}


def get_mac_table(device: dict, session_key: bytes, verifier_fn=None) -> dict:
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show mac address-table", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    kwargs = _netmiko_device(device, session_key)
    with _connect_with_policy(kwargs, verifier_fn) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show mac address-table")
    return {"source": source, "data": data}


def run_cli_command(device: dict, command: str, session_key: bytes, verifier_fn=None) -> str:
    """Run an arbitrary CLI command and return raw output."""
    kwargs = _netmiko_device(device, session_key)
    with _connect_with_policy(kwargs, verifier_fn) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        output = conn.send_command(command, read_timeout=30)
    return output