from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTextEdit
from .base import BasePanel, make_table, set_cell
import connector


class ArpMacPanel(BasePanel):
    def __init__(self, parent=None):
        super().__init__("ARP / MAC TABLE", parent)

    def _build_content(self, layout: QVBoxLayout):
        proto_row = QHBoxLayout()
        proto_row.addWidget(QLabel("Table:"))
        self.proto_combo = QComboBox()
        self.proto_combo.addItems(["ARP", "MAC"])
        self.proto_combo.currentTextChanged.connect(self._toggle)
        proto_row.addWidget(self.proto_combo)
        proto_row.addStretch()
        layout.addLayout(proto_row)

        self.arp_table = make_table([
            "Protocol", "IP Address", "Age", "MAC Address", "Type", "Interface"
        ])
        self.mac_table = make_table(["VLAN", "MAC Address", "Type", "Port"])
        self.mac_table.hide()
        layout.addWidget(self.arp_table)
        layout.addWidget(self.mac_table)

        self.raw = QTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setMaximumHeight(100)
        layout.addWidget(self.raw)

    def _toggle(self, text: str):
        if text == "ARP":
            self.arp_table.show()
            self.mac_table.hide()
        else:
            self.arp_table.hide()
            self.mac_table.show()

    def _run_fetch(self):
        if self.proto_combo.currentText() == "ARP":
            self._start_worker(connector.get_arp_table, self._device, self._session_key)
        else:
            self._start_worker(connector.get_mac_table, self._device, self._session_key)

    def _on_result(self, data):
        self.raw.clear()

        if data["source"] == "raw":
            self.raw.setPlainText(data["data"])
            return

        if data["source"] == "textfsm":
            if self.proto_combo.currentText() == "ARP":
                self._populate_arp_textfsm(data["data"])
            else:
                self._populate_mac_textfsm(data["data"])
            return

        # Genie path
        if self.proto_combo.currentText() == "ARP":
            self._populate_arp(data["data"])
        else:
            self._populate_mac(data["data"])

    def _populate_arp_textfsm(self, rows: list):
        self.arp_table.setRowCount(len(rows))
        for r, entry in enumerate(rows):
            set_cell(self.arp_table, r, 0, entry.get("protocol", ""))
            set_cell(self.arp_table, r, 1, entry.get("ip_address", ""))
            set_cell(self.arp_table, r, 2, entry.get("age", ""))
            set_cell(self.arp_table, r, 3, entry.get("mac_address", ""))
            set_cell(self.arp_table, r, 4, entry.get("type", ""))
            set_cell(self.arp_table, r, 5, entry.get("interface", ""))

        self.status_message.emit(f"Fetched {len(rows)} ARP entries via TextFSM.")

    def _populate_mac_textfsm(self, rows: list):
        self.mac_table.setRowCount(len(rows))
        for r, entry in enumerate(rows):
            set_cell(self.mac_table, r, 0, entry.get("vlan", ""))
            set_cell(self.mac_table, r, 1, entry.get("mac_address", ""))
            set_cell(self.mac_table, r, 2, entry.get("type", ""))
            set_cell(self.mac_table, r, 3, entry.get("port", ""))

        self.status_message.emit(f"Fetched {len(rows)} MAC entries via TextFSM.")

    def _populate_arp(self, parsed: dict):
        rows = []
        for iface, idata in parsed.get("interfaces", {}).items():
            for ip, arp in idata.get("ipv4", {}).get("neighbors", {}).items():
                rows.append((
                    "Internet",
                    ip,
                    str(arp.get("age", "")),
                    arp.get("link_layer_address", ""),
                    arp.get("origin", ""),
                    iface,
                ))

        self.arp_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                set_cell(self.arp_table, r, c, val)

        self.status_message.emit(f"Fetched {len(rows)} ARP entries.")

    def _populate_mac(self, parsed: dict):
        rows = []
        for vlan, vdata in parsed.get("mac_table", {}).get("vlans", {}).items():
            for mac, mdata in vdata.get("mac_addresses", {}).items():
                for iface in mdata.get("interfaces", {}).keys():
                    rows.append((str(vlan), mac, mdata.get("entry_type", ""), iface))

        self.mac_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                set_cell(self.mac_table, r, c, val)

        self.status_message.emit(f"Fetched {len(rows)} MAC entries.")