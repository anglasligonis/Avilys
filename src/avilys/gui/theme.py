"""Light and dark themes. Every colour the window uses comes from here."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QProxyStyle, QStyle

HONEY = "#f5b027"  # logo fill
COMB = "#241c10"   # logo arrow

THEMES = {
    "light": {
        "window": "#ffffff", "panel": "#f7f8fa", "border": "#e1e4e8", "border_strong": "#c9ced5",
        "row_border": "#eef0f3",
        "text": "#1f2328", "muted": "#59616b", "faint": "#8a929b", "placeholder": "#6e7781",
        "hover": "#eef1f4", "pressed": "#e3e7eb", "input": "#ffffff",
        "selection": "#fdf5e3", "filter_selected": "#fbefd4",
        "primary_bg": COMB, "primary_fg": "#ffffff",
        # Darker honey for marks on white (4.2:1); the active tab and focus use it.
        "accent": "#b06d00", "check": "#b06d00", "check_fg": "#ffffff",
        "danger": "#b42318", "track": "#e6e9ed", "icon": "#1f2328",
        "scroll": "#cdd2d8", "scroll_hover": "#a9b0b8",
        # State colours: the mark (dots, bars, icons), then a tint and the text on it
        "downloading": "#c27c08", "downloading_bg": "#fbf0d8", "downloading_fg": "#7d4c00",
        "seeding": "#1f8a43", "seeding_bg": "#e2f3e7", "seeding_fg": "#17612e",
        "paused": "#8c959f", "paused_bg": "#eef0f2", "paused_fg": "#57606a",
        "checking": "#6e56cf", "checking_bg": "#efebfc", "checking_fg": "#5641b0",
        "danger_bg": "#fde8e6", "danger_fg": "#a1201a",
    },
    "dark": {
        "window": "#16171b", "panel": "#1c1e23", "border": "#2c3038", "border_strong": "#3e434c",
        "row_border": "#23262c",
        "text": "#e6e7ea", "muted": "#a3aab4", "faint": "#7f8690", "placeholder": "#8a919b",
        "hover": "#24272d", "pressed": "#2c3037", "input": "#121317",
        "selection": "#2c2618", "filter_selected": "#3a2f17",
        "primary_bg": HONEY, "primary_fg": COMB,
        "accent": HONEY, "check": HONEY, "check_fg": COMB,
        "danger": "#ff8a80", "track": "#2a2e35", "icon": "#e6e7ea",
        "scroll": "#3b4049", "scroll_hover": "#4f5560",
        "downloading": "#e3a52b", "downloading_bg": "#382e18", "downloading_fg": "#f4c868",
        "seeding": "#3fb950", "seeding_bg": "#173222", "seeding_fg": "#6fd88a",
        "paused": "#8b949e", "paused_bg": "#272a30", "paused_fg": "#a3aab4",
        "checking": "#a78bfa", "checking_bg": "#29233f", "checking_fg": "#c4b5fd",
        "danger_bg": "#3b1d1b", "danger_fg": "#ffa198",
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

QToolBar {{ background: {t['panel']}; border: 0; border-bottom: 1px solid {t['border']}; padding: 8px 12px; spacing: 4px; }}
QToolBar::separator {{ background: {t['border']}; width: 1px; margin: 6px 8px; }}
QToolBar QToolButton {{ padding: 6px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: {t['text']}; }}
QToolBar QToolButton:hover {{ background: {t['hover']}; }}
QToolBar QToolButton:pressed {{ background: {t['pressed']}; }}
QToolBar QToolButton#primary {{ padding: 6px 12px; background: {t['primary_bg']}; color: {t['primary_fg']}; border-color: {t['primary_bg']}; font-weight: 500; }}
QToolBar QToolButton#secondary {{ padding: 6px 12px; background: {t['window']}; border-color: {t['border']}; font-weight: 500; }}
QToolBar QToolButton#secondary:hover {{ background: {t['hover']}; }}
QToolBar QLineEdit {{ padding: 6px 8px; min-width: 240px; margin-right: 4px; }}
QLabel#wordmark {{ font-size: 16px; font-weight: 600; padding: 0 14px 0 6px; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{ background: {t['input']}; color: {t['text']}; border: 1px solid {t['border_strong']}; border-radius: 6px; padding: 5px 8px; selection-background-color: {t['filter_selected']}; selection-color: {t['text']}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {t['accent']}; }}
QLineEdit:read-only {{ background: {t['panel']}; }}
QComboBox QAbstractItemView {{ background: {t['window']}; border: 1px solid {t['border']}; selection-background-color: {t['hover']}; selection-color: {t['text']}; outline: 0; }}

QPushButton {{ background: {t['window']}; color: {t['text']}; border: 1px solid {t['border_strong']}; border-radius: 6px; padding: 6px 14px; min-height: 18px; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:pressed {{ background: {t['pressed']}; }}
QPushButton:focus {{ border-color: {t['accent']}; }}
QPushButton:default {{ background: {t['primary_bg']}; color: {t['primary_fg']}; border-color: {t['primary_bg']}; font-weight: 500; }}
QPushButton:disabled {{ color: {t['faint']}; border-color: {t['border']}; }}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}

QWidget#sidebar {{ background: {t['panel']}; border-right: 1px solid {t['border']}; }}
QListWidget#filters {{ background: transparent; border: 0; padding: 0 8px; outline: 0; }}
QLabel#section {{ color: {t['muted']}; font-size: 11px; font-weight: 600; padding: 14px 18px 6px; }}

QTableView, QTreeView, QListView {{ background: {t['window']}; border: 0; gridline-color: {t['row_border']}; selection-background-color: {t['selection']}; selection-color: {t['text']}; outline: 0; }}
QTableView::item {{ border-bottom: 1px solid {t['row_border']}; padding: 0 6px; }}
QTreeView::item {{ padding: 3px 0; }}
QHeaderView {{ background: {t['window']}; }}
QHeaderView::section {{ background: {t['window']}; color: {t['muted']}; border: 0; border-bottom: 1px solid {t['border']}; padding: 7px 8px; font-weight: 500; }}

QTabWidget::pane {{ border: 0; border-top: 1px solid {t['row_border']}; }}
QTabBar {{ background: {t['window']}; qproperty-drawBase: 0; }}
QTabBar::tab {{ padding: 9px 12px; margin: 0 2px; color: {t['muted']}; border: 0; border-bottom: 2px solid transparent; background: {t['window']}; }}
QTabBar::tab:hover {{ color: {t['text']}; }}
QTabBar::tab:selected {{ color: {t['text']}; font-weight: 600; border-bottom: 2px solid {t['accent']}; }}

QLabel {{ background: transparent; }}
QLabel[role="muted"] {{ color: {t['muted']}; }}
QLabel[role="strong"] {{ color: {t['text']}; font-weight: 500; }}
QLabel[role="title"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="warning"] {{ color: {t['danger']}; }}
QStatusBar QLabel[role="warning"] {{ color: {t['danger']}; }}
QStatusBar QLabel[role="good"] {{ color: {t['seeding']}; }}
QFrame[role="rule"] {{ color: {t['border']}; background: {t['border']}; max-height: 1px; border: 0; }}
QFrame[role="vrule"] {{ background: {t['border']}; min-width: 1px; max-width: 1px; min-height: 14px; max-height: 14px; border: 0; }}

QStatusBar {{ background: {t['panel']}; border-top: 1px solid {t['border']}; color: {t['muted']}; min-height: 28px; }}
QStatusBar::item {{ border: 0; }}
QStatusBar QLabel {{ color: {t['muted']}; padding: 0 8px; }}
QStatusBar QToolButton {{ border: 0; border-radius: 5px; padding: 3px 8px; color: {t['muted']}; background: transparent; }}
QStatusBar QToolButton:hover {{ background: {t['hover']}; color: {t['text']}; }}
QStatusBar QToolButton:checked {{ background: {t['filter_selected']}; color: {t['text']}; }}

QSplitter::handle {{ background: {t['window']}; border-top: 1px solid {t['border']}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: {t['scroll']}; border-radius: 3px; margin: 2px; }}
QScrollBar::handle:vertical {{ min-height: 32px; }}
QScrollBar::handle:horizontal {{ min-width: 32px; }}
QScrollBar::handle:hover {{ background: {t['scroll_hover']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {t['window']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['hover']}; }}
QMenu::item:disabled {{ color: {t['faint']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 6px; }}
QToolTip {{ background: {t['window']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px 6px; }}
"""


def palette(t: dict) -> QPalette:
    pal = QPalette()
    for role, key in {
        QPalette.Window: "window", QPalette.Base: "window", QPalette.AlternateBase: "panel",
        QPalette.Text: "text", QPalette.WindowText: "text", QPalette.ButtonText: "text",
        QPalette.Button: "panel", QPalette.Highlight: "selection", QPalette.HighlightedText: "text",
        QPalette.ToolTipBase: "window", QPalette.ToolTipText: "text", QPalette.PlaceholderText: "placeholder",
        QPalette.Mid: "border", QPalette.Dark: "border", QPalette.Light: "window", QPalette.Midlight: "panel",
        QPalette.Link: "accent", QPalette.LinkVisited: "accent",
    }.items():
        pal.setColor(role, QColor(t[key]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(t["faint"]))
    return pal


class Style(QProxyStyle):
    """Fusion, with check boxes and radio buttons drawn in the theme's colours
    (a style sheet can only restyle those with image files)."""

    INDICATOR = 16

    def pixelMetric(self, metric, option=None, widget=None):
        if metric in (QStyle.PM_IndicatorWidth, QStyle.PM_IndicatorHeight,
                      QStyle.PM_ExclusiveIndicatorWidth, QStyle.PM_ExclusiveIndicatorHeight):
            return self.INDICATOR
        return super().pixelMetric(metric, option, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        if element in (QStyle.PE_IndicatorCheckBox, QStyle.PE_IndicatorItemViewItemCheck):
            self._check(option, painter)
        elif element == QStyle.PE_IndicatorRadioButton:
            self._radio(option, painter)
        else:
            super().drawPrimitive(element, option, painter, widget)

    @classmethod
    def _box(cls, option) -> QRectF:
        s = cls.INDICATOR
        r = option.rect
        return QRectF(r.x() + (r.width() - s) / 2, r.y() + (r.height() - s) / 2, s, s).adjusted(0.5, 0.5, -0.5, -0.5)

    def _check(self, option, p) -> None:
        t = current
        box = self._box(option)
        enabled = bool(option.state & QStyle.State_Enabled)
        on = bool(option.state & QStyle.State_On)
        partly = bool(option.state & QStyle.State_NoChange)
        p.save()
        p.setRenderHint(p.RenderHint.Antialiasing)
        if on or partly:
            fill = QColor(t["check"])
            if not enabled:
                fill.setAlphaF(0.45)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(box, 4, 4)
            p.setPen(QPen(QColor(t["check_fg"]), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            x, y, w = box.x(), box.y(), box.width()
            if on:
                mark = QPainterPath(QPointF(x + w * 0.26, y + w * 0.52))
                mark.lineTo(QPointF(x + w * 0.43, y + w * 0.69))
                mark.lineTo(QPointF(x + w * 0.75, y + w * 0.34))
                p.drawPath(mark)
            else:
                p.drawLine(QPointF(x + w * 0.28, y + w / 2), QPointF(x + w * 0.72, y + w / 2))
        else:
            hovered = enabled and option.state & QStyle.State_MouseOver
            p.setPen(QPen(QColor(t["accent"] if hovered else t["border_strong"]), 1))
            p.setBrush(QColor(t["input"] if enabled else t["panel"]))
            p.drawRoundedRect(box, 4, 4)
        p.restore()

    def _radio(self, option, p) -> None:
        t = current
        box = self._box(option)
        enabled = bool(option.state & QStyle.State_Enabled)
        p.save()
        p.setRenderHint(p.RenderHint.Antialiasing)
        if option.state & QStyle.State_On:
            fill = QColor(t["check"])
            if not enabled:
                fill.setAlphaF(0.45)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawEllipse(box)
            p.setBrush(QColor(t["check_fg"]))
            c = box.center()
            p.drawEllipse(c, box.width() * 0.19, box.width() * 0.19)
        else:
            hovered = enabled and option.state & QStyle.State_MouseOver
            p.setPen(QPen(QColor(t["accent"] if hovered else t["border_strong"]), 1))
            p.setBrush(QColor(t["input"] if enabled else t["panel"]))
            p.drawEllipse(box)
        p.restore()


def ui_font(base: QFont) -> QFont:
    """The app font with tabular figures, so numbers line up in columns."""
    font = QFont(base)
    try:
        font.setFeature(QFont.Tag("tnum"), 1)  # Qt 6.7+
    except (AttributeError, TypeError):
        pass
    return font


def apply(app, choice: str) -> str:
    """Apply 'system', 'light' or 'dark' to the app; returns the theme used."""
    global current, current_name
    current_name = resolve(choice)
    current = THEMES[current_name]
    app.setPalette(palette(current))
    app.setStyleSheet(stylesheet(current))
    return current_name
