"""Окно «Справочники» — единая точка доступа к редакторам общих данных.

Сводит разрозненные редакторы (раньше открывались только изнутри «Табеля»/«Реестра») в
одно место главного меню. Сами редакторы переиспользуются как есть — они пишут в общую
базу (`app.db`), поэтому правки видны всем функциям. Модуль живёт на уровне View (`app/`),
а не в `core`, чтобы не нарушать слой (core не зависит от features).
"""

import tkinter as tk
from tkinter import messagebox, ttk


class ReferenceWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Справочники")
        self.geometry("440x340")
        self.minsize(380, 300)
        self.transient(master)
        self._build()

    def _build(self):
        ttk.Label(self, text="Общие справочники приложения — используются всеми функциями.",
                  wraplength=410, foreground="#555", justify="left").pack(fill="x", padx=12, pady=(12, 8))
        items = [
            ("Отделения и сотрудники", self._open_departments),
            ("Производственный календарь", self._open_calendar),
            ("Реквизиты и подписи", self._open_settings),
            ("Клиенты и группы (Реестр)", self._open_clients),
            ("Экспорт / импорт данных…", self._transfer),
        ]
        for text, cmd in items:
            ttk.Button(self, text=text, command=cmd).pack(fill="x", padx=12, pady=4)
        ttk.Button(self, text="Закрыть", command=self.destroy).pack(pady=(10, 0))

    def _run(self, factory):
        """Открыть редактор-Toplevel и подождать его закрытия; ошибки — в messagebox."""
        try:
            dlg = factory()
            if dlg is not None:
                self.wait_window(dlg)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка", f"Не удалось открыть редактор:\n{e}", parent=self)

    def _open_departments(self):
        def make():
            from .features.timesheet import storage as ts
            from .features.timesheet.gui import DepartmentManager
            return DepartmentManager(self, ts.load_departments(), ts.load_settings())
        self._run(make)

    def _open_calendar(self):
        def make():
            from .features.timesheet import storage as ts
            from .features.timesheet.gui import CalendarDialog
            return CalendarDialog(self, ts.load_calendar())
        self._run(make)

    def _open_settings(self):
        def make():
            from .features.timesheet import storage as ts
            from .features.timesheet.gui import SettingsDialog
            return SettingsDialog(self, ts.load_settings())
        self._run(make)

    def _open_clients(self):
        def make():
            from .features.reestr.gui import ClientsManager
            return ClientsManager(self)
        self._run(make)

    def _transfer(self):
        from .core import db
        from tkinter import filedialog
        import os
        win = tk.Toplevel(self)
        win.title("Экспорт / импорт данных")
        win.geometry("440x170")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, wraplength=410, justify="left",
                  text=("Перенос всех данных между компьютерами одним файлом базы "
                        "(отделения, сотрудники, клиенты, нагрузки, календарь, настройки).")
                  ).pack(fill="x", padx=12, pady=(12, 8))

        def do_export():
            dest = filedialog.asksaveasfilename(parent=win, title="Экспорт данных",
                                                defaultextension=".db", initialfile="Табель_данные.db",
                                                filetypes=[("База данных", "*.db")])
            if not dest:
                return
            try:
                db.export_db(dest)
                messagebox.showinfo("Готово", f"Данные сохранены:\n{dest}", parent=win)
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Ошибка экспорта", str(e), parent=win)

        def do_import():
            src = filedialog.askopenfilename(parent=win, title="Импорт данных",
                                             filetypes=[("База данных", "*.db"), ("Все файлы", "*.*")])
            if not src or not os.path.exists(src):
                return
            if not messagebox.askyesno("Подтверждение",
                                       "Текущие данные будут заменены (создастся резервная копия). Продолжить?",
                                       parent=win):
                return
            try:
                db.import_db(src)
                messagebox.showinfo("Готово",
                                    "Данные импортированы. Перезапустите программу, чтобы изменения вступили в силу.",
                                    parent=win)
                win.destroy()
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Ошибка импорта",
                                     f"Не удалось импортировать (файл не является базой «Табеля»?):\n{e}",
                                     parent=win)

        ttk.Button(win, text="Экспорт данных в файл…", command=do_export).pack(fill="x", padx=12, pady=4)
        ttk.Button(win, text="Импорт данных из файла…", command=do_import).pack(fill="x", padx=12, pady=4)


def open_reference(master):
    return ReferenceWindow(master)
