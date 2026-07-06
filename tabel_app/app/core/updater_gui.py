"""Диалог обновления приложения (UI поверх app/core/updater.py).

Сетевые операции (проверка/загрузка) выполняются в фоновом потоке; виджеты трогаются
ТОЛЬКО из главного потока через `widget.after(0, ...)` (Tkinter не потокобезопасен).
"""

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import ui_state, updater


def check_explicit(master):
    """Явная проверка по кнопке: показывает ход/итог (включая «обновлений нет»/ошибку)."""
    if not updater.is_configured():
        messagebox.showinfo(
            "Обновления",
            "Авто-обновление пока не настроено.\nОно заработает после подключения источника обновлений.")
        return

    def work():
        try:
            info, err = updater.check_for_update(), None
        except Exception as e:  # noqa: BLE001
            info, err = None, e
        master.after(0, lambda: _explicit_result(master, info, err))
    threading.Thread(target=work, daemon=True).start()


def _explicit_result(master, info, err):
    if err is not None:
        messagebox.showwarning("Не удалось проверить",
                               "Нет связи с сервером обновлений. Попробуйте позже.")
        return
    if not info:
        messagebox.showinfo("Обновлений нет",
                            f"У вас установлена последняя версия ({updater.current_version()}).")
        return
    UpdateDialog(master, info)


def check_silent(master, skip_version=None):
    """Тихая проверка при запуске: молча при ошибке/оффлайне; диалог только если есть новее."""
    if not updater.is_configured():
        return   # канал обновления не настроен — тихо ничего не делаем

    def work():
        try:
            info = updater.check_for_update()
        except Exception:  # noqa: BLE001
            info = None
        if info and info.get("version") != skip_version:
            master.after(0, lambda: UpdateDialog(master, info))
    threading.Thread(target=work, daemon=True).start()


class UpdateDialog(tk.Toplevel):
    def __init__(self, master, info):
        super().__init__(master)
        self.info = info
        self.kind = updater.installation_kind()
        self.title("Обновление программы")
        self.geometry("480x340")
        self.minsize(420, 300)
        self.transient(master)
        self.grab_set()
        self._build()

    def _build(self):
        pad = {"padx": 12, "pady": 6}
        head = f"Доступна новая версия {self.info['version']}"
        if self.info.get("date"):
            head += f" от {self.info['date']}"
        ttk.Label(self, text=head, font=("", 11, "bold")).pack(anchor="w", **pad)

        box = tk.Text(self, height=7, wrap="word")
        box.insert("1.0", self.info.get("notes") or "—")
        box.config(state="disabled")
        box.pack(fill="both", expand=True, padx=12)

        self.status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status, foreground="#555").pack(fill="x", padx=12)
        self.prog = ttk.Progressbar(self, mode="determinate")

        bar = ttk.Frame(self)
        bar.pack(fill="x", **pad)
        if self.kind == "installed":
            self.ok = ttk.Button(bar, text="Обновить сейчас", command=self._update_installed)
        else:
            self.ok = ttk.Button(bar, text="Скачать установщик", command=self._download_portable)
        self.ok.pack(side="right")
        ttk.Button(bar, text="Позже", command=self.destroy).pack(side="right", padx=6)
        ttk.Button(bar, text="Пропустить версию", command=self._skip).pack(side="left")

        if self.kind == "source":
            self.status.set("Запуск из исходников — обновление не требуется.")
            self.ok.config(state="disabled")
        elif self.kind == "portable":
            self.status.set("Портативная копия: установщик будет скачан в «Загрузки».")

    # ---- сценарий установленной версии: скачать -> запустить -> закрыть приложение ----
    def _update_installed(self):
        self._start_download(self._after_installed)

    def _after_installed(self, path):
        self.status.set("Запускаю установку… Программа закроется и обновится.")
        try:
            updater.run_installer(path)
        except Exception as e:  # noqa: BLE001
            self._fail(e)
            return
        # Закрыть приложение, чтобы установщик обновил поверх (мьютекс освободится).
        self.after(400, self._quit_app)

    def _quit_app(self):
        try:
            self.master.destroy()
        except Exception:  # noqa: BLE001
            self.destroy()

    # ---- сценарий portable: только скачать установщик в «Загрузки» ----
    def _download_portable(self):
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        try:
            os.makedirs(downloads, exist_ok=True)
        except Exception:  # noqa: BLE001
            downloads = os.path.expanduser("~")
        dest = os.path.join(downloads,
                            os.path.basename(updater.temp_installer_path(self.info["version"])))
        self._start_download(self._after_portable, dest=dest)

    def _after_portable(self, path):
        self.status.set("Готово.")
        messagebox.showinfo(
            "Установщик скачан",
            f"Установщик сохранён:\n{path}\n\nЗакройте программу и запустите его для обновления.")
        self.destroy()

    # ---- общая загрузка с прогрессом (в фоновом потоке) ----
    def _start_download(self, on_done, dest=None):
        self.ok.config(state="disabled")
        self.prog.pack(fill="x", padx=12, pady=(0, 8))
        dest = dest or updater.temp_installer_path(self.info["version"])
        info = self.info

        def progress(done, total):
            def upd():
                if total:
                    self.prog.config(mode="determinate", maximum=total, value=done)
                    self.status.set(f"Загрузка… {done * 100 // total}%")
                else:
                    self.prog.config(mode="indeterminate")
                    self.prog.start(20)
            self.after(0, upd)

        def work():
            try:
                if not (os.path.exists(dest) and updater.verify_sha256(dest, info.get("sha256"))):
                    updater.download(info["url"], dest, progress)
                    if not updater.verify_sha256(dest, info.get("sha256")):
                        raise updater.UpdateError("Контрольная сумма не совпала.")
                self.after(0, lambda: on_done(dest))
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: self._fail(e))
        threading.Thread(target=work, daemon=True).start()

    def _fail(self, e):
        try:
            self.prog.stop()
        except Exception:  # noqa: BLE001
            pass
        self.status.set("")
        messagebox.showerror("Ошибка обновления", f"Не удалось загрузить обновление:\n{e}")
        self.ok.config(state="normal")

    def _skip(self):
        ui_state.set_skipped_update(self.info["version"])
        self.destroy()
