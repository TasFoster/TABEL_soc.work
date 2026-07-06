"""Главное меню приложения (лаунчер функций) — CustomTkinter (Фаза 6, пилот).

Показывает прокручиваемый список доступных функций; каждая открывается в отдельном окне.
Сами функции лежат в app/features/<имя> и регистрируются в features/registry.py.
Панель сверху: «Справочники», «Сохранённые документы», «Проверить обновления».

Внешний вид — CustomTkinter (светлая тема, под цвет окон функций). Окна функций пока
остаются на ttk/tk; они открываются как отдельные Toplevel и работают с CTk-родителем.
"""

from tkinter import messagebox

import customtkinter as ctk

from .core import ui_state, updater_gui
from .core.clipboard import enable_cyrillic_clipboard
from .core.documents_gui import open_documents
from .features.registry import get_features
from .reference_gui import open_reference

APP_TITLE = "Программа — рабочие функции"

ctk.set_appearance_mode("light")          # под цвет существующих окон функций
ctk.set_default_color_theme("blue")


class Shell(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("640x560")
        self.minsize(560, 440)
        # Копирование/вставка на русской раскладке (для всех окон программы).
        enable_cyrillic_clipboard(self)
        # Ошибки колбэков Tkinter — в лог-файл (data/logs/app.log).
        self.report_callback_exception = self._log_callback_error

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 2))
        ctk.CTkLabel(header, text="Выберите функцию",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkButton(toolbar, text="Справочники", width=120,
                      command=self._open_reference).pack(side="left")
        ctk.CTkButton(toolbar, text="Сохранённые документы", width=190,
                      command=self._open_documents).pack(side="left", padx=6)
        ctk.CTkButton(toolbar, text="Проверить обновления", width=180,
                      command=self._check_updates).pack(side="right")

        cards = ctk.CTkScrollableFrame(self)
        cards.pack(fill="both", expand=True, padx=12, pady=6)

        features = get_features()
        if not features:
            ctk.CTkLabel(cards, text="Функции не найдены.").pack(pady=20)
        for feat in features:
            card = ctk.CTkFrame(cards)
            card.pack(fill="x", pady=6, padx=4)
            ctk.CTkLabel(card, text=feat.title,
                         font=ctk.CTkFont(size=14, weight="bold")).pack(
                anchor="w", padx=12, pady=(8, 0))
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(0, 10))
            ctk.CTkLabel(row, text=feat.description, wraplength=430, justify="left",
                         text_color="gray30").pack(side="left")
            ctk.CTkButton(row, text="Открыть", width=110,
                          command=lambda f=feat: self._open(f)).pack(side="right")

        # Тихая фоновая проверка обновлений вскоре после старта (не мешает при оффлайне).
        self.after(1500, self._silent_update_check)

    def _open(self, feat):
        try:
            win = feat.open(self)
            if win is not None:
                win.transient(self)
                win.focus_set()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка", f"Не удалось открыть «{feat.title}»:\n{e}")

    def _open_documents(self):
        try:
            win = open_documents(self)
            win.transient(self)
            win.focus_set()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка", f"Не удалось открыть архив документов:\n{e}")

    def _open_reference(self):
        try:
            win = open_reference(self)
            win.transient(self)
            win.focus_set()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка", f"Не удалось открыть справочники:\n{e}")

    def _log_callback_error(self, exc, val, tb):
        try:
            import logging
            logging.getLogger("tkinter").error("Ошибка в обработчике интерфейса",
                                               exc_info=(exc, val, tb))
        except Exception:  # noqa: BLE001
            pass

    def _check_updates(self):
        updater_gui.check_explicit(self)

    def _silent_update_check(self):
        try:
            updater_gui.check_silent(self, skip_version=ui_state.skipped_update())
        except Exception:  # noqa: BLE001 — проверка обновлений не должна мешать запуску
            pass


def run():
    Shell().mainloop()
