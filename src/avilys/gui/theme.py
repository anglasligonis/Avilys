"""Light and dark themes. Every colour the window uses comes from here."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

HONEY = "#f5b027"  # logo fill
COMB = "#241c10"   # logo arrow

THEMES = {
    "light": {
        "window": "#ffffff", "panel": "#f6f8fa", "border": "#d0d7de", "row_border": "#eaeef2",
        "text": "#1f2328", "muted": "#57606a", "placeholder": "#6e7781",
        "hover": "#eef1f4", "input": "#ffffff",
        "selection": "#fdf3dc", "filter_selected": "#f6e3b8",
        "primary_bg": COMB, "primary_fg": "#ffffff",
        # Darker honey for marks on white (4.2:1); bars and the active tab use it.
        "accent": "#b06d00", "danger": "#b42318", "track": "#e1e5ea", "icon": "#1f2328",
        "downloading": "#b06d00", "seeding": "#17612e", "paused": "#8c959f", "checking": "#6e56cf",
    },
    "dark": {
        "window": "#17181c", "panel": "#1e2026", "border": "#30343c", "row_border": "#262a31",
        "text": "#e6e7ea", "muted": "#a2a9b3", "placeholder": "#8a919b",
        "hover": "#262a31", "input": "#121317",
        "selection": "#3a2f17", "filter_selected": "#4a3a17",
        "primary_bg": HONEY, "primary_fg": COMB,
        "accent": HONEY, "danger": "#ff8a80", "track": "#2e333b", "icon": "#e6e7ea",
        "downloading": HONEY, "seeding": "#3fb950", "paused": "#8b949e", "checking": "#a78bfa",
    },
}

# The theme in use; models and painters read colours from it.
current: dict = THEMES["light"]
current_name = "light"


def system_is_dark() -> bool:
    hints = QGuiApplication.styleHints()
    try:
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt older than 6.5: guess from the default palette
        return QGuiApplication.palette().color(QPalette.Window).lightness() < 128


def resolve(choice: str) -> str:
    """'system' -> 'light' or 'dark'."""
    if choice in ("light", "dark"):
        return choice
    return "dark" if system_is_dark() else "light"


def stylesheet(t: dict) -> str:
    return f"""
QMainWindow, QWidget {{ background: {t['window']}; color: {t['text']}; }}
QDialog {{ background: {t['window']}; }}
QToolBar {{ background: {t['panel']}; border: 0; border-bottom: 1px solid {t['border']}; padding: 6px 8px; spacing: 6px; }}
QToolBar QToolButton {{ padding: 5px 10px; border: 1px solid {t['border']}; border-radius: 6px; background: {t['window']}; color: {t['text']}; }}
QToolBar QToolButton:hover {{ background: {t['hover']}; }}
QToolBar QToolButton#primary {{ background: {t['primary_bg']}; color: {t['primary_fg']}; border-color: {t['primary_bg']}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {t['input']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px 8px; }}
QToolBar QLineEdit {{ padding: 5px 8px; min-width: 200px; }}
QPushButton {{ background: {t['window']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 5px 14px; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:default {{ background: {t['primary_bg']}; color: {t['primary_fg']}; border-color: {t['primary_bg']}; }}
QWidget#sidebar {{ background: {t['panel']}; border-right: 1px solid {t['border']}; }}
QListWidget#filters {{ background: transparent; border: 0; padding: 8px 6px; outline: 0; }}
QListWidget#filters::item {{ padding: 7px 8px; border-radius: 6px; color: {t['text']}; }}
QListWidget#filters::item:selected {{ background: {t['filter_selected']}; color: {t['text']}; font-weight: 600; }}
QTableView, QTreeView {{ background: {t['window']}; border: 0; gridline-color: {t['row_border']}; selection-background-color: {t['selection']}; selection-color: {t['text']}; outline: 0; }}
QTableView::item {{ border-bottom: 1px solid {t['row_border']}; padding: 0 6px; }}
QHeaderView::section {{ background: {t['window']}; color: {t['muted']}; border: 0; border-bottom: 1px solid {t['border']}; padding: 6px 8px; }}
QTabWidget::pane {{ border: 0; border-top: 1px solid {t['border']}; }}
QTabBar {{ background: {t['panel']}; qproperty-drawBase: 0; }}
QTabBar::tab {{ padding: 8px 14px; color: {t['muted']}; border: 0; background: {t['panel']}; }}
QTabBar::tab:selected {{ color: {t['text']}; font-weight: 600; border-bottom: 2px solid {t['accent']}; }}
QLabel {{ background: transparent; }}
QLabel[role="muted"] {{ color: {t['muted']}; }}
QLabel[role="strong"] {{ color: {t['text']}; }}
QLabel[role="warning"] {{ color: {t['danger']}; }}
QStatusBar QLabel[role="warning"] {{ color: {t['danger']}; }}
QStatusBar QLabel[role="good"] {{ color: {t['seeding']}; }}
QFrame[role="rule"] {{ color: {t['border']}; background: {t['border']}; max-height: 1px; border: 0; }}
QStatusBar {{ background: {t['panel']}; border-top: 1px solid {t['border']}; color: {t['muted']}; }}
QStatusBar QLabel {{ color: {t['muted']}; padding: 0 8px; }}
QSplitter::handle {{ background: {t['border']}; }}
QMenu {{ background: {t['window']}; color: {t['text']}; border: 1px solid {t['border']}; }}
QMenu::item:selected {{ background: {t['selection']}; }}
QToolTip {{ background: {t['window']}; color: {t['text']}; border: 1px solid {t['border']}; }}
"""


def palette(t: dict) -> QPalette:
    pal = QPalette()
    for role, key in {
        QPalette.Window: "window", QPalette.Base: "window", QPalette.AlternateBase: "panel",
        QPalette.Text: "text", QPalette.WindowText: "text", QPalette.ButtonText: "text",
        QPalette.Button: "panel", QPalette.Highlight: "selection", QPalette.HighlightedText: "text",
        QPalette.ToolTipBase: "window", QPalette.ToolTipText: "text", QPalette.PlaceholderText: "placeholder",
        QPalette.Mid: "border", QPalette.Dark: "border",
        QPalette.Link: "accent", QPalette.LinkVisited: "accent",
    }.items():
        pal.setColor(role, QColor(t[key]))
    return pal


def apply(app, choice: str) -> str:
    """Apply 'system', 'light' or 'dark' to the app; returns the theme used."""
    global current, current_name
    current_name = resolve(choice)
    current = THEMES[current_name]
    app.setPalette(palette(current))
    app.setStyleSheet(stylesheet(current))
    return current_name
