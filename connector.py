from __future__ import annotations

from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
from db import decrypt_field


# ── Genie/pyATS optional import ────────────────────────────────────────────────
try:
    from genie.testbed import load as genie_load
    GENIE_AVAILABLE = True
except ImportError:
    GENIE_AVAILABLE = False


PLATFORM_MAP = {
    "ios":    "cisco_ios",
    "iosxe":  "cisco_xe",
    "iosxr":  "cisco_xr",
    "nxos":   "cisco_nxos",
    "eos":    "arista_eos",
    "junos":  "juniper_junos",
}

NO_ENABLE_PLATFORMS = {"eos", "junos"}


def _netmiko_device(device: dict, session_key: bytes) -> dict:
    """Build Netmiko connection dict from device record, decrypting credentials."""
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
        "ssh_strict":       False,  # auto-accept unknown host keys
        "system_host_keys": False,  # don't load system known_hosts file
        "use_keys":         False,  # don't use SSH key files
        "key_file":         None,   # no key file
        "disabled_algorithms": {
            "pubkeys": ["rsa-sha2-256", "rsa-sha2-512"],  # fall back to legacy RSA
        },
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


# ── Public API ─────────────────────────────────────────────────────────────────

def get_interfaces(device: dict, session_key: bytes) -> dict:
    """Return structured interface data via Genie, TextFSM, or raw CLI."""
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show interfaces", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    with ConnectHandler(**_netmiko_device(device, session_key)) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show interfaces")
    return {"source": source, "data": data}


def get_routing_table(device: dict, session_key: bytes) -> dict:
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show ip route", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    with ConnectHandler(**_netmiko_device(device, session_key)) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show ip route")
    return {"source": source, "data": data}


def get_bgp_neighbors(device: dict, session_key: bytes) -> dict:
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show bgp all neighbors", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    with ConnectHandler(**_netmiko_device(device, session_key)) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show ip bgp neighbors")
    return {"source": source, "data": data}


def get_ospf_neighbors(device: dict, session_key: bytes) -> dict:
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show ip ospf neighbor", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    with ConnectHandler(**_netmiko_device(device, session_key)) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show ip ospf neighbor")
    return {"source": source, "data": data}


def get_arp_table(device: dict, session_key: bytes) -> dict:
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show ip arp", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    with ConnectHandler(**_netmiko_device(device, session_key)) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show ip arp")
    return {"source": source, "data": data}


def get_mac_table(device: dict, session_key: bytes) -> dict:
    if GENIE_AVAILABLE:
        result = _genie_fetch(device, "show mac address-table", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    with ConnectHandler(**_netmiko_device(device, session_key)) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        source, data = _send(conn, "show mac address-table")
    return {"source": source, "data": data}


def run_cli_command(device: dict, command: str, session_key: bytes) -> str:
    """Run an arbitrary CLI command and return raw output."""
    with ConnectHandler(**_netmiko_device(device, session_key)) as conn:
        if device["platform"] not in NO_ENABLE_PLATFORMS:
            conn.enable()
        output = conn.send_command(command, read_timeout=30)
    return output