import sys
import db
from styles import QSS

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QTabWidget, QSplitter, QStatusBar, QMessageBox, QFrame,
    QMenuBar, QMenu
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction

from device_manager import DeviceManagerDialog
from panels import InterfacesPanel, RoutingPanel, NeighborPanel, ArpMacPanel, CliPanel


# ── Login Dialog ───────────────────────────────────────────────────────────────

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RemoteIn — Login")
        self.setFixedSize(480, 400)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.current_user = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        title = QLabel("REMOTEIN")
        title.setObjectName("loginTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("NETWORK OPERATIONS TOOL")
        sub.setObjectName("loginSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("loginSep")
        layout.addWidget(sep)

        form = QFormLayout()
        form.setSpacing(10)
        self.user_input = QLineEdit(placeholderText="username")
        self.pass_input = QLineEdit(placeholderText="password")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("USER", self.user_input)
        form.addRow("PASS", self.pass_input)
        layout.addLayout(form)

        self.error_lbl = QLabel("")
        self.error_lbl.setObjectName("statusErr")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.error_lbl)

        login_btn = QPushButton("LOGIN")
        login_btn.setObjectName("primaryBtn")
        login_btn.clicked.connect(self._login)
        self.pass_input.returnPressed.connect(self._login)
        layout.addWidget(login_btn)

    def _login(self):
        user = self.user_input.text().strip()
        pwd  = self.pass_input.text()
        result = db.verify_user(user, pwd)
        if result:
            self.current_user = result
            self.accept()
        else:
            self.error_lbl.setText("Invalid credentials.")
            self.pass_input.clear()

    # Allow drag to move frameless window
    def mousePressEvent(self, event):
        self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag_pos"):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()


# ── Main Window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, user: dict):
        super().__init__()
        self._user = user
        self._selected_device = None
        self.setWindowTitle("RemoteIn")
        self.setMinimumSize(1200, 720)
        self._build_menu()
        self._build_ui()
        self._refresh_devices()

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        dev_action = QAction("Device Manager", self)
        dev_action.triggered.connect(self._open_device_manager)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(dev_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        if self._user.get("role") == "admin":
            admin_menu = menu.addMenu("Admin")
            usr_action = QAction("Manage Users", self)
            usr_action.triggered.connect(self._manage_users)
            admin_menu.addAction(usr_action)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QHBoxLayout(central)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ── Left sidebar: device list ──────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        sidebar.setObjectName("sidebar")
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(12, 16, 12, 12)
        sv.setSpacing(8)

        user_lbl = QLabel(f"  ● {self._user['username'].upper()}  [{self._user['role']}]")
        user_lbl.setObjectName("userBadge")
        sv.addWidget(user_lbl)

        hdr = QLabel("DEVICES")
        hdr.setObjectName("sectionHeader")
        sv.addWidget(hdr)

        self.device_list = QListWidget()
        self.device_list.itemClicked.connect(self._on_device_selected)
        sv.addWidget(self.device_list)

        mgr_btn = QPushButton("⊕  MANAGE DEVICES")
        mgr_btn.clicked.connect(self._open_device_manager)
        sv.addWidget(mgr_btn)

        # ── Right: panels ──────────────────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 16, 16, 0)
        rv.setSpacing(8)

        self.device_header = QLabel("SELECT A DEVICE")
        self.device_header.setObjectName("sectionHeader")
        rv.addWidget(self.device_header)

        self.tabs = QTabWidget()
        self.iface_panel   = InterfacesPanel()
        self.route_panel   = RoutingPanel()
        self.neighbor_panel= NeighborPanel()
        self.arpmac_panel  = ArpMacPanel()
        self.cli_panel     = CliPanel()

        for panel in (self.iface_panel, self.route_panel,
                      self.neighbor_panel, self.arpmac_panel, self.cli_panel):
            panel.status_message.connect(self._set_status)

        self.tabs.addTab(self.iface_panel,    "INTERFACES")
        self.tabs.addTab(self.route_panel,    "ROUTING")
        self.tabs.addTab(self.neighbor_panel, "BGP/OSPF")
        self.tabs.addTab(self.arpmac_panel,   "ARP/MAC")
        self.tabs.addTab(self.cli_panel,      "CLI")
        rv.addWidget(self.tabs)

        main.addWidget(sidebar)
        main.addWidget(right)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._set_status("Ready.")

    def _refresh_devices(self):
        self.device_list.clear()
        self._devices = db.list_devices()
        for d in self._devices:
            item = QListWidgetItem(f"  {d['name']}\n  {d['hostname']} · {d['platform'].upper()}")
            item.setData(Qt.ItemDataRole.UserRole, d["id"])
            self.device_list.addItem(item)

    def _on_device_selected(self, item):
        dev_id = item.data(Qt.ItemDataRole.UserRole)
        device = db.get_device(dev_id)
        if not device:
            return
        self._selected_device = device
        self.device_header.setText(
            f"{device['name'].upper()}  ·  {device['hostname']}  ·  {device['platform'].upper()}"
        )
        for panel in (self.iface_panel, self.route_panel,
                      self.neighbor_panel, self.arpmac_panel, self.cli_panel):
            panel.set_device(device)
        self._set_status(f"Device selected: {device['name']} ({device['hostname']})")

    def _open_device_manager(self):
        dlg = DeviceManagerDialog(self)
        dlg.devices_changed.connect(self._refresh_devices)
        dlg.exec()

    def _manage_users(self):
        from user_manager import UserManagerDialog
        dlg = UserManagerDialog(self)
        dlg.exec()

    def _set_status(self, msg: str):
        self.status.showMessage(f"  {msg}")


# ── Bootstrap ──────────────────────────────────────────────────────────────────

def main():
    db.init_db()
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)

    login = LoginDialog()
    if login.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    window = MainWindow(user=login.current_user)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()