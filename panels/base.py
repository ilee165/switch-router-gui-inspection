from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QColor

PALETTE = {"success": "#10B981", "error": "#EF4444", "caution": "#F59E0B"}


# ── Worker thread ──────────────────────────────────────────────────────────────

class FetchWorker(QObject):
    result   = pyqtSignal(object)
    error    = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, fn, *args):
        super().__init__()
        self._fn   = fn
        self._args = args

    def run(self):
        try:
            data = self._fn(*self._args)
            self.result.emit(data)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


# ── Table helpers ──────────────────────────────────────────────────────────────

def make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    return t


def set_cell(table: QTableWidget, row: int, col: int, text: str, color: str | None = None):
    item = QTableWidgetItem(str(text))
    if color:
        item.setForeground(QColor(color))
    table.setItem(row, col, item)


# ── Base panel ─────────────────────────────────────────────────────────────────

class BasePanel(QWidget):
    status_message = pyqtSignal(str)

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._device = None
        self._session_key = None
        self._verifier_fn = None
        self._thread = None
        self._worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        top = QHBoxLayout()
        self.hdr = QLabel(label)
        self.hdr.setObjectName("sectionHeader")
        self.fetch_btn = QPushButton("▶  FETCH")
        self.fetch_btn.setObjectName("primaryBtn")
        self.fetch_btn.clicked.connect(self.fetch)
        self.spinner = QLabel("")
        top.addWidget(self.hdr)
        top.addStretch()
        top.addWidget(self.spinner)
        top.addWidget(self.fetch_btn)
        layout.addLayout(top)

        self._build_content(layout)

    def _build_content(self, layout: QVBoxLayout):
        raise NotImplementedError

    def set_device(self, device: dict | None, session_key: bytes | None = None,
                   verifier_fn=None):
        self._device = device
        self._session_key = session_key
        self._verifier_fn = verifier_fn

    def fetch(self):
        if not self._device:
            self.status_message.emit("No device selected.")
            return
        self.fetch_btn.setEnabled(False)
        self.spinner.setText("⟳ connecting…")
        self._run_fetch()

    def _run_fetch(self):
        raise NotImplementedError

    def _start_worker(self, fn, *args):
        # Prevent double-start: if a fetch is already running, ignore the new
        # request. Without this guard, a rapid double-click creates two concurrent
        # FetchWorker threads; both emit result and both re-enable the Fetch button
        # via _on_done, potentially overwriting each other's table data.
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = QThread()
        self._worker = FetchWorker(fn, *args)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_done)
        self._thread.start()

    def _on_result(self, data):
        raise NotImplementedError

    def _on_error(self, msg: str):
        self.status_message.emit(f"ERROR: {msg}")

    def _on_done(self):
        self.fetch_btn.setEnabled(True)
        self.spinner.setText("")