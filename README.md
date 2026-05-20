# RemoteIn

A local desktop GUI for querying Cisco and other vendor network devices over SSH.
Built with PyQt6. Runs fully offline — no cloud, no telemetry, no account required.

---

## What it does

RemoteIn lets you connect to network devices and inspect live state across five panels:

| Panel | What it shows |
|---|---|
| **Interfaces** | Interface status, speed, duplex, error counters |
| **Routing** | IP routing table |
| **BGP / OSPF** | BGP and OSPF neighbor state |
| **ARP / MAC** | ARP table and MAC address table |
| **CLI** | Free-form command input with output history |

On Linux/Mac, output is parsed by **Genie** into structured tables.
On Windows, raw CLI output is displayed — this is expected behavior, not a bug.

---

## Supported platforms

| Key | Vendor / OS |
|---|---|
| `ios` | Cisco IOS |
| `iosxe` | Cisco IOS-XE |
| `iosxr` | Cisco IOS-XR |
| `nxos` | Cisco NX-OS |
| `eos` | Arista EOS |
| `junos` | Juniper JunOS |

---

## Requirements

- Python 3.10+
- Network access to target devices over SSH

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/isaacdwlee/switch-router-gui-inspection.git
cd switch-router-gui-inspection

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python main.py
```

> **Linux / Mac only:** To enable structured Genie parsing, also install:
> ```bash
> pip install pyats genie
> ```
> Without these, the app falls back to raw CLI output automatically.

---

## First run

1. Log in with the default credentials: **admin / admin**
2. Open **File → Device Manager** and add your first device
3. Select the device from the sidebar
4. Use the tabs to inspect interfaces, routing, neighbors, ARP/MAC, or run CLI commands

> Change the default admin password after first login via **Admin → Manage Users**.

---

## Adding a device

| Field | Description |
|---|---|
| Device Name | Friendly label shown in the sidebar |
| Hostname | IP address or FQDN |
| Platform | Select from the supported platform list above |
| SSH Port | Default 22 |
| Username / Password | SSH credentials |
| Enable Password | Required for Cisco devices that need `enable` mode |

---

## User roles

| Role | Access |
|---|---|
| `admin` | Full access — device manager, user manager, all panels |
| `operator` | Read-only panels — no device or user management |

---

## Project structure

```
switch-router-gui-inspection/
├── main.py              # App entry point, login dialog, main window
├── db.py                # SQLite — users and device inventory
├── connector.py         # Genie + Netmiko SSH connection logic
├── device_manager.py    # Device add / edit / delete dialog
├── user_manager.py      # Admin user management dialog
├── styles.py            # QSS dark theme (amber accent)
├── requirements.txt     # Python dependencies
└── panels/
    ├── base.py          # BasePanel — threading, fetch button, error handling
    ├── interfaces.py
    ├── routing.py
    ├── bgp_ospf.py
    ├── arp_mac.py
    └── cli.py
```

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

For architecture details, conventions, and known issues, read [CLAUDE.md](CLAUDE.md)
before making changes — it explains the layering rules, styling system, and roadmap.

---

## License

MIT — see [LICENSE](LICENSE).
