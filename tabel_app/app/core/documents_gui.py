"""Окно «Сохранённые документы» — просмотр архива сформированных файлов из базы.

Поиск по названию, фильтр по функции, сортировка по столбцам, итоги по объёму.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import documents
from .documents import FEATURE_TITLES

_ALL = "Все функции"


class DocumentsWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Сохранённые документы")
        self.geometry("860x500")
        self.minsize(680, 380)
        self._all = []            # список dict из documents.list_documents()
        self._rows = {}           # iid -> (doc_id, filename)
        self._sort = ("created", True)   # (колонка, по убыванию)
        self.search_var = tk.StringVar()
        self.feature_var = tk.StringVar(value=_ALL)
        self.totals_var = tk.StringVar(value="")
        self._build()
        self._reload()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Label(top, text="Поиск:").pack(side="left")
        ent = ttk.Entry(top, textvariable=self.search_var, width=30)
        ent.pack(side="left", padx=(4, 12))
        self.search_var.trace_add("write", lambda *a: self._apply())
        ttk.Label(top, text="Функция:").pack(side="left")
        self.feature_combo = ttk.Combobox(top, textvariable=self.feature_var, state="readonly",
                                           width=22, values=[_ALL] + list(FEATURE_TITLES.values()))
        self.feature_combo.pack(side="left", padx=4)
        self.feature_combo.bind("<<ComboboxSelected>>", lambda e: self._apply())

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=8, pady=6)
        cols = ("feature", "title", "period", "created", "size")
        heads = (("feature", "Функция", 160), ("title", "Документ", 330),
                 ("period", "Период", 130), ("created", "Создан", 140), ("size", "Размер", 80))
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        for k, t, w in heads:
            self.tree.heading(k, text=t, command=lambda c=k: self._sort_by(c))
            self.tree.column(k, width=w, anchor="w" if k in ("feature", "title", "period") else "center")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._open())

        ttk.Label(self, textvariable=self.totals_var, foreground="#777").pack(fill="x", padx=10)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=8)
        ttk.Button(bar, text="Открыть", command=self._open).pack(side="left")
        ttk.Button(bar, text="Сохранить как…", command=self._save_as).pack(side="left", padx=6)
        ttk.Button(bar, text="Удалить", command=self._delete).pack(side="left")
        ttk.Button(bar, text="Обновить", command=self._reload).pack(side="right")

    # ---------------------------------------------------------------- данные
    def _reload(self):
        self._all = documents.list_documents()
        self._apply()

    def _feature_key_by_title(self, title):
        for k, t in FEATURE_TITLES.items():
            if t == title:
                return k
        return None

    def _apply(self):
        text = self.search_var.get().strip().lower()
        feat_filter = self._feature_key_by_title(self.feature_var.get())
        rows = []
        for d in self._all:
            if feat_filter and d.get("feature") != feat_filter:
                continue
            feat_title = FEATURE_TITLES.get(d["feature"], d["feature"])
            title = d.get("title") or d.get("filename") or ""
            period = documents.params_brief(d.get("params"))
            if text and text not in (title.lower() + " " + feat_title.lower() + " " + period.lower()):
                continue
            rows.append((d, feat_title, title, period))

        col, rev = self._sort
        keyfun = {
            "feature": lambda r: r[1].lower(),
            "title": lambda r: r[2].lower(),
            "period": lambda r: r[3].lower(),
            "created": lambda r: r[0].get("created_at") or "",
            "size": lambda r: r[0].get("size") or 0,
        }[col]
        rows.sort(key=keyfun, reverse=rev)

        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        total_size = 0
        for d, feat_title, title, period in rows:
            size = d.get("size") or 0
            total_size += size
            kb = f"{round(size / 1024)} КБ" if size else ""
            iid = self.tree.insert("", "end", values=(feat_title, title, period,
                                                      d.get("created_at"), kb))
            self._rows[iid] = (d["id"], d.get("filename") or "document")
        mb = total_size / (1024 * 1024)
        self.totals_var.set(f"Показано: {len(rows)} из {len(self._all)} · объём: "
                            + (f"{mb:.1f} МБ" if mb >= 1 else f"{round(total_size / 1024)} КБ"))

    def _sort_by(self, col):
        cur_col, cur_rev = self._sort
        self._sort = (col, not cur_rev if col == cur_col else False)
        self._apply()

    # ---------------------------------------------------------------- действия
    def _selected(self):
        s = self.tree.selection()
        return self._rows.get(s[0]) if s else (None, None)

    def _open(self):
        doc_id, _ = self._selected()
        if not doc_id:
            return
        path = documents.extract_to_temp(doc_id)
        if path:
            try:
                os.startfile(path)
            except Exception:  # noqa: BLE001
                messagebox.showinfo("Файл", path)

    def _save_as(self):
        doc_id, filename = self._selected()
        if not doc_id:
            return
        ext = os.path.splitext(filename or "")[1] or ".dat"
        dest = filedialog.asksaveasfilename(title="Сохранить как…", defaultextension=ext,
                                            initialfile=filename)
        if dest and documents.save_as(doc_id, dest):
            messagebox.showinfo("Сохранено", f"Файл сохранён:\n{dest}")

    def _delete(self):
        doc_id, filename = self._selected()
        if not doc_id:
            return
        if messagebox.askyesno("Удалить", f"Удалить из базы «{filename}»?"):
            documents.delete(doc_id)
            self._reload()


def open_documents(master):
    return DocumentsWindow(master)
