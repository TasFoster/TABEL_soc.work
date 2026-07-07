"""Представление (View) «Пересмотра» — Tkinter (тонкий слой)."""

import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import FEATURE_TITLE, service
from .service import MONTHS_NOM
from .writer import COLS
from ...core import documents, feedback, ui_state

_KEYS = ("fio", "end")
_TREE_WIDTHS = (360, 150)


class PeresmotrWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title(FEATURE_TITLE)
        self.geometry("640x560")
        self.minsize(560, 460)

        self._rows = []
        today = datetime.date.today()
        self.month_var = tk.StringVar(value=MONTHS_NOM[today.month])
        self.year_var = tk.IntVar(value=today.year)
        self.src_var = tk.StringVar()
        self.info = tk.StringVar(
            value="Выберите отчёт ИПСУ (.xls), укажите месяц/год и нажмите «Найти».")
        self._build()

    def _build(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.LabelFrame(self, text="Период и источник")
        top.pack(fill="x", **pad)
        g = ttk.Frame(top)
        g.pack(fill="x", padx=6, pady=4)
        ttk.Label(g, text="Месяц:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(g, textvariable=self.month_var, state="readonly", width=12,
                     values=list(MONTHS_NOM[1:])).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(g, text="Год:").grid(row=0, column=2, sticky="w")
        tk.Spinbox(g, from_=2020, to=2035, textvariable=self.year_var, width=6).grid(
            row=0, column=3, sticky="w", padx=4)
        s = ttk.Frame(top)
        s.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Label(s, text="Отчёт ИПСУ (.xls):").grid(row=0, column=0, sticky="w")
        ttk.Entry(s, textvariable=self.src_var, width=46).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(s, text="Обзор…", command=self._pick_source).grid(row=0, column=2)
        ttk.Button(s, text="Найти", command=self._find).grid(row=0, column=3, padx=6)
        s.columnconfigure(1, weight=1)

        prev = ttk.LabelFrame(self, text="Заканчивается срок обслуживания")
        prev.pack(fill="both", expand=True, **pad)
        self.tree = ttk.Treeview(prev, columns=_KEYS, show="headings", selectmode="browse")
        for key, head, w in zip(_KEYS, COLS, _TREE_WIDTHS):
            self.tree.heading(key, text=head)
            self.tree.column(key, width=w, anchor="w", stretch=(key == "fio"))
        tsb = ttk.Scrollbar(prev, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        ttk.Label(self, textvariable=self.info, foreground="#555", wraplength=600,
                  justify="left").pack(fill="x", padx=10, pady=(2, 0))
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        self.gen_btn = ttk.Button(bottom, text="Сохранить (.ods)", command=self._generate,
                                  state="disabled")
        self.gen_btn.pack(side="right")
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    def _month_num(self):
        return service.month_num(self.month_var.get()) or datetime.date.today().month

    def _pick_source(self):
        f = filedialog.askopenfilename(
            title="Отчёт по формированию реестра ИПСУ (.xls)",
            initialdir=ui_state.last_dir("open") or None,
            filetypes=[("Excel 97-2003", "*.xls"), ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.src_var.set(f)

    def _find(self):
        path = self.src_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Нет файла", "Укажите отчёт ИПСУ (.xls).")
            return
        try:
            self._rows = service.find_expiring(path, int(self.year_var.get()), self._month_num())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка чтения", str(e))
            return
        self._refresh_tree()
        self.info.set(f"Найдено записей: {len(self._rows)}.")
        self.gen_btn.config(state=("normal" if self._rows else "disabled"))

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self._rows):
            self.tree.insert("", "end", iid=str(i), values=tuple(r.get(k, "") for k in _KEYS))

    def _generate(self):
        if not self._rows:
            messagebox.showwarning("Пусто", "Нет записей для сохранения.")
            return
        year = int(self.year_var.get())
        month = self._month_num()
        default = f"Пересмотр_{MONTHS_NOM[month]}_{year}.ods"
        out = filedialog.asksaveasfilename(
            title="Сохранить как…", defaultextension=".ods", initialfile=default,
            initialdir=ui_state.last_dir("save") or None,
            filetypes=[("OpenDocument Spreadsheet", "*.ods")])
        if not out:
            return
        ui_state.set_last_dir(out, "save")
        ctx = {"title": service.default_title(year, month)}
        self.gen_btn.config(state="disabled")
        self.update_idletasks()
        try:
            service.generate(out, ctx, self._rows)
            documents.save_file("peresmotr", out, {"month": month, "year": year})
        except Exception as e:  # noqa: BLE001
            self.gen_btn.config(state="normal")
            messagebox.showerror("Ошибка формирования", str(e))
            return
        self.gen_btn.config(state="normal")
        self.info.set(f"Готово: {out}")
        if messagebox.askyesno("Готово", f"Файл сохранён:\n{out}\n\nОткрыть?"):
            try:
                os.startfile(out)
            except Exception:  # noqa: BLE001
                pass


def open_peresmotr(master):
    return PeresmotrWindow(master)
