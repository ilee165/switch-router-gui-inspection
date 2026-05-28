from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTextEdit
from .base import BasePanel, make_table, set_cell, PALETTE
import connector


BGP_STATE_COLORS = {
    "Established": PALETTE["success"],
    "Idle":        PALETTE["error"],
    "Active":      PALETTE["caution"],
}


class NeighborPanel(BasePanel):
    def __init__(self, parent=None):
        super().__init__("BGP / OSPF NEIGHBORS", parent)

    def _build_content(self, layout: QVBoxLayout):
        proto_row = QHBoxLayout()
        proto_row.addWidget(QLabel("Protocol:"))
        self.proto_combo = QComboBox()
        self.proto_combo.addItems(["BGP", "OSPF"])
        self.proto_combo.currentTextChanged.connect(self._toggle_proto)
        proto_row.addWidget(self.proto_combo)
        proto_row.addStretch()
        layout.addLayout(proto_row)

        self.bgp_table = make_table([
            "Neighbor", "AS", "State", "Router ID", "Remote IP", "VRF"
        ])
        self.ospf_table = make_table([
            "Neighbor ID", "Priority", "State", "Dead Timer", "Interface", "Address"
        ])
        self.ospf_table.hide()
        layout.addWidget(self.bgp_table)
        layout.addWidget(self.ospf_table)

        self.raw = QTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setMaximumHeight(100)
        layout.addWidget(self.raw)

    def _toggle_proto(self, text: str):
        if text == "BGP":
            self.bgp_table.show()
            self.ospf_table.hide()
        else:
            self.bgp_table.hide()
            self.ospf_table.show()

    def _run_fetch(self):
        if self.proto_combo.currentText() == "BGP":
            self._start_worker(connector.get_bgp_neighbors, self._device, self._session_key)
        else:
            self._start_worker(connector.get_ospf_neighbors, self._device, self._session_key)

    def _on_result(self, data):
        self.raw.clear()

        if data["source"] == "raw":
            self.raw.setPlainText(data["data"])
            return

        if data["source"] == "textfsm":
            if self.proto_combo.currentText() == "BGP":
                self._populate_bgp_textfsm(data["data"])
            else:
                self._populate_ospf_textfsm(data["data"])
            return

        # Genie path
        if self.proto_combo.currentText() == "BGP":
            self._populate_bgp(data["data"])
        else:
            self._populate_ospf(data["data"])

    def _populate_bgp_textfsm(self, rows: list):
        self.bgp_table.setRowCount(len(rows))
        for r, nbr in enumerate(rows):
            state = nbr.get("bgp_state", "")
            color = BGP_STATE_COLORS.get(state, None)

            set_cell(self.bgp_table, r, 0, nbr.get("neighbor", ""))
            set_cell(self.bgp_table, r, 1, nbr.get("remote_as", ""))
            set_cell(self.bgp_table, r, 2, state, color)
            set_cell(self.bgp_table, r, 3, nbr.get("remote_router_id", ""))
            set_cell(self.bgp_table, r, 4, nbr.get("remote_ip", ""))
            set_cell(self.bgp_table, r, 5, nbr.get("vrf", "default"))

        self.status_message.emit(f"Fetched {len(rows)} BGP neighbors via TextFSM.")

    def _populate_ospf_textfsm(self, rows: list):
        self.ospf_table.setRowCount(len(rows))
        for r, nbr in enumerate(rows):
            set_cell(self.ospf_table, r, 0, nbr.get("neighbor_id", ""))
            set_cell(self.ospf_table, r, 1, nbr.get("priority", ""))
            set_cell(self.ospf_table, r, 2, nbr.get("state", ""))
            set_cell(self.ospf_table, r, 3, nbr.get("dead_time", ""))
            set_cell(self.ospf_table, r, 4, nbr.get("interface", ""))
            set_cell(self.ospf_table, r, 5, nbr.get("ip_address", ""))

        self.status_message.emit(f"Fetched {len(rows)} OSPF neighbors via TextFSM.")

    def _populate_bgp(self, parsed: dict):
        rows = []
        for vrf_name, vrf in (
            parsed.get("instance", {})
                  .get("default", {})
                  .get("vrf", {})
                  .items()
        ):
            for nbr_ip, nbr in vrf.get("neighbor", {}).items():
                prefixes = (
                    nbr.get("address_family", {})
                       .get("ipv4 unicast", {})
                       .get("prefixes", {})
                       .get("received", "")
                )
                rows.append((
                    nbr_ip,
                    str(nbr.get("remote_as", "")),
                    nbr.get("session_state", ""),
                    nbr.get("router_id", ""),
                    nbr_ip,
                    vrf_name,
                ))

        self.bgp_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                color = BGP_STATE_COLORS.get(row[2], None) if c == 2 else None
                set_cell(self.bgp_table, r, c, val, color)

        self.status_message.emit(f"Fetched {len(rows)} BGP neighbors.")

    def _populate_ospf(self, parsed: dict):
        rows = []
        for pid, pdata in parsed.get("ospf_neighbor_detail", {}).get("instance", {}).items():
            for area, adata in pdata.get("areas", {}).items():
                for iface, idata in adata.get("interfaces", {}).items():
                    for nbr_id, nbr in idata.get("neighbors", {}).items():
                        rows.append((
                            nbr_id,
                            str(nbr.get("priority", "")),
                            nbr.get("state", ""),
                            str(nbr.get("dead_time", "")),
                            iface,
                            nbr.get("address", ""),
                        ))

        self.ospf_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                set_cell(self.ospf_table, r, c, val)

        self.status_message.emit(f"Fetched {len(rows)} OSPF neighbors.")