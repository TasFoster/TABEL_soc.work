"""Небольшое общее состояние интерфейса между сеансами (JSON в data/_app).

Хранит мелочи удобства, не относящиеся к доменным данным: пропущенную версию
обновления, последние папки сохранения, последний выбор месяца/года/отделения и т.п.
Ошибки чтения/записи не критичны — функции возвращают значения по умолчанию.
"""

import json
import os

from . import storage

_FEATURE = "_app"
_FILE = "ui_state.json"


def _path():
    return os.path.join(storage.feature_data_dir(_FEATURE), _FILE)


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save(obj):
    try:
        storage.save_json(_FEATURE, _FILE, obj)
    except Exception:  # noqa: BLE001
        pass


def get(key, default=None):
    return load().get(key, default)


def set_key(key, value):
    d = load()
    d[key] = value
    save(d)


# --- авто-обновление --------------------------------------------------------------
def skipped_update():
    return get("skipped_update")


def set_skipped_update(version):
    set_key("skipped_update", version)


# --- память папок/выбора (Фаза 3) -------------------------------------------------
def last_dir(kind="save"):
    """Последняя использованная папка (для filedialog initialdir)."""
    return get(f"last_dir_{kind}") or ""


def set_last_dir(path, kind="save"):
    if path:
        set_key(f"last_dir_{kind}", os.path.dirname(path) if os.path.splitext(path)[1] else path)


# --- память выбора отделения по функции (Фаза 4: автоподстановка) -----------------
def last_dept(feature):
    """Название последнего выбранного отделения для функции (или None)."""
    return get(f"dept_{feature}")


def set_last_dept(feature, name):
    if name:
        set_key(f"dept_{feature}", name)


def dept_index(feature, names, default=0):
    """Индекс запомненного отделения в списке names (или default)."""
    want = last_dept(feature)
    if want and want in names:
        return names.index(want)
    return default
