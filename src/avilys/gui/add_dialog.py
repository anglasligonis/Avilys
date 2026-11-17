"""The dialog shown when adding a torrent: where to save it and which files."""

from __future__ import annotations

import shutil
from pathlib import Path

import libtorrent as lt
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from .. import display
from ..engine import params_name
from ..i18n import tr, trn
from . import icons, theme

SKIP, NORMAL = 0, 4  # libtorrent download priorities


def real_files(ti: lt.torrent_info) -> list[int]:
    """File indexes worth showing: everything except libtorrent's padding files."""
    fs = ti.files()
    return [i for i in range(fs.num_files()) if not fs.file_flags(i) & lt.file_storage.flag_pad_file]


def display_path(ti: lt.torrent_info, index: int) -> str:
    """'Album/disc 1/01.flac' -> 'disc 1/01.flac' (the torrent's own folder is implied)."""
    path = ti.files().file_path(index).replace("\\", "/")
    root = ti.name() + "/"
    return path[len(root):] if path.startswith(root) else path


def free_space(path: Path) -> int | None:
    """Free bytes on the drive holding `path`, even if the folder doesn't exist yet."""
    p = Path(path).expanduser()
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


class AddTorrentDialog(QDialog):
    def __init__(self, atp: lt.add_torrent_params, save_path: Path, parent=None, choosing: bool = False):
        """choosing=True: a magnet's file list just arrived; pick its files."""
        super().__init__(parent)
        self.atp = atp
        self.ti = atp.ti
        self.choose_later = False
        self.setWindowTitle(tr("Choose files") if choosing else tr("Add torrent"))
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        name = QLabel(params_name(atp))
        name.setTextFormat(Qt.PlainText)  # the name is the torrent maker's text
        name.setWordWrap(True)
        name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        name.setProperty("role", "title")
        layout.addWidget(name)

        summary = QLabel()
        summary.setProperty("role", "muted")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Save to")))
        self.save_path = QLineEdit(str(save_path))
        self.save_path.setAccessibleName(tr("Save to folder"))
        self.save_path.textChanged.connect(self._update_footer)
        browse = QPushButton(tr("Browse…"))
        browse.setAutoDefault(False)
        browse.clicked.connect(self._browse)
        row.addWidget(self.save_path, 1)
        row.addWidget(browse)
        layout.addLayout(row)

        self.tree: QTreeWidget | None = None
        self.files = real_files(self.ti) if self.ti is not None else []
        self.choose_box: QCheckBox | None = None
        if self.ti is None:
            summary.setText(tr("Magnet link. Avilys gets the file list from other peers once it connects."))
            self.choose_box = QCheckBox(tr("Let me choose files when the file list arrives"))
            self.choose_box.setChecked(True)
        else:
            total = sum(self.ti.files().file_size(i) for i in self.files)
            count = len(self.files)
            summary.setText(trn("{n} file", "{n} files", count) + f" · {display.size(total)}")
        if self.ti is not None and len(self.files) > 1:
            self._build_file_list(layout)
        if self.choose_box is not None:
            layout.addWidget(self.choose_box)

        self.footer = QLabel()
        self.footer.setTextFormat(Qt.PlainText)
        layout.addWidget(self.footer)
        self.dont_ask = QCheckBox(tr("Don't show this again (you can turn it back on in Settings)"))
        layout.addWidget(self.dont_ask)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.add_button = buttons.addButton(tr("Download") if choosing else tr("Add"), QDialogButtonBox.AcceptRole)
        self.add_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_footer()

    def _build_file_list(self, layout: QVBoxLayout) -> None:
        tools = QHBoxLayout()
        for label, state in ((tr("Select all"), Qt.Checked), (tr("Select none"), Qt.Unchecked)):
            b = QPushButton(label)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _=False, s=state: self.set_all(s))
            tools.addWidget(b)
        tools.addStretch(1)
        layout.addLayout(tools)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([tr("File"), tr("Size")])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumHeight(220)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        fs = self.ti.files()
        for i in sorted(self.files, key=lambda i: display_path(self.ti, i).lower()):
            item = QTreeWidgetItem([display_path(self.ti, i), display.size(fs.file_size(i))])
            item.setIcon(0, icons.icon(icons.file_kind(fs.file_path(i), 1), theme.current["muted"]))
            item.setData(0, Qt.UserRole, i)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            self.tree.addTopLevelItem(item)
        self.tree.itemChanged.connect(self._update_footer)
        layout.addWidget(self.tree, 1)

    # -- state ------------------------------------------------------------
    def _items(self):
        if self.tree is None:
            return []
        return [self.tree.topLevelItem(r) for r in range(self.tree.topLevelItemCount())]

    def set_all(self, state) -> None:
        for item in self._items():
            item.setCheckState(0, state)

    def set_checked(self, index: int, checked: bool) -> None:
        for item in self._items():
            if item.data(0, Qt.UserRole) == index:
                item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

    def selected_files(self) -> set[int]:
        if self.tree is None:
            return set(self.files)
        return {it.data(0, Qt.UserRole) for it in self._items() if it.checkState(0) == Qt.Checked}

    def _update_footer(self, *_) -> None:
        free = free_space(Path(self.save_path.text() or "."))
        free_text = tr("{size} free", size=display.size(free)) if free is not None else tr("free space unknown")
        if self.ti is None:
            self.footer.setText(free_text)
            self.footer.setProperty("role", "muted")
            self.add_button.setEnabled(True)
        else:
            fs = self.ti.files()
            chosen = self.selected_files()
            size = sum(fs.file_size(i) for i in chosen)
            text = tr("Selected {size}", size=display.size(size)) + f" · {free_text}"
            short = free is not None and size > free
            if short:
                text += " " + tr("(not enough space)")
            self.footer.setText(text)
            self.footer.setProperty("role", "warning" if short else "muted")
            self.add_button.setEnabled(bool(chosen))
        self.footer.style().unpolish(self.footer)
        self.footer.style().polish(self.footer)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("Save to"), self.save_path.text())
        if path:
            self.save_path.setText(path)

    def result_params(self) -> tuple[lt.add_torrent_params, Path]:
        """The params with file choices applied, and the chosen save folder."""
        self.choose_later = self.choose_box is not None and self.choose_box.isChecked()
        if self.ti is not None and self.tree is not None:
            chosen = self.selected_files()
            self.atp.file_priorities = [
                NORMAL if i in chosen else SKIP for i in range(self.ti.files().num_files())
            ]
        return self.atp, Path(self.save_path.text()).expanduser()
