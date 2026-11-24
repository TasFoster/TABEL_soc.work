"""Общий редактор чек-листов для окон функций."""

import sqlite3
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import checklists, feedback


def add_button(parent, master_window, feature_key, feature_title, **pack_options):
    button = ttk.Button(parent, text="Чек-лист",
                        command=lambda: open_editor(master_window, feature_key, feature_title))
    button.pack(**pack_options)
    return button


def open_editor(master, feature_key, feature_title):
    try:
        saved = checklists.load(feature_key)
    except (OSError, sqlite3.Error, ValueError) as exc:
        messagebox.showerror("Чек-лист", f"Не удалось открыть чек-лист.\n{exc}", parent=master)
        return None
    return ChecklistEditor(master, feature_key, feature_title, saved)


class ChecklistEditor(tk.Toplevel):
    def __init__(self, master, feature_key, feature_title, saved):
        super().__init__(master)
        self.title(f"Чек-лист — {feature_title}")
        self.geometry("600x390")
        self.minsize(470, 275)
        self.transient(master)
        self.feature_key = feature_key
        self.feature_title = feature_title
        self.saved = saved
        self.items = list(saved.items)
        self.version_label = tk.StringVar(master=self)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        self._refresh()
        self.listbox.focus_set()
        self.grab_set()

    def _build(self):
        ttk.Label(self, textvariable=self.version_label).pack(anchor="w", padx=10, pady=(10, 0))
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=8)
        self.listbox = tk.Listbox(frame, exportselection=False)
        scroll_y = ttk.Scrollbar(frame, orient="vertical", command=self.listbox.yview)
        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=self.listbox.xview)
        self.listbox.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.listbox.bind("<<ListboxSelect>>", self._set_selection_actions)
        self.listbox.bind("<Double-Button-1>", lambda event: self._edit_item())
        self.listbox.bind("<Return>", lambda event: self._edit_item())
        self.listbox.bind("<Delete>", lambda event: self._remove_item())

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=10)
        ttk.Button(actions, text="+ Добавить", command=self._add_item).pack(side="left")
        self.edit_button = ttk.Button(actions, text="Изменить", command=self._edit_item)
        self.edit_button.pack(side="left", padx=6)
        self.remove_button = ttk.Button(actions, text="− Удалить", command=self._remove_item)
        self.remove_button.pack(side="left")

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=10, pady=10)
        ttk.Button(footer, text="Закрыть", command=self._close).pack(side="left")
        ttk.Button(footer, text="Отправить разработчику…", command=self._send).pack(side="right")
        ttk.Button(footer, text="Сохранить", command=self._save).pack(side="right", padx=6)

    def _refresh(self, index=None):
        self.listbox.delete(0, "end")
        for number, item in enumerate(self.items, start=1):
            self.listbox.insert("end", f"{number}. {item}")
        if index is not None and self.items:
            index = min(index, len(self.items) - 1)
            self.listbox.selection_set(index)
            self.listbox.activate(index)
            self.listbox.see(index)
        self._set_selection_actions()
        self._update_version_label()

    def _set_selection_actions(self, _event=None):
        state = "normal" if self.listbox.curselection() else "disabled"
        self.edit_button.configure(state=state)
        self.remove_button.configure(state=state)

    def _update_version_label(self):
        pending = " · Есть несохранённые изменения" if tuple(self.items) != self.saved.items else ""
        self.version_label.set(f"Сохранённая версия: {self.saved.version}{pending}")

    def _ask_item(self, title, initial=""):
        answer = simpledialog.askstring(title, "Текст пункта:", initialvalue=initial, parent=self)
        if answer is not None and not answer.strip():
            messagebox.showinfo("Чек-лист", "Введите текст пункта.", parent=self)
        return answer.strip() if answer else ""

    def _add_item(self):
        item = self._ask_item("Добавить пункт")
        if item:
            self.items.append(item)
            self._refresh(len(self.items) - 1)

    def _edit_item(self):
        selection = self.listbox.curselection()
        if selection:
            index = selection[0]
            item = self._ask_item("Изменить пункт", self.items[index])
            if item:
                self.items[index] = item
                self._refresh(index)

    def _remove_item(self):
        selection = self.listbox.curselection()
        if selection:
            index = selection[0]
            del self.items[index]
            self._refresh(index)

    def _save(self):
        try:
            self.saved = checklists.save(self.feature_key, self.items, self.saved.version)
        except (OSError, sqlite3.Error, ValueError) as exc:
            messagebox.showerror("Чек-лист", f"Не удалось сохранить чек-лист.\n{exc}", parent=self)
            return False
        self._update_version_label()
        return True

    def _send(self):
        if self._save():
            dialog = feedback.open_feedback_dialog(
                self, self.feature_title, checklist_message=self.saved.message(self.feature_title))
            self.wait_window(dialog)
            if self.winfo_exists():
                self.grab_set()

    def _close(self):
        if tuple(self.items) != self.saved.items:
            keep = messagebox.askyesnocancel("Чек-лист", "Сохранить изменения перед закрытием?", parent=self)
            if keep is None or (keep and not self._save()):
                return
        self.destroy()
