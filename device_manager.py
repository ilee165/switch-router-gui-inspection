from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QSpinBox, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QGroupBox,
    QWidget, QSplitter, QTextEdit, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
import db
from db import decrypt_field
from panels.base import make_table, set_cell, PALETTE


PLATFORMS = ["ios", "iosxe", "iosxr", "nxos", "eos", "junos"]


class DeviceFormWidget(QWidget):
    """Form for adding / editing a device."""
    submitted = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._device_id = None
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        self.name_edit     = QLineEdit(placeholderText="e.g. CORE-SW-01")
        self.host_edit     = QLineEdit(placeholderText="Hostname (e.g. core-sw-01.corp.local)")
        self.ip_edit       = QLineEdit(placeholderText="IP address (e.g. 10.0.0.1)")
        self.platform_box  = QComboBox()
        self.platform_box.addItems(PLATFORMS)
        self.port_spin     = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        self.user_edit     = QLineEdit(placeholderText="SSH username")
        self.pass_edit     = QLineEdit(placeholderText="SSH password")
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.enable_edit   = QLineEdit(placeholderText="Enable password (if required)")
        self.enable_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.notes_edit    = QTextEdit()
        self.notes_edit.setMaximumHeight(60)
        self.notes_edit.setPlaceholderText("Optional notes...")

        layout.addRow("Device Name", self.name_edit)
        layout.addRow("Hostname", self.host_edit)
        layout.addRow("IP Address", self.ip_edit)
        layout.addRow("Platform", self.platform_box)
        layout.addRow("SSH Port", self.port_spin)
        layout.addRow("Username", self.user_edit)
        layout.addRow("Password", self.pass_edit)
        layout.addRow("Enable Pass", self.enable_edit)
        layout.addRow("Notes", self.notes_edit)

        btn_row = QHBoxLayout()
        self.save_btn  = QPushButton("SAVE DEVICE")
        self.save_btn.setObjectName("primaryBtn")
        self.clear_btn = QPushButton("CLEAR")
        btn_row.addWidget(self.clear_btn)
        btn_row.addWidget(self.save_btn)
        layout.addRow("", btn_row)

        self.save_btn.clicked.connect(self._on_save)
        self.clear_btn.clicked.connect(self.clear)

    def load_device(self, device: dict, *, session_key: bytes):
        """Populate the form with an existing device record, decrypting credentials.

        session_key is required — omitting it would display raw ciphertext in the
        password fields and risk double-encryption on save.
        """
        self._device_id = device["id"]
        self.name_edit.setText(device["name"])
        self.host_edit.setText(device["hostname"])
        self.ip_edit.setText(device.get("ip_address", ""))
        idx = self.platform_box.findText(device["platform"])
        if idx >= 0:
            self.platform_box.setCurrentIndex(idx)
        self.port_spin.setValue(device["port"])
        self.user_edit.setText(device["username"])
        _pw = decrypt_field(session_key, device["password"])
        self.pass_edit.setText(_pw if _pw is not None else "")
        _ep = decrypt_field(session_key, device.get("enable_pass", ""))
        self.enable_edit.setText(_ep if _ep is not None else "")
        self.notes_edit.setPlainText(device.get("notes", ""))

    def clear(self):
        self._device_id = None
        self.name_edit.clear()
        self.host_edit.clear()
        self.ip_edit.clear()
        self.platform_box.setCurrentIndex(0)
        self.port_spin.setValue(22)
        self.user_edit.clear()
        self.pass_edit.clear()
        self.enable_edit.clear()
        self.notes_edit.clear()

    def _on_save(self):
        name = self.name_edit.text().strip()
        host = self.host_edit.text().strip()
        user = self.user_edit.text().strip()
        pwd  = self.pass_edit.text()
        if not (name and host and user and pwd):
            QMessageBox.warning(self, "Missing Fields",
                                "Name, Hostname, Username, and Password are required.")
            return
        payload = {
            "id":          self._device_id,
            "name":        name,
            "hostname":    host,
            "ip_address":  self.ip_edit.text().strip(),
            "platform":    self.platform_box.currentText(),
            "port":        self.port_spin.value(),
            "username":    user,
            "password":    pwd,
            "enable_pass": self.enable_edit.text(),
            "notes":       self.notes_edit.toPlainText(),
        }
        self.submitted.emit(payload)


class DeviceManagerDialog(QDialog):
    """Full device inventory management window."""

    devices_changed = pyqtSignal()

    def __init__(self, parent=None, *, session_key: bytes):
        super().__init__(parent)
        self._session_key = session_key
        self._current_device_id = None
        self.setWindowTitle("Device Manager")
        self.setMinimumSize(800, 500)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        main = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: device list
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        hdr = QLabel("DEVICE INVENTORY")
        hdr.setObjectName("sectionHeader")
        lv.addWidget(hdr)
        self.list_widget = QListWidget()
        lv.addWidget(self.list_widget)
        del_btn = QPushButton("DELETE SELECTED")
        del_btn.setObjectName("dangerBtn")
        del_btn.clicked.connect(self._delete_device)
        lv.addWidget(del_btn)

        # Right: tab container
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        hdr2 = QLabel("ADD / EDIT DEVICE")
        hdr2.setObjectName("sectionHeader")
        rv.addWidget(hdr2)

        # Tab widget: Details (form) + SSH Keys
        self._tab_widget = QTabWidget()

        # Details tab — existing form
        details_tab = QWidget()
        details_layout = QVBoxLayout(details_tab)
        details_layout.setContentsMargins(0, 8, 0, 0)
        self.form = DeviceFormWidget()
        details_layout.addWidget(self.form)
        details_layout.addStretch()
        self._tab_widget.addTab(details_tab, "Details")

        # SSH Keys tab
        ssh_tab = QWidget()
        ssh_layout = QVBoxLayout(ssh_tab)
        ssh_layout.setContentsMargins(0, 8, 0, 0)

        self._ssh_table = make_table(["Key Type", "Fingerprint", "Added"])
        ssh_layout.addWidget(self._ssh_table)

        self._ssh_empty_label = QLabel("No stored host keys for this device.")
        self._ssh_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ssh_empty_label.setStyleSheet("color: #6B7280;")
        ssh_layout.addWidget(self._ssh_empty_label)
        self._ssh_empty_label.setVisible(False)

        del_key_btn = QPushButton("DELETE SELECTED KEY")
        del_key_btn.setObjectName("dangerBtn")
        del_key_btn.clicked.connect(self._delete_host_key)
        ssh_layout.addWidget(del_key_btn)

        self._tab_widget.addTab(ssh_tab, "SSH Keys")
        rv.addWidget(self._tab_widget)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([300, 500])
        main.addWidget(splitter)

        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.form.submitted.connect(self._save_device)

    def _refresh_list(self):
        self.list_widget.clear()
        self._devices = db.list_devices()
        self._current_device_id = None
        self._ssh_table.setRowCount(0)
        self._ssh_empty_label.setVisible(False)
        self._ssh_table.setVisible(True)
        for d in self._devices:
            item = QListWidgetItem(f"  {d['name']}  [{d['hostname']}]  {d['platform'].upper()}")
            item.setData(Qt.ItemDataRole.UserRole, d["id"])
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item):
        dev_id = item.data(Qt.ItemDataRole.UserRole)
        self._current_device_id = dev_id
        device = db.get_device(dev_id)
        if device:
            self.form.load_device(device, session_key=self._session_key)
            self._load_ssh_keys(dev_id)

    def _load_ssh_keys(self, device_id: int):
        """Populate the SSH Keys tab with stored host keys for the given device.

        Clears the table, fetches rows from the DB, then either shows the
        table rows or the empty-state label. The key ID is stored in column 0
        via UserRole so the Delete action can retrieve it without a second query.

        Error contract: if db.get_device_host_keys raises, show a warning dialog
        and display the empty-state label. Do not crash the dialog.
        """
        self._ssh_table.setRowCount(0)
        try:
            keys = db.get_device_host_keys(device_id=device_id)
        except Exception as e:
            QMessageBox.warning(self, "SSH Keys Error", f"Could not load host keys:\n{e}")
            self._ssh_empty_label.setVisible(True)
            self._ssh_table.setVisible(False)
            return
        if not keys:
            self._ssh_empty_label.setVisible(True)
            self._ssh_table.setVisible(False)
            return
        self._ssh_empty_label.setVisible(False)
        self._ssh_table.setVisible(True)
        self._ssh_table.setRowCount(len(keys))
        for row_idx, key_row in enumerate(keys):
            set_cell(self._ssh_table, row_idx, 0, key_row["key_type"])
            set_cell(self._ssh_table, row_idx, 1, key_row["fingerprint"])
            set_cell(self._ssh_table, row_idx, 2, key_row["added_at"])
            # Store the key primary-key ID in column 0's item via UserRole.
            # This lets _delete_host_key retrieve the correct row ID without
            # needing a second DB query or a separate data structure.
            item = self._ssh_table.item(row_idx, 0)
            item.setData(Qt.ItemDataRole.UserRole, key_row["id"])

    def _delete_host_key(self):
        """Delete the selected host key row after a confirmation dialog.

        Retrieves the key ID from column 0's UserRole data (set by _load_ssh_keys),
        shows a confirmation dialog with the fingerprint, then calls
        db.delete_host_key(key_id=...) and refreshes the table.
        """
        selected_rows = self._ssh_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Select a key row to delete.")
            return
        row = self._ssh_table.currentRow()
        key_id_item = self._ssh_table.item(row, 0)
        if key_id_item is None:
            return
        key_id = key_id_item.data(Qt.ItemDataRole.UserRole)
        fp_item = self._ssh_table.item(row, 1)
        fingerprint = fp_item.text() if fp_item else "?"
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete stored host key?\nFingerprint: {fingerprint}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                db.delete_host_key(key_id=key_id)
            except Exception as e:
                QMessageBox.warning(self, "Delete Error", str(e))
                return
            if self._current_device_id is not None:
                self._load_ssh_keys(self._current_device_id)

    def _save_device(self, payload: dict):
        if payload["id"] is None:
            db.add_device(
                payload["name"], payload["hostname"], payload["ip_address"],
                payload["platform"], payload["port"], payload["username"],
                payload["password"], payload["enable_pass"], payload["notes"],
                session_key=self._session_key
            )
        else:
            db.update_device(
                payload["id"], payload["name"], payload["hostname"], payload["ip_address"],
                payload["platform"], payload["port"], payload["username"],
                payload["password"], payload["enable_pass"], payload["notes"],
                session_key=self._session_key
            )
        self.form.clear()
        self._refresh_list()
        self.devices_changed.emit()

    def _delete_device(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        dev_id = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete device: {item.text().strip()}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_device(dev_id)
            self._refresh_list()
            self.form.clear()
            self.devices_changed.emit()