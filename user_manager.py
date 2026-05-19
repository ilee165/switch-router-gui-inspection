"""
user_manager.py - Admin dialog for managing application users.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PyQt6.QtCore import Qt
import db


class UserManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("User Manager")
        self.setMinimumSize(600, 420)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        hdr = QLabel("MANAGE USERS")
        hdr.setObjectName("sectionHeader")
        layout.addWidget(hdr)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "Username", "Role"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        # Add user form
        form_hdr = QLabel("ADD USER")
        form_hdr.setObjectName("sectionHeader")
        layout.addWidget(form_hdr)

        form = QFormLayout()
        self.new_user  = QLineEdit(placeholderText="username")
        self.new_pass  = QLineEdit(placeholderText="password")
        self.new_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_role  = QComboBox()
        self.new_role.addItems(["operator", "admin"])
        form.addRow("Username", self.new_user)
        form.addRow("Password", self.new_pass)
        form.addRow("Role",     self.new_role)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("ADD USER")
        add_btn.setObjectName("primaryBtn")
        add_btn.clicked.connect(self._add_user)
        del_btn = QPushButton("DELETE SELECTED")
        del_btn.setObjectName("dangerBtn")
        del_btn.clicked.connect(self._delete_user)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(add_btn)
        layout.addLayout(btn_row)

    def _refresh(self):
        self.table.setRowCount(0)
        for u in db.list_users():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(u["id"])))
            self.table.setItem(r, 1, QTableWidgetItem(u["username"]))
            self.table.setItem(r, 2, QTableWidgetItem(u["role"]))

    def _add_user(self):
        uname = self.new_user.text().strip()
        pwd   = self.new_pass.text()
        role  = self.new_role.currentText()
        if not uname or not pwd:
            QMessageBox.warning(self, "Missing", "Username and password required.")
            return
        try:
            db.create_user(uname, pwd, role)
            self.new_user.clear(); self.new_pass.clear()
            self._refresh()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _delete_user(self):
        item = self.table.item(self.table.currentRow(), 0)
        if not item:
            return
        uid = int(item.text())
        reply = QMessageBox.question(
            self, "Confirm", f"Delete user ID {uid}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_user(uid)
            self._refresh()