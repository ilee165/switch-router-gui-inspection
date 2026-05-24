from PyQt6.QtWidgets import QVBoxLayout, QTextEdit
from .base import BasePanel, make_table, set_cell
import connector


PROTO_COLORS = {
    "C": "#10B981",  # Connected
    "S": "#6B7280",  # Static
    "O": "#60A5FA",  # OSPF
    "B": "#F59E0B",  # BGP
    "R": "#A78BFA",  # RIP
    "i": "#34D399",  # IS-IS
}


class RoutingPanel(BasePanel):
    def __init__(self, parent=None):
        super().__init__("ROUTING TABLE", parent)

    def _build_content(self, layout: QVBoxLayout):
        self.table = make_table([
            "Prefix", "Protocol", "Next Hop", "Interface", "Metric", "AD"
        ])
        layout.addWidget(self.table)

        self.raw = QTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setMaximumHeight(120)
        layout.addWidget(self.raw)

    def _run_fetch(self):
        self._start_worker(connector.get_routing_table, self._device)

    def _on_result(self, data):
        self.table.setRowCount(0)
        self.raw.clear()

        if data["source"] == "raw":
            self.raw.setPlainText(data["data"])
            return

        if data["source"] == "textfsm":
            self._populate_textfsm(data["data"])
            return

        # Genie structured path
        vrfs = data["data"].get("vrf", {})
        rows = []
        for vrf_name, vrf_data in vrfs.items():
            routes = (
                vrf_data.get("address_family", {})
                        .get("ipv4", {})
                        .get("routes", {})
            )
            for prefix, pdata in routes.items():
                for route in pdata.get("next_hop", {}).get("next_hop_list", {}).values():
                    rows.append((
                        prefix,
                        pdata.get("source_protocol_codes", ""),
                        route.get("next_hop", ""),
                        route.get("outgoing_interface", ""),
                        str(pdata.get("metric", "")),
                        str(pdata.get("distance", "")),
                    ))

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            proto = row[1]
            color = PROTO_COLORS.get(proto[0] if proto else "", None)
            for c, val in enumerate(row):
                set_cell(self.table, r, c, val, color if c == 1 else None)

        self.status_message.emit(f"Fetched {len(rows)} routes.")

    def _populate_textfsm(self, rows: list):
        self.table.setRowCount(len(rows))
        for r, route in enumerate(rows):
            proto  = route.get("protocol", "")
            color  = PROTO_COLORS.get(proto[0] if proto else "", None)
            prefix = route.get("network", "")
            mask   = route.get("prefix_length", "")
            if mask:
                prefix = f"{prefix}/{mask}"

            set_cell(self.table, r, 0, prefix)
            set_cell(self.table, r, 1, proto, color)
            set_cell(self.table, r, 2, route.get("nexthop_ip", ""))
            set_cell(self.table, r, 3, route.get("nexthop_if", ""))
            set_cell(self.table, r, 4, route.get("metric", ""))
            set_cell(self.table, r, 5, route.get("distance", ""))

        self.status_message.emit(f"Fetched {len(rows)} routes via TextFSM.")