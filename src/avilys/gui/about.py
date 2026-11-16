"""The About window: logo, version, the poem, and credits."""

from __future__ import annotations

import libtorrent as lt
from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from .. import __version__
from ..i18n import N_, tr

POEM_TITLE = "Seven Seas"
POEM_LINES = (
    "Seven seas of fiber under neon rain,",
    "every song on lease, every book on loan.",
    "He drops a magnet in the static, feeds the swarm:",
    "what you can’t keep, you never owned.",
)
POEM_AUTHOR = "by KS"

CREDITS = N_(
    'Built on <a href="https://libtorrent.org">libtorrent</a> and '
    '<a href="https://doc.qt.io/qtforpython/">Qt for Python</a>.<br>'
    'IP Geolocation by <a href="https://db-ip.com">DB-IP</a> (CC BY 4.0). '
    'Flags from <a href="https://github.com/lipis/flag-icons">flag-icons</a> (MIT).'
)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        from .app import logo_pixmap  # here to avoid a circular import

        self.setWindowTitle(tr("About Avilys"))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 18)
        layout.setSpacing(14)

        # Logo, name and version
        head = QHBoxLayout()
        head.setSpacing(14)
        dpr = self.devicePixelRatioF()
        pm = logo_pixmap(round(56 * dpr))
        pm.setDevicePixelRatio(dpr)
        logo = QLabel()
        logo.setPixmap(pm)
        head.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(2)
        title = QLabel("Avilys")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        version = QLabel(tr("Version {version}", version=__version__) + f" · libtorrent {lt.__version__} · Qt {pyside_version}")
        version.setProperty("role", "muted")
        version.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tagline = QLabel(tr("A BitTorrent client. “Avilys” is Lithuanian for beehive."))
        tagline.setProperty("role", "muted")
        names.addWidget(title)
        names.addWidget(version)
        names.addWidget(tagline)
        head.addLayout(names, 1)
        layout.addLayout(head)

        layout.addWidget(self._rule())

        # The poem
        poem_title = QLabel(POEM_TITLE)
        poem_title.setAlignment(Qt.AlignCenter)
        poem_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.poem = QLabel("\n".join(POEM_LINES))
        self.poem.setAlignment(Qt.AlignCenter)
        self.poem.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.poem.setStyleSheet("font-size: 14px; font-style: italic;")
        self.poem.setAccessibleName(tr("Poem: {title}, {author}", title=POEM_TITLE, author=POEM_AUTHOR))
        author = QLabel(POEM_AUTHOR)
        author.setAlignment(Qt.AlignCenter)
        author.setProperty("role", "muted")
        layout.addSpacing(4)
        layout.addWidget(poem_title)
        layout.addWidget(self.poem)
        layout.addWidget(author)
        layout.addSpacing(4)

        layout.addWidget(self._rule())

        credits = QLabel(tr(CREDITS))
        credits.setWordWrap(True)
        credits.setOpenExternalLinks(True)
        credits.setProperty("role", "muted")
        credits.setAlignment(Qt.AlignCenter)
        layout.addWidget(credits)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _rule() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setProperty("role", "rule")
        return line
