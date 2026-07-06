"""Логирование ошибок в файл (data/logs/app.log) с ротацией — для диагностики.

В оконном .exe нет консоли, поэтому необработанные исключения иначе теряются. Здесь
настраивается запись в файл и перехват `sys.excepthook`. Окна Tkinter дополнительно
перенаправляют ошибки колбэков сюда (см. shell.py / report_callback_exception).
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import storage

_CONFIGURED = False


def log_path():
    d = os.path.join(storage.app_base_dir(), "data", "logs")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "app.log")


def setup():
    """Идемпотентно настроить файловый лог и перехват необработанных исключений."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True
    try:
        handler = RotatingFileHandler(log_path(), maxBytes=512 * 1024,
                                      backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)

        def _hook(exc_type, exc, tb):
            logging.getLogger("uncaught").error(
                "Необработанное исключение", exc_info=(exc_type, exc, tb))
            sys.__excepthook__(exc_type, exc, tb)
        sys.excepthook = _hook
    except Exception:  # noqa: BLE001 — логирование не должно мешать работе
        pass


def get_logger(name="tabel"):
    return logging.getLogger(name)


def log_exception(msg="Ошибка"):
    """Записать текущее исключение (вызывать из except)."""
    logging.getLogger("tabel").exception(msg)
