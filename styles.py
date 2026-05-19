"""
styles.py - Centralized QSS stylesheet.
Industrial dark theme with amber accent. Clean, dense, utilitarian — built for
network engineers who stare at terminals all day.
"""

QSS = """
/* ── Global ───────────────────────────────────────────────────────────────── */
* {
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 13px;
    color: #D4D0C8;
    outline: none;
}

QMainWindow, QDialog, QWidget {
    background-color: #1A1A1E;
}

/* ── Labels ───────────────────────────────────────────────────────────────── */
QLabel {
    color: #D4D0C8;
    background: transparent;
}
QLabel#sectionHeader {
    font-size: 11px;
    font-weight: bold;
    color: #F59E0B;
    letter-spacing: 2px;
    padding: 4px 0px 2px 0px;
}
QLabel#loginTitle {
    font-size: 22px;
    font-weight: bold;
    color: #F59E0B;
    letter-spacing: 1px;
}
QLabel#loginSubtitle {
    font-size: 11px;
    color: #6B7280;
    letter-spacing: 3px;
}
QLabel#statusOk  { color: #10B981; }
QLabel#statusErr { color: #EF4444; }
QLabel#statusWarn { color: #F59E0B; }

/* ── Line Edits ───────────────────────────────────────────────────────────── */
QLineEdit {
    background: #0D0D0F;
    border: 1px solid #2D2D35;
    border-radius: 3px;
    padding: 6px 10px;
    color: #E5E7EB;
    selection-background-color: #F59E0B;
    selection-color: #000;
}
QLineEdit:focus {
    border: 1px solid #F59E0B;
}
QLineEdit:disabled {
    color: #4B5563;
    background: #111114;
}

/* ── Buttons ──────────────────────────────────────────────────────────────── */
QPushButton {
    background: #2D2D35;
    border: 1px solid #3D3D48;
    border-radius: 3px;
    padding: 7px 16px;
    color: #D4D0C8;
    font-weight: bold;
    letter-spacing: 0.5px;
}
QPushButton:hover {
    background: #3A3A45;
    border-color: #F59E0B;
    color: #F59E0B;
}
QPushButton:pressed {
    background: #1A1A1E;
}
QPushButton#primaryBtn {
    background: #F59E0B;
    color: #0D0D0F;
    border: none;
}
QPushButton#primaryBtn:hover {
    background: #FBBF24;
    color: #000;
}
QPushButton#dangerBtn {
    border-color: #EF4444;
    color: #EF4444;
}
QPushButton#dangerBtn:hover {
    background: #EF4444;
    color: #fff;
}

/* ── List Widget ──────────────────────────────────────────────────────────── */
QListWidget {
    background: #0D0D0F;
    border: 1px solid #2D2D35;
    border-radius: 3px;
    padding: 4px;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 2px;
    border-bottom: 1px solid #1E1E24;
}
QListWidget::item:selected {
    background: #1E2A1A;
    color: #F59E0B;
    border-left: 2px solid #F59E0B;
}
QListWidget::item:hover {
    background: #1E1E28;
}

/* ── Tab Widget ───────────────────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #2D2D35;
    background: #111114;
    border-radius: 3px;
}
QTabBar::tab {
    background: #1A1A1E;
    border: 1px solid #2D2D35;
    border-bottom: none;
    padding: 8px 18px;
    color: #6B7280;
    font-size: 11px;
    letter-spacing: 1px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #111114;
    color: #F59E0B;
    border-top: 2px solid #F59E0B;
}
QTabBar::tab:hover {
    color: #D4D0C8;
}

/* ── Table Widget ─────────────────────────────────────────────────────────── */
QTableWidget {
    background: #0D0D0F;
    border: 1px solid #2D2D35;
    gridline-color: #1E1E24;
    border-radius: 3px;
}
QTableWidget::item {
    padding: 5px 10px;
}
QTableWidget::item:selected {
    background: #1E2A1A;
    color: #F59E0B;
}
QHeaderView::section {
    background: #1A1A1E;
    color: #F59E0B;
    font-size: 10px;
    letter-spacing: 1.5px;
    font-weight: bold;
    padding: 6px 10px;
    border: none;
    border-right: 1px solid #2D2D35;
    border-bottom: 1px solid #2D2D35;
}

/* ── Text Edit (CLI output) ───────────────────────────────────────────────── */
QTextEdit, QPlainTextEdit {
    background: #0A0A0C;
    border: 1px solid #2D2D35;
    border-radius: 3px;
    color: #A3E635;
    font-size: 12px;
    padding: 8px;
    selection-background-color: #F59E0B;
    selection-color: #000;
}

/* ── ComboBox ─────────────────────────────────────────────────────────────── */
QComboBox {
    background: #0D0D0F;
    border: 1px solid #2D2D35;
    border-radius: 3px;
    padding: 6px 10px;
    color: #D4D0C8;
}
QComboBox:focus { border-color: #F59E0B; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #0D0D0F;
    border: 1px solid #F59E0B;
    selection-background-color: #1E2A1A;
    selection-color: #F59E0B;
}

/* ── Scroll bars ──────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #0D0D0F;
    width: 8px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #3D3D48;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #F59E0B; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background: #0D0D0F;
    height: 8px;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #3D3D48;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover { background: #F59E0B; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Splitter ─────────────────────────────────────────────────────────────── */
QSplitter::handle {
    background: #2D2D35;
    width: 2px;
}
QSplitter::handle:hover { background: #F59E0B; }

/* ── Spin box ─────────────────────────────────────────────────────────────── */
QSpinBox {
    background: #0D0D0F;
    border: 1px solid #2D2D35;
    border-radius: 3px;
    padding: 5px 8px;
    color: #D4D0C8;
}
QSpinBox:focus { border-color: #F59E0B; }

/* ── Status bar ───────────────────────────────────────────────────────────── */
QStatusBar {
    background: #0D0D0F;
    border-top: 1px solid #2D2D35;
    color: #6B7280;
    font-size: 11px;
}

/* ── Message box ──────────────────────────────────────────────────────────── */
QMessageBox {
    background: #1A1A1E;
}
QMessageBox QPushButton {
    min-width: 80px;
}

/* ── Group box ────────────────────────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #2D2D35;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 8px;
    color: #6B7280;
    font-size: 10px;
    letter-spacing: 1.5px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #F59E0B;
}

/* ── Menu bar ─────────────────────────────────────────────────────────────── */
QMenuBar {
    background: #0D0D0F;
    color: #D4D0C8;
    padding: 2px;
}
QMenuBar::item:selected {
    background: #1E1E28;
    color: #F59E0B;
}
QMenu {
    background: #1A1A1E;
    border: 1px solid #2D2D35;
    color: #D4D0C8;
}
QMenu::item:selected {
    background: #1E2A1A;
    color: #F59E0B;
}

/* ── Login separator ──────────────────────────────────────────────────────── */
QFrame#loginSep {
    color: #2D2D35;
}

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
QWidget#sidebar {
    background: #111114;
    border-right: 1px solid #2D2D35;
}

/* ── User badge ───────────────────────────────────────────────────────────── */
QLabel#userBadge {
    color: #10B981;
    font-size: 10px;
    letter-spacing: 1px;
}
"""