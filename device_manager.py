from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QSpinBox, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QGroupBox,
    QWidget, QSplitter, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
import db


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

    def load_device(self, device: dict):
        self._device_id = device["id"]
        self.name_edit.setText(device["name"])
        self.host_edit.setText(device["hostname"])
        self.ip_edit.setText(device.get("ip_address", ""))
        idx = self.platform_box.findText(device["platform"])
        if idx >= 0:
            self.platform_box.setCurrentIndex(idx)
        self.port_spin.setValue(device["port"])
        self.user_edit.setText(device["username"])
        self.pass_edit.setText(device["password"])
        self.enable_edit.setText(device.get("enable_pass", ""))
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

    def __init__(self, parent=None):
        super().__init__(parent)
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

        # Right: form
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        hdr2 = QLabel("ADD / EDIT DEVICE")
        hdr2.setObjectName("sectionHeader")
        rv.addWidget(hdr2)
        self.form = DeviceFormWidget()
        rv.addWidget(self.form)
        rv.addStretch()

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([300, 500])
        main.addWidget(splitter)

        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.form.submitted.connect(self._save_device)

    def _refresh_list(self):
        self.list_widget.clear()
        self._devices = db.list_devices()
        for d in self._devices:
            item = QListWidgetItem(f"  {d['name']}  [{d['hostname']}]  {d['platform'].upper()}")
            item.setData(Qt.ItemDataRole.UserRole, d["id"])
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item):
        dev_id = item.data(Qt.ItemDataRole.UserRole)
        device = db.get_device(dev_id)
        if device:
            self.form.load_device(device)

    def _save_device(self, payload: dict):
        if payload["id"] is None:
            db.add_device(
                payload["name"], payload["hostname"], payload["ip_address"],
                payload["platform"], payload["port"], payload["username"],
                payload["password"], payload["enable_pass"], payload["notes"]
            )
        else:
            db.update_device(
                payload["id"], payload["name"], payload["hostname"], payload["ip_address"],
                payload["platform"], payload["port"], payload["username"],
                payload["password"], payload["enable_pass"], payload["notes"]
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