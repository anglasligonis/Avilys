"""Translations: every piece of text in the code has a Lithuanian version,
and no text reaches the window without going through tr()."""

from __future__ import annotations

import ast
import re
import string
from pathlib import Path

import pytest

from avilys import i18n
from avilys.translations import lt as lithuanian

SRC = Path(i18n.__file__).resolve().parent
MARKERS = {"tr", "N_", "trn"}

# Calls that put text on screen. A plain string handed to one of these would
# stay English, so it must be wrapped in tr() (or listed in NOT_TEXT).
SHOWS_TEXT = {
    "QLabel", "QCheckBox", "QPushButton", "QAction", "QToolBar", "QListWidgetItem", "QTreeWidgetItem",
    "setText", "setToolTip", "setWindowTitle", "setPlaceholderText", "setSpecialValueText", "setSuffix",
    "setAccessibleName", "setTabText", "setHeaderLabels", "setHorizontalHeaderLabels",
    "addAction", "addTab", "addItem", "addRow", "addButton", "showMessage", "notify", "hint",
    "information", "warning", "getMultiLineText", "getExistingDirectory", "getOpenFileName",
    "getOpenFileNames", "log",
}
# Names and symbols that are the same in every language
NOT_TEXT = {"Avilys", "Avilys\n", "avilys  ", " KiB/s", "RC4", "µTP + TCP"}
WORD = re.compile(r"[A-Za-z]{2,}")
IDENTIFIER = re.compile(r"[a-z_]+")       # a stored value such as "system", not text
NOT_SHOWN = {"shortcut", "objectName"}     # keyword arguments that aren't text
TERMINAL = {"cli.py", "display.py"}        # terminal mode stays English


def sources():
    return [p for p in SRC.rglob("*.py") if "translations" not in p.parts]


def call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def text_of(node) -> str | None:
    """A string literal's text; adjacent literals are already joined by the parser."""
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def marked_strings() -> dict[str, tuple[str, bool]]:
    """Every literal passed to tr(), N_() or trn(): text -> (where, is plural)."""
    found = {}
    for path in sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and call_name(node) in MARKERS and node.args):
                continue
            where = f"{path.relative_to(SRC)}:{node.lineno}"
            if call_name(node) == "trn":
                one, many = text_of(node.args[0]), text_of(node.args[1])
                assert one and many, f"{where}: trn() needs two literal strings"
                found[many] = (where, True)
            else:
                text = text_of(node.args[0])
                if text is not None:  # tr(variable) translates text marked elsewhere with N_()
                    found[text] = (where, False)
    return found


def fields(text: str) -> set[str]:
    return {name.split(".")[0].split("[")[0] for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_string_has_a_lithuanian_translation():
    marked = marked_strings()
    assert len(marked) > 200  # the scan really found the window's text
    missing = sorted(f"{where}  {text!r}" for text, (where, _) in marked.items() if text not in lithuanian.STRINGS)
    assert not missing, "not translated:\n" + "\n".join(missing)
    unused = sorted(set(lithuanian.STRINGS) - set(marked))
    assert not unused, f"translations for text no longer in the code: {unused}"

    for text, (where, plural) in marked.items():
        translated = lithuanian.STRINGS[text]
        if plural:
            assert isinstance(translated, list) and len(translated) == 3, f"{where}: {text!r} needs 3 plural forms"
        forms = translated if isinstance(translated, list) else [translated]
        for form in forms:
            assert form.strip(), f"{where}: empty translation of {text!r}"
            assert fields(form) == fields(text), f"{where}: placeholders differ in {text!r} -> {form!r}"
            # Leading and trailing spaces and line breaks matter where text is joined
            assert (form[:1].isspace(), form[-1:].isspace()) == (text[:1].isspace(), text[-1:].isspace()), \
                f"{where}: spacing differs in {text!r}"


def test_no_text_skips_translation():
    """A bare English string (or f-string) given straight to a widget would never be translated."""
    bare = []
    for path in (p for p in sources() if p.name not in TERMINAL):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and call_name(node) in SHOWS_TEXT):
                continue
            for arg in [*node.args, *(k.value for k in node.keywords if k.arg not in NOT_SHOWN)]:
                parts = arg.elts if isinstance(arg, (ast.List, ast.Tuple)) else [arg]
                for part in parts:
                    if isinstance(part, ast.JoinedStr):
                        literal = "".join(v.value for v in part.values if isinstance(v, ast.Constant))
                    else:
                        literal = text_of(part)
                    if literal and literal not in NOT_TEXT and WORD.search(literal) \
                            and not IDENTIFIER.fullmatch(literal):
                        bare.append(f"{path.relative_to(SRC)}:{node.lineno}  {literal!r}")
    assert not bare, "text shown without tr():\n" + "\n".join(bare)


def test_plurals_numbers_and_fallbacks():
    try:
        assert i18n.tr("Settings") == "Settings" and i18n.num(1.5) == "1.5"
        assert i18n.trn("{n} torrent", "{n} torrents", 1) == "1 torrent"
        assert i18n.trn("{n} torrent", "{n} torrents", 5) == "5 torrents"

        assert i18n.set_language("lt") == "lt"
        assert i18n.tr("Settings") == "Nustatymai"
        assert i18n.tr("Port {port}", port=6881) == "Prievadas 6881"
        # Lithuanian has three plural forms: 1, 21… / 2–9, 22… / 0, 10–20, 30…
        got = {n: i18n.trn("{n} torrent", "{n} torrents", n) for n in (0, 1, 2, 9, 10, 11, 12, 21, 22, 30, 101, 111)}
        assert got == {0: "0 torentų", 1: "1 torentas", 2: "2 torentai", 9: "9 torentai", 10: "10 torentų",
                       11: "11 torentų", 12: "12 torentų", 21: "21 torentas", 22: "22 torentai",
                       30: "30 torentų", 101: "101 torentas", 111: "111 torentų"}
        assert i18n.num(1.5) == "1,5"  # decimal comma
        assert i18n.tr("text nobody translated") == "text nobody translated"
        assert i18n.qt_text("Cancel") == "Atsisakyti"

        # "Same as system" follows the system's language, falling back to English
        assert i18n.resolve("system", "lt_LT") == "lt" and i18n.resolve("system", "de_DE") == "en"
        assert i18n.resolve("en", "lt_LT") == "en"
    finally:
        i18n.set_language("en")


def test_window_speaks_lithuanian(tmp_path):
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QDialogButtonBox

    from avilys.gui.app import MainWindow, install_language, make_app
    from avilys.gui.dialogs import SettingsDialog
    from test_gui import gui_config

    app = make_app([])
    try:
        assert install_language(app, "lt") == "lt"
        win = MainWindow(gui_config(tmp_path, language="lt"))
        win.refresh()
        assert win.act_settings.text() == "Nustatymai" and win.act_pause.text() == "Pristabdyti"
        assert win.model.headerData(0, Qt.Horizontal) == "Pavadinimas"
        assert win.filters.item(0).text().startswith("Visi")
        assert win.details.tabText(0) == "Bendra"
        assert win.lbl_port.text().startswith("Prievadas ")
        assert "0 torentų" in win.lbl_counts.text()

        dlg = SettingsDialog(win.cfg)
        assert dlg.windowTitle() == "Nustatymai"
        assert [dlg.tabs.tabText(i).replace("&&", "&") for i in range(dlg.tabs.count())] == \
            ["Bendra", "Ryšys", "Greitis", "Eilė ir skleidimas", "Privatumas"]
        # Qt's own buttons are translated too
        box = dlg.findChild(QDialogButtonBox)
        assert box.button(QDialogButtonBox.Cancel).text() == "Atsisakyti"
        # The language list names each language in that language
        assert [dlg.language.itemText(i) for i in range(dlg.language.count())] == \
            ["Kaip sistemoje", "English", "Lietuvių"]
        assert dlg.result_config().language == "lt"
        dlg.language.setCurrentIndex(dlg.language.findData("en"))
        assert dlg.result_config().language == "en"
        win.quit()
    finally:
        install_language(QApplication.instance(), "en")

