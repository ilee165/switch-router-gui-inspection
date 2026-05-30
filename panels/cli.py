from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QTableWidgetItem
)
from PyQt6.QtGui import QFont
from .base import BasePanel, set_cell, make_table
import connector


class CliPanel(BasePanel):
    def __init__(self, parent=None):
        super().__init__("CUSTOM CLI", parent)

    def _build_content(self, layout: QVBoxLayout):
        cmd_row = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Enter CLI command, e.g.  show version")
        self.cmd_input.returnPressed.connect(self.fetch)
        cmd_row.addWidget(self.cmd_input)
        layout.addLayout(cmd_row)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("JetBrains Mono", 12))
        layout.addWidget(self.output)

        hist_hdr = QLabel("HISTORY")
        hist_hdr.setObjectName("sectionHeader")
        layout.addWidget(hist_hdr)

        self.hist_list = make_table(["#", "Command"])
        self.hist_list.setMaximumHeight(100)
        self.hist_list.itemDoubleClicked.connect(self._replay)
        layout.addWidget(self.hist_list)

    def _run_fetch(self):
        cmd = self.cmd_input.text().strip()
        if not cmd:
            self.status_message.emit("Enter a command first.")
            self._on_done()
            return
        self._start_worker(connector.run_cli_command, self._device, cmd, self._session_key, self._verifier_fn)

    def _on_result(self, data: str):
        cmd = self.cmd_input.text().strip()
        self.output.setPlainText(data)

        row = self.hist_list.rowCount()
        self.hist_list.insertRow(row)
        set_cell(self.hist_list, row, 0, str(row + 1))
        set_cell(self.hist_list, row, 1, cmd)

        self.status_message.emit(f"Command executed: {cmd}")

    def _replay(self, item: QTableWidgetItem):
        cmd_item = self.hist_list.item(item.row(), 1)
        if cmd_item:
            self.cmd_input.setText(cmd_item.text())