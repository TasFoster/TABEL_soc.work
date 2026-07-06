"""Версия приложения и тип сборки — для окна «Отзывы…» и авто-обновления.

Единый источник версии — файл `tabel_app/VERSION` (одна строка semver, напр. `1.3.0`).
Из исходников версия читается из этого файла; в собранном one-file .exe файла рядом нет,
поэтому `build.ps1` впечатывает значение в `_EMBEDDED_VERSION` перед сборкой (фолбэк).

APP_VERSION — чистый semver (для сравнения в updater); APP_VERSION_DISPLAY — с датой
(для показа пользователю в окне «Отзывы…»).
"""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))
# core -> app -> tabel_app/VERSION
_VERSION_FILE = os.path.join(_HERE, "..", "..", "VERSION")

# build.ps1 впечатывает сюда значение из VERSION перед сборкой .exe (фолбэк для frozen).
_EMBEDDED_VERSION = "1.3.0"
APP_RELEASE_DATE = "2026-06-22"


def _read_version():
    try:
        with open(_VERSION_FILE, encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:  # noqa: BLE001 — нет файла (frozen) -> фолбэк
        pass
    return _EMBEDDED_VERSION


APP_VERSION = _read_version()
APP_VERSION_DISPLAY = f"{APP_VERSION} ({APP_RELEASE_DATE})"


def app_variant():
    """«Полная» (есть функция «Проезд») или «Лёгкая» (Проезд исключён из сборки)."""
    try:
        import app.features.proezd  # noqa: F401
        return "Полная"
    except Exception:  # noqa: BLE001
        return "Лёгкая"
