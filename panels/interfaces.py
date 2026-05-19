from PyQt6.QtWidgets import QVBoxLayout, QLabel, QTextEdit
from .base import BasePanel, make_table, set_cell
import connector


class InterfacesPanel(BasePanel):
    def __init__(self, parent=None):
        super().__init__("INTERFACES", parent)

    def _build_content(self, layout: QVBoxLayout):
        self.table = make_table([
            "Interface", "Status", "Protocol", "IP Address",
            "Speed", "Duplex", "Description"
        ])
        layout.addWidget(self.table)

        layout.addWidget(QLabel("Raw / Parse Notes:"))
        self.raw = QTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setMaximumHeight(120)
        layout.addWidget(self.raw)

    def _run_fetch(self):
        self._start_worker(connector.get_interfaces, self._device)

    def _on_result(self, data):
        self.table.setRowCount(0)
        self.raw.clear()

        if data["source"] == "raw":
            self.raw.setPlainText(data["data"])
            self.status_message.emit("Raw CLI output (Genie parser unavailable).")
            return

        ifaces = data["data"]
        self.table.setRowCount(len(ifaces))
        for row, (name, info) in enumerate(ifaces.items()):
            oper  = info.get("oper_status", "")
            line  = info.get("line_protocol", "")
            ipv4  = info.get("ipv4", {})
            ip    = next(iter(ipv4.keys()), "") if ipv4 else ""
            speed = info.get("bandwidth", "")
            duplex= info.get("duplex_mode", "")
            desc  = info.get("description", "")
            color = "#10B981" if "up" in oper.lower() else "#EF4444"

            set_cell(self.table, row, 0, name)
            set_cell(self.table, row, 1, oper, color)
            set_cell(self.table, row, 2, line)
            set_cell(self.table, row, 3, ip)
            set_cell(self.table, row, 4, str(speed))
            set_cell(self.table, row, 5, duplex)
            set_cell(self.table, row, 6, desc)

        self.status_message.emit(f"Fetched {len(ifaces)} interfaces.")