from __future__ import annotations
import threading
from typing import Callable, Any

from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException


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


def _netmiko_device(device: dict) -> dict:
    """Build Netmiko connection dict from device record."""
    return {
        "device_type":      PLATFORM_MAP.get(device["platform"], "cisco_ios"),
        "host":             device["hostname"],
        "port":             device.get("port", 22),
        "username":         device["username"],
        "password":         device["password"],
        "secret":           device.get("enable_pass", ""),
        "timeout":          15,
        "ssh_strict":       False,  # auto-accept unknown host keys
        "system_host_keys": False,  # don't load system known_hosts file
        "use_keys":         False,  # don't use SSH key files
        "key_file":         None,   # no key file
        "disabled_algorithms": {
            "pubkeys": ["rsa-sha2-256", "rsa-sha2-512"],  # fall back to legacy RSA
        },
    }


def _genie_testbed(device: dict) -> dict:
    """Build minimal pyATS testbed dict for a single device."""
    plat = device["platform"]
    os_map = {"ios": "ios", "iosxe": "iosxe", "iosxr": "iosxr", "nxos": "nxos", "eos": "eos", "junos": "junos"}
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
                        "password": device["password"],
                    },
                    "enable": {
                        "password": device.get("enable_pass", ""),
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


# ── Public API ─────────────────────────────────────────────────────────────────

def run_in_thread(fn: Callable, *args, callback: Callable[[Any, Exception | None], None] = None):
    """Run a blocking network call in a daemon thread; invoke callback(result, error) when done."""
    def _worker():
        try:
            result = fn(*args)
            if callback:
                callback(result, None)
        except Exception as exc:
            if callback:
                callback(None, exc)
    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def get_interfaces(device: dict) -> dict:
    """Return structured interface data via Genie, TextFSM, or raw CLI."""
    if GENIE_AVAILABLE:
        try:
            tb = genie_load(_genie_testbed(device))
            dev = tb.devices[device["name"]]
            dev.connect(log_stdout=False, learn_hostname=True)
            data = dev.parse("show interfaces")
            dev.disconnect()
            return {"source": "genie", "data": data}
        except Exception:
            pass
    with ConnectHandler(**_netmiko_device(device)) as conn:
        conn.enable()
        source, data = _send(conn, "show interfaces")
    return {"source": source, "data": data}


def get_routing_table(device: dict) -> dict:
    if GENIE_AVAILABLE:
        try:
            tb = genie_load(_genie_testbed(device))
            dev = tb.devices[device["name"]]
            dev.connect(log_stdout=False, learn_hostname=True)
            data = dev.parse("show ip route")
            dev.disconnect()
            return {"source": "genie", "data": data}
        except Exception:
            pass
    with ConnectHandler(**_netmiko_device(device)) as conn:
        conn.enable()
        source, data = _send(conn, "show ip route")
    return {"source": source, "data": data}


def get_bgp_neighbors(device: dict) -> dict:
    if GENIE_AVAILABLE:
        try:
            tb = genie_load(_genie_testbed(device))
            dev = tb.devices[device["name"]]
            dev.connect(log_stdout=False, learn_hostname=True)
            data = dev.parse("show bgp all neighbors")
            dev.disconnect()
            return {"source": "genie", "data": data}
        except Exception:
            pass
    with ConnectHandler(**_netmiko_device(device)) as conn:
        conn.enable()
        source, data = _send(conn, "show ip bgp neighbors")
    return {"source": source, "data": data}


def get_ospf_neighbors(device: dict) -> dict:
    if GENIE_AVAILABLE:
        try:
            tb = genie_load(_genie_testbed(device))
            dev = tb.devices[device["name"]]
            dev.connect(log_stdout=False, learn_hostname=True)
            data = dev.parse("show ip ospf neighbor")
            dev.disconnect()
            return {"source": "genie", "data": data}
        except Exception:
            pass
    with ConnectHandler(**_netmiko_device(device)) as conn:
        conn.enable()
        source, data = _send(conn, "show ip ospf neighbor")
    return {"source": source, "data": data}


def get_arp_table(device: dict) -> dict:
    if GENIE_AVAILABLE:
        try:
            tb = genie_load(_genie_testbed(device))
            dev = tb.devices[device["name"]]
            dev.connect(log_stdout=False, learn_hostname=True)
            data = dev.parse("show ip arp")
            dev.disconnect()
            return {"source": "genie", "data": data}
        except Exception:
            pass
    with ConnectHandler(**_netmiko_device(device)) as conn:
        conn.enable()
        source, data = _send(conn, "show ip arp")
    return {"source": source, "data": data}


def get_mac_table(device: dict) -> dict:
    if GENIE_AVAILABLE:
        try:
            tb = genie_load(_genie_testbed(device))
            dev = tb.devices[device["name"]]
            dev.connect(log_stdout=False, learn_hostname=True)
            data = dev.parse("show mac address-table")
            dev.disconnect()
            return {"source": "genie", "data": data}
        except Exception:
            pass
    with ConnectHandler(**_netmiko_device(device)) as conn:
        conn.enable()
        source, data = _send(conn, "show mac address-table")
    return {"source": source, "data": data}


def run_cli_command(device: dict, command: str) -> str:
    """Run an arbitrary CLI command and return raw output."""
    with ConnectHandler(**_netmiko_device(device)) as conn:
        conn.enable()
        output = conn.send_command(command, read_timeout=30)
    return output