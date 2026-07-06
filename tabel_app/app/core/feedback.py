"""Окно «Отзывы, жалобы и пожелания» — письмо разработчику.

Отправка БЕЗ паролей/SMTP: формирует готовое письмо и открывает его в почтовой
программе пользователя (mailto). Если клиента нет — кнопка «Скопировать» кладёт
адрес и текст в буфер обмена, пользователь отправляет сам. К письму добавляются
служебные данные (функция, версия, ОС, пользователь, дата) для диагностики.

Кнопку показывает каждое окно функции через add_button(); адрес — FEEDBACK_EMAIL.
"""

import datetime
import getpass
import json
import os
import sys
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
from tkinter import messagebox, ttk

from .version import APP_VERSION_DISPLAY, app_variant

FEEDBACK_EMAIL = "farcrystas@gmail.com"
CATEGORIES = ("Проблема", "Пожелание", "Вопрос")

# Прямая отправка письма из приложения через Web3Forms (без своего сервера, без
# паролей в .exe). Вставьте Access Key с web3forms.com (привязан к FEEDBACK_EMAIL) —
# тогда кнопка «Отправить» шлёт письмо по интернету; если ключа нет или нет сети —
# откроется почтовая программа (mailto) / кнопка «Скопировать».
WEB3FORMS_KEY = "d6a24686-6a1e-44fb-be01-6d8ed29f50f4"
WEB3FORMS_ENDPOINT = "https://api.web3forms.com/submit"


def _post_web3forms(subject, body):
    """Отправить письмо через Web3Forms. True — успех. Бросает при сетевой ошибке."""
    payload = json.dumps({
        "access_key": WEB3FORMS_KEY,
        "subject": subject,
        "from_name": "Табель — обратная связь",
        "message": body,
    }).encode("utf-8")
    req = urllib.request.Request(
        WEB3FORMS_ENDPOINT, data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 # без браузерного User-Agent Web3Forms отвечает 403 (server-side блок)
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return 200 <= resp.status < 300


def _system_info(feature_title):
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = os.environ.get("USERNAME", "?")
    pc = os.environ.get("COMPUTERNAME", "?")
    try:
        import platform
        win = platform.platform()
    except Exception:  # noqa: BLE001
        win = sys.platform
    when = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    return {
        "Функция": feature_title or "(главное меню)",
        "Версия": f"{APP_VERSION_DISPLAY}, сборка: {app_variant()}",
        "Windows": win,
        "Пользователь/ПК": f"{user} / {pc}",
        "Дата": when,
    }


def open_feedback_dialog(master, feature_title=""):
    return FeedbackDialog(master, feature_title)


def add_button(parent, master_window, feature_title, **pack_opts):
    """Добавить в `parent` кнопку «Отзывы…», открывающую диалог для `master_window`."""
    btn = ttk.Button(parent, text="Отзывы, жалобы и пожелания",
                     command=lambda: open_feedback_dialog(master_window, feature_title))
    btn.pack(**(pack_opts or {"side": "left"}))
    return btn


class FeedbackDialog(tk.Toplevel):
    def __init__(self, master, feature_title=""):
        super().__init__(master)
        self.title("Отзывы, жалобы и пожелания")
        self.geometry("560x520")
        self.minsize(480, 440)
        self.transient(master)
        self.grab_set()
        self.feature_title = feature_title
        self.info = _system_info(feature_title)
        self._build()

    def _build(self):
        pad = {"padx": 10, "pady": 6}
        ttk.Label(self, text=("Сообщите о проблеме или предложите нужную функцию — "
                              "письмо уйдёт разработчику."),
                  wraplength=520, foreground="#444").pack(fill="x", **pad)
        cf = ttk.Frame(self)
        cf.pack(fill="x", **pad)
        ttk.Label(cf, text="Тип:").pack(side="left")
        self.cat_var = tk.StringVar(value=CATEGORIES[0])
        for c in CATEGORIES:
            ttk.Radiobutton(cf, text=c, value=c, variable=self.cat_var).pack(side="left", padx=(6, 0))
        ttk.Label(self, text="Опишите подробно:").pack(anchor="w", padx=10)
        self.text = tk.Text(self, height=12, wrap="word")
        self.text.pack(fill="both", expand=True, padx=10)
        self.text.focus_set()
        info_str = "; ".join(f"{k}: {v}" for k, v in self.info.items())
        ttk.Label(self, text="К письму добавится → " + info_str, wraplength=520,
                  foreground="#888").pack(fill="x", padx=10, pady=(4, 0))
        bar = ttk.Frame(self)
        bar.pack(fill="x", **pad)
        ttk.Button(bar, text="Отправить", command=self._send).pack(side="right")
        ttk.Button(bar, text="Скопировать", command=self._copy).pack(side="right", padx=6)
        ttk.Button(bar, text="Закрыть", command=self.destroy).pack(side="left")

    def _subject(self):
        return f"Табель — {self.cat_var.get()} — {self.feature_title or 'общее'}"

    def _body(self):
        head = "\n".join(f"{k}: {v}" for k, v in self.info.items())
        msg = self.text.get("1.0", "end").strip()
        return f"{msg}\n\n----- служебные данные -----\nТип: {self.cat_var.get()}\n{head}\n"

    def _clipboard_text(self):
        return f"Кому: {FEEDBACK_EMAIL}\nТема: {self._subject()}\n\n{self._body()}"

    def _send(self):
        if not self.text.get("1.0", "end").strip():
            messagebox.showinfo("Пусто", "Сначала напишите текст обращения.")
            return
        # Прямая отправка по интернету, если задан ключ Web3Forms.
        if WEB3FORMS_KEY:
            try:
                if _post_web3forms(self._subject(), self._body()):
                    messagebox.showinfo(
                        "Отправлено", "Спасибо! Ваше сообщение отправлено разработчику.")
                    self.destroy()
                    return
            except Exception:  # noqa: BLE001 — нет сети/ошибка сервиса → запасной путь
                pass
            if not messagebox.askyesno(
                "Не удалось отправить",
                "Не получилось отправить через интернет (возможно, нет сети).\n"
                "Открыть письмо в почтовой программе вместо этого?"):
                return
        self._open_mailto()

    def _open_mailto(self):
        url = "mailto:%s?subject=%s&body=%s" % (
            FEEDBACK_EMAIL,
            urllib.parse.quote(self._subject()),
            urllib.parse.quote(self._body()),
        )
        ok = False
        try:
            ok = webbrowser.open(url)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            if messagebox.askyesno(
                "Почта не открылась",
                "Не удалось открыть почтовую программу.\nСкопировать текст письма в буфер "
                f"обмена, чтобы отправить вручную на {FEEDBACK_EMAIL}?"):
                self._copy()

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self._clipboard_text())
        messagebox.showinfo(
            "Скопировано",
            f"Адрес и текст письма скопированы в буфер обмена.\nВставьте в почту и "
            f"отправьте на {FEEDBACK_EMAIL}.")
