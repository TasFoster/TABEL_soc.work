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
import queue
import tempfile
from pathlib import Path
from .feedback_mail import make_draft
import threading
import sys
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
from tkinter import filedialog, messagebox, ttk

from .version import APP_VERSION_DISPLAY, app_variant

FEEDBACK_EMAIL = "farcrystas@gmail.com"
CATEGORIES = ("Проблема", "Пожелание", "Доработка", "Вопрос")

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
        return 200 <= resp.status < 300 and json.load(resp).get("success") is True


def _system_info(feature_title):
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = os.environ.get("USERNAME", "?")
    try:
        import platform
        operating_system = platform.platform()
        pc = platform.node() or "?"
    except Exception:  # noqa: BLE001
        operating_system = sys.platform
        pc = os.environ.get("COMPUTERNAME", "?")
    when = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    return {
        "Функция": feature_title or "(главное меню)",
        "Версия": f"{APP_VERSION_DISPLAY}, сборка: {app_variant()}",
        "Операционная система": operating_system,
        "Пользователь/ПК": f"{user} / {pc}",
        "Дата": when,
    }


def open_feedback_dialog(master, feature_title="", *, checklist_message=None):
    return FeedbackDialog(master, feature_title, checklist_message=checklist_message)


def add_button(parent, master_window, feature_title, **pack_opts):
    """Добавить в `parent` кнопку «Отзывы…», открывающую диалог для `master_window`."""
    btn = ttk.Button(parent, text="Отзывы, жалобы и пожелания",
                     command=lambda: open_feedback_dialog(master_window, feature_title))
    btn.pack(**(pack_opts or {"side": "left"}))
    return btn


class FeedbackDialog(tk.Toplevel):
    def __init__(self, master, feature_title="", *, checklist_message=None):
        super().__init__(master)
        self.title("Отзывы, жалобы и пожелания" if checklist_message is None else "Отправка чек-листа")
        self.geometry("560x520")
        self.minsize(480, 440)
        self.transient(master)
        self.grab_set()
        self.feature_title = feature_title
        self.checklist_message = checklist_message
        self.info = _system_info(feature_title)
        self.attachments = []
        self._build()

    def _build(self):
        pad = {"padx": 10, "pady": 6}
        self.cat_var = tk.StringVar(value=CATEGORIES[0])
        self.categories = []
        if self.checklist_message is None:
            cf = ttk.Frame(self)
            cf.pack(fill="x", **pad)
            ttk.Label(cf, text="Тип:").pack(side="left")
            for c in CATEGORIES:
                option = ttk.Radiobutton(cf, text=c, value=c, variable=self.cat_var)
                option.pack(side="left", padx=(6, 0))
                self.categories.append(option)
            ttk.Label(self, text="Опишите подробно:").pack(anchor="w", padx=10)
        else:
            self.cat_var.set("Чек-лист")
            ttk.Label(self, text=self._subject(), wraplength=450).pack(anchor="w", **pad)
        self.text = tk.Text(self, height=6, wrap="word")
        self.text.pack(fill="both", expand=True, padx=10)
        self.text.focus_set()
        if self.checklist_message is not None:
            self.text.insert("1.0", self.checklist_message)
            self.text.configure(state="disabled")
        files = ttk.Frame(self)
        files.pack(fill="x", padx=10)
        self.attach_button = ttk.Button(files, text="Прикрепить файлы…", command=self._attach)
        self.attach_button.pack(side="left")
        ttk.Button(files, text="Убрать выбранные", command=self._remove).pack(side="left", padx=4)
        self.file_list = tk.Listbox(self, height=3, selectmode="extended")
        self.file_list.pack(fill="x", padx=10)
        info_str = "; ".join(f"{k}: {v}" for k, v in self.info.items())
        ttk.Label(self, text="К письму добавится → " + info_str, wraplength=450,
                  foreground="#888").pack(fill="x", padx=10, pady=(4, 0))
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", before=self.text, **pad)
        self.send_button = ttk.Button(bar, text="Отправить", command=self._send)
        self.send_button.pack(side="right")
        ttk.Button(bar, text="Скопировать", command=self._copy).pack(side="right", padx=6)
        ttk.Button(bar, text="Закрыть", command=self.destroy).pack(side="left")

    def _attach(self):
        for path in filedialog.askopenfilenames(parent=self, title="Образцы для разработчика"):
            if path not in self.attachments:
                self.attachments.append(path)
                self.file_list.insert("end", Path(path).name)
        self._update_send_label()

    def _remove(self):
        for index in reversed(self.file_list.curselection()):
            del self.attachments[index]
            self.file_list.delete(index)
        self._update_send_label()

    def _update_send_label(self):
        self.send_button.configure(text="Открыть письмо в почте…" if self.attachments else "Отправить")

    def _open_attached_draft(self):
        try:
            content = make_draft(FEEDBACK_EMAIL, self._subject(), self._body(), self.attachments)
        except OSError as exc:
            messagebox.showerror("Вложения", str(exc), parent=self)
            return
        if os.name == "nt":
            try:
                with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as draft:
                    draft.write(content)
                os.startfile(draft.name)
                messagebox.showinfo("Черновик открыт", "Проверьте письмо и нажмите «Отправить» в почтовой программе.", parent=self)
                return
            except OSError:
                pass
        filename = "Отзыв.eml" if self.checklist_message is None else "Чек-лист.eml"
        target = filedialog.asksaveasfilename(parent=self, title="Сохранить письмо для отправки из почтовой программы",
                                             initialfile=filename, defaultextension=".eml")
        if target:
            try:
                Path(target).write_bytes(content)
                messagebox.showinfo("Черновик сохранён", "Откройте файл в почтовой программе и отправьте письмо.", parent=self)
            except OSError as exc:
                messagebox.showerror("Письмо", str(exc), parent=self)

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
        if self.attachments:
            self._open_attached_draft()
            return
        if not WEB3FORMS_KEY:
            self._open_mailto()
            return

        subject, body = self._subject(), self._body()
        outcome = queue.SimpleQueue()
        self.send_button.configure(state="disabled", text="Отправка…")
        self.attach_button.state(["disabled"])
        self.text.configure(state="disabled")
        for option in self.categories:
            option.state(["disabled"])

        def submit():
            try:
                outcome.put(_post_web3forms(subject, body))
            except Exception:
                outcome.put(False)

        def check_result():
            try:
                success = outcome.get_nowait()
            except queue.Empty:
                self.after(100, check_result)
                return
            if success:
                messagebox.showinfo("Отправлено", "Спасибо! Обращение отправлено.", parent=self)
                self.destroy()
                return
            self.send_button.configure(state="normal", text="Отправить")
            self.attach_button.state(["!disabled"])
            if self.checklist_message is None:
                self.text.configure(state="normal")
            for option in self.categories:
                option.state(["!disabled"])
            if messagebox.askyesno("Не удалось подтвердить отправку",
                                   "Открыть письмо в почтовой программе?", parent=self):
                self._open_mailto()

        threading.Thread(target=submit, daemon=True).start()
        self.after(100, check_result)

    def _open_mailto(self):
        url = "mailto:%s?subject=%s&body=%s" % (
            FEEDBACK_EMAIL,
            urllib.parse.quote(self._subject()),
            urllib.parse.quote(self._body()),
        )
        if self.checklist_message is not None and len(url) > 1900:
            self._open_attached_draft()
            return
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
