"""Запуск системных программ из обычного Python и из PyInstaller."""

import os
import subprocess
import sys


def system_process_env():
    env = os.environ.copy()
    if sys.platform != "linux" or not getattr(sys, "frozen", False):
        return env
    # PyInstaller добавляет каталог приложения в поиск библиотек.
    # Системные программы должны загружать библиотеки своего дистрибутива.
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is None:
        env.pop("LD_LIBRARY_PATH", None)
    else:
        env["LD_LIBRARY_PATH"] = original
    return env


def open_path(path):
    """Открыть документ или папку в приложении, выбранном пользователем."""
    path = os.path.abspath(path)
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path], env=system_process_env(), close_fds=True)
