"""Translations. Text in the code is English; `tr()` swaps in the chosen
language from `avilys/translations/<code>.py`.

    tr("Port {port}", port=6881)
    trn("{n} torrent", "{n} torrents", count)      # picks the plural form
    N_("Seeding")                                   # marks text translated later, by tr(variable)
"""

from __future__ import annotations

import importlib

LANGUAGES = {"en": "English", "lt": "Lietuvių"}  # code -> its own name

language = "en"
decimal_point = "."
_strings: dict[str, str | list[str]] = {}
_qt_strings: dict[str, str] = {}
_plural = lambda n: 0 if n == 1 else 1  # noqa: E731


def resolve(choice: str, system_locale: str = "") -> str:
    """'system' -> the language of the system if we have it, else English."""
    if choice in LANGUAGES:
        return choice
    code = system_locale.replace("-", "_").split("_")[0].lower()
    return code if code in LANGUAGES else "en"


def set_language(choice: str, system_locale: str = "") -> str:
    """Switch language; returns the code now in use."""
    global language, decimal_point, _strings, _qt_strings, _plural
    code = resolve(choice, system_locale)
    if code == "en":
        _strings, _qt_strings, _plural, decimal_point = {}, {}, (lambda n: 0 if n == 1 else 1), "."
    else:
        module = importlib.import_module(f"{__package__}.translations.{code}")
        _strings, _qt_strings = module.STRINGS, module.QT_STRINGS
        _plural, decimal_point = module.plural, module.DECIMAL_POINT
    language = code
    return code


def tr(text: str, **values) -> str:
    """The text in the current language, with {placeholders} filled in."""
    out = _strings.get(text, text)
    if isinstance(out, list):  # a plural entry used without a number
        out = out[-1]
    return out.format(**values) if values else out


def trn(one: str, many: str, n: int, **values) -> str:
    """Singular or plural for n; {n} is filled in."""
    forms = _strings.get(many)
    if isinstance(forms, list):
        out = forms[min(_plural(n), len(forms) - 1)]
    else:
        out = one if n == 1 else many
    return out.format(n=n, **values)


def qt_text(source: str) -> str | None:
    """Qt's own text (button labels, the file dialog) in the current language."""
    return _qt_strings.get(source)


def N_(text: str) -> str:
    """Marks text for translation without translating it here."""
    return text


def num(value: float, digits: int = 1) -> str:
    """A number with the language's decimal separator: 1.5 or 1,5."""
    out = f"{value:.{digits}f}"
    return out if decimal_point == "." else out.replace(".", decimal_point)
