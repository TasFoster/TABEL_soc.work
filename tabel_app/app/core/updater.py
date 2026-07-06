"""Авто-обновление «Табель»: проверка версии онлайн, загрузка установщика, запуск.

Только стандартная библиотека (urllib/json/ssl/hashlib/subprocess/winreg) — без внешних
зависимостей. Сетевой код по образцу `feedback.py` (User-Agent, timeout, HTTPS-контекст).

Канал распространения — публичная папка Яндекс.Диска: там лежат `version.json` (манифест
версий) и установщики обеих сборок. Программа читает манифест, сравнивает версии и, если
есть новее, скачивает установщик и запускает его — установщик Inno обновляет программу
поверх (через мьютекс `TabelAppRunningMutex`). Для portable-копии установщик не запускается
поверх (см. installation_kind / UpdateDialog) — он лишь скачивается.

Перед публикацией укажите YANDEX_PUBLIC_KEY (публичную ссылку на папку Яндекс.Диска).
"""

import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

from .version import APP_VERSION, app_variant

# --- канал обновления -------------------------------------------------------------
UPDATE_CHANNEL = "yandex"
# Публичная ссылка на ПАПКУ Яндекс.Диска с version.json и установщиками.
YANDEX_PUBLIC_KEY = "https://disk.yandex.ru/d/Gb0wzbmbP8rrqw"
MANIFEST_PATH = "/version.json"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_TIMEOUT = 15
_SCHEMA = 1

# Папки установки (совпадают с installer/*.iss) — для определения installed/portable.
_INSTALL_DIRS = {"full": "Tabel", "lite": "Tabel-lite"}
_INNO_APPIDS = {
    "full": "{7F3A2C10-9B4D-4E61-AE12-1F2D3C4B5A60}_is1",
    "lite": "{7F3A2C10-9B4D-4E61-AE12-1F2D3C4B5A61}_is1",
}


class UpdateError(Exception):
    pass


def is_configured():
    """Настроен ли канал обновления (задан публичный ключ или тестовый манифест)."""
    return bool(YANDEX_PUBLIC_KEY) or bool(os.environ.get("TABEL_UPDATE_MANIFEST"))


def variant_key():
    return "full" if app_variant() == "Полная" else "lite"


def current_version():
    return APP_VERSION


# ----------------------------------------------------------------- сравнение версий
def parse_version(s):
    """'1.3.0' / '1.3' / '1.2 (2026-06-21)' -> (1,3,0). Недостающее = 0, дата игнорируется."""
    m = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(s or ""))
    if not m:
        return (0, 0, 0)
    return tuple(int(g) if g else 0 for g in m.groups())


def is_newer(remote, local):
    return parse_version(remote) > parse_version(local)


# ----------------------------------------------------------------- HTTP
def _ctx():
    return ssl.create_default_context()


def _http_get(url, timeout=_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        return r.read()


def _http_get_json(url, timeout=_TIMEOUT):
    return json.loads(_http_get(url, timeout).decode("utf-8"))


# ----------------------------------------------------------------- адаптер Яндекс.Диск
def _yadisk_href(path):
    """Прямая (временная) ссылка на файл в публичной папке Яндекс.Диска (без токена)."""
    if not YANDEX_PUBLIC_KEY:
        raise UpdateError("Не задан YANDEX_PUBLIC_KEY (публичная папка Яндекс.Диска).")
    api = ("https://cloud-api.yandex.net/v1/disk/public/resources/download?"
           + urllib.parse.urlencode({"public_key": YANDEX_PUBLIC_KEY, "path": path}))
    href = _http_get_json(api).get("href")
    if not href:
        raise UpdateError("Яндекс.Диск не вернул ссылку на файл.")
    return href


def _manifest_url():
    # Для локального теста можно задать прямой URL манифеста через переменную окружения.
    env = os.environ.get("TABEL_UPDATE_MANIFEST")
    if env:
        return env
    if UPDATE_CHANNEL == "yandex":
        return _yadisk_href(MANIFEST_PATH)
    raise UpdateError(f"Неизвестный канал обновления: {UPDATE_CHANNEL}")


def _download_url(entry):
    """Прямая ссылка на установщик из записи манифеста."""
    # Если в манифесте уже задан абсолютный url (тест/иной хостинг) — использовать его.
    if entry.get("url"):
        return entry["url"]
    if UPDATE_CHANNEL == "yandex":
        return _yadisk_href(entry["path"])
    raise UpdateError(f"Неизвестный канал обновления: {UPDATE_CHANNEL}")


# ----------------------------------------------------------------- проверка обновления
def check_for_update():
    """{version,date,notes,size,sha256,url} если есть новее, иначе None.

    Бросает при сетевой/форматной ошибке — вызывающий решает, молчать (тихая проверка)
    или показать предупреждение (явная проверка по кнопке)."""
    manifest = _http_get_json(_manifest_url())
    if int(manifest.get("schema", 0)) != _SCHEMA:
        raise UpdateError("Неподдерживаемый формат манифеста обновления.")
    entry = (manifest.get("latest") or {}).get(variant_key())
    if not entry or not is_newer(entry.get("version"), APP_VERSION):
        return None
    return {
        "version": entry.get("version"),
        "date": entry.get("date", ""),
        "notes": entry.get("notes", ""),
        "size": entry.get("size"),
        "sha256": (entry.get("sha256") or "").lower(),
        "url": _download_url(entry),
    }


# ----------------------------------------------------------------- загрузка
def temp_installer_path(version):
    return os.path.join(tempfile.gettempdir(), f"Tabel_update_{variant_key()}_{version}.exe")


def _allow_insecure():
    return os.environ.get("TABEL_UPDATE_INSECURE") == "1"   # только для локального теста


def download(url, dest, progress_cb=None):
    """Скачать файл потоково (с прогрессом) во временный .part, затем атомарно переименовать."""
    if not url.lower().startswith("https://") and not _allow_insecure():
        raise UpdateError("Ссылка на обновление не защищена (не https).")
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    part = dest + ".part"
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ctx()) as r:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(part, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)
    os.replace(part, dest)
    return dest


def verify_sha256(path, expected):
    if not expected:
        return True   # хеш не задан — пропускаем проверку
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected.lower()


# ----------------------------------------------------------------- установка
def run_installer(path):
    """Запустить установщик отдельным (detached) процессом, чтобы он пережил выход приложения."""
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([path], close_fds=True, creationflags=flags)


# ----------------------------------------------------------------- режим установки
def installation_kind():
    """'installed' (через установщик), 'portable' (произвольная папка) или 'source' (из исходников)."""
    if not getattr(sys, "frozen", False):
        return "source"
    exe_dir = os.path.normcase(os.path.dirname(os.path.abspath(sys.executable)))
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        expected = os.path.normcase(os.path.join(local, _INSTALL_DIRS[variant_key()]))
        if exe_dir == expected:
            return "installed"
    return "installed" if _inno_installed() else "portable"


def _inno_installed():
    try:
        import winreg
        key = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\"
               + _INNO_APPIDS[variant_key()])
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            return True
    except OSError:
        return False
