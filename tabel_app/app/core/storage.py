"""Общее хранилище данных приложения (для всех функций).

Каждая функция (feature) хранит свои данные в отдельной подпапке:
    <рядом с программой>/data/<feature>/...   — редактируемые пользователем данные
    <ресурсы>/features/<feature>/data/...      — значения по умолчанию (зашиты в .exe)
    <ресурсы>/features/<feature>/templates/... — шаблоны только для чтения

Работает и из исходников, и из собранного .exe (PyInstaller).
"""

import json
import os
import shutil
import sys


def _is_frozen():
    return getattr(sys, "frozen", False)


def app_base_dir():
    """Папка рядом с программой (для пользовательских данных)."""
    if _is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    # app/core/storage.py -> core -> app -> tabel_app
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _meipass():
    return getattr(sys, "_MEIPASS", app_base_dir())


def feature_resource_dir(feature, dev_package_dir):
    """Папка ресурсов функции (шаблоны, значения по умолчанию), только для чтения.

    dev_package_dir — путь к пакету функции (из исходников); для .exe ресурсы
    лежат в _MEIPASS/features/<feature>.
    """
    if _is_frozen():
        return os.path.join(_meipass(), "features", feature)
    return dev_package_dir


def feature_data_dir(feature):
    d = os.path.join(app_base_dir(), "data", feature)
    os.makedirs(d, exist_ok=True)
    return d


def _ensure_data_file(feature, dev_package_dir, name):
    target = os.path.join(feature_data_dir(feature), name)
    if not os.path.exists(target):
        default = os.path.join(feature_resource_dir(feature, dev_package_dir), "data", name)
        if os.path.exists(default):
            shutil.copy(default, target)
    return target


def load_json(feature, dev_package_dir, name):
    path = _ensure_data_file(feature, dev_package_dir, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(feature, name, obj):
    path = os.path.join(feature_data_dir(feature), name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def template_path(feature, dev_package_dir, filename):
    return os.path.join(feature_resource_dir(feature, dev_package_dir), "templates", filename)
