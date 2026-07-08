"""Представление (View) «Реестра по оплате» — Tkinter (тонкий слой).

Выбор готового реестра .ods + отчёта по договорам .xls → «Проанализировать» →
чеклист предлагаемых изменений (галочка = применить; для новых клиентов двойным
кликом назначается соцработник) → «Применить и сохранить». Живые формулы
пересобираются, готовый файл архивируется в «Сохранённые документы».
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import FEATURE_TITLE
from . import service
from ...core import documents, feedback, ui_state

_COLS = ("sel", "cat", "fio", "worker", "detail")
_HEADS = ("✔", "Тип", "ФИО", "Соцработник", "Изменение")
_WIDTHS = (34, 150, 250, 200, 230)
_ON, _OFF = "☑", "☐"


class ReestrOplataWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title(FEATURE_TITLE)
        self.geometry("980x620")
        self.minsize(820, 480)

        self.model = None
        self.journal = None
        self.plan = None
        self._order = []                       # индексы plan.changes в порядке дерева

        self.ods_var = tk.StringVar()
        self.jrn_var = tk.StringVar()
        self.info = tk.StringVar(value=(
            "1) Выберите готовый реестр .ods (Гос_/Доп/деньги).  "
            "2) Выберите «Отчёт по количеству заключённых договоров» .xls.  "
            "3) Нажмите «Проанализировать»."))
        self._build()

    # ------------------------------------------------------------------ разметка
    def _build(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.LabelFrame(self, text="Исходные файлы")
        top.pack(fill="x", **pad)
        g = ttk.Frame(top)
        g.pack(fill="x", padx=6, pady=4)
        ttk.Label(g, text="Реестр (.ods):").grid(row=0, column=0, sticky="w")
        ttk.Entry(g, textvariable=self.ods_var).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(g, text="Обзор…", command=self._pick_ods).grid(row=0, column=2)
        ttk.Label(g, text="Отчёт по договорам (.xls):").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(g, textvariable=self.jrn_var).grid(row=1, column=1, sticky="we", padx=4, pady=(4, 0))
        ttk.Button(g, text="Обзор…", command=self._pick_jrn).grid(row=1, column=2, pady=(4, 0))
        ttk.Button(g, text="Проанализировать", command=self._analyze).grid(
            row=0, column=3, rowspan=2, sticky="ns", padx=8)
        g.columnconfigure(1, weight=1)

        mid = ttk.LabelFrame(self, text="Предлагаемые изменения (галочка = применить)")
        mid.pack(fill="both", expand=True, **pad)
        self.tree = ttk.Treeview(mid, columns=_COLS, show="headings", selectmode="browse")
        for key, head, w in zip(_COLS, _HEADS, _WIDTHS):
            self.tree.heading(key, text=head)
            anchor = "center" if key == "sel" else "w"
            self.tree.column(key, width=w, anchor=anchor,
                             stretch=(key in ("fio", "detail")))
        tsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("new", background="#eaf5ea")
        self.tree.tag_configure("snyat", background="#fdeaea")
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Double-1>", self._on_double_click)

        ttk.Label(self, textvariable=self.info, foreground="#555", wraplength=940,
                  justify="left").pack(fill="x", padx=10, pady=(2, 0))
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        self.apply_btn = ttk.Button(bottom, text="Применить и сохранить",
                                    command=self._apply, state="disabled")
        self.apply_btn.pack(side="right")
        ttk.Button(bottom, text="Снять все", command=lambda: self._mark_all(False)).pack(
            side="right", padx=4)
        ttk.Button(bottom, text="Отметить все", command=lambda: self._mark_all(True)).pack(
            side="right", padx=4)
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    # ------------------------------------------------------------------ файлы
    def _pick_ods(self):
        f = filedialog.askopenfilename(
            title="Готовый реестр (.ods)", initialdir=ui_state.last_dir("open") or None,
            filetypes=[("OpenDocument Spreadsheet", "*.ods"), ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.ods_var.set(f)

    def _pick_jrn(self):
        f = filedialog.askopenfilename(
            title="Отчёт по количеству заключённых договоров (.xls)",
            initialdir=ui_state.last_dir("open") or None,
            filetypes=[("Excel 97-2003", "*.xls"), ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.jrn_var.set(f)

    # ------------------------------------------------------------------ анализ
    def _analyze(self):
        ods, jrn = self.ods_var.get().strip(), self.jrn_var.get().strip()
        if not ods or not os.path.exists(ods):
            messagebox.showwarning("Нет файла", "Укажите готовый реестр .ods.")
            return
        if not jrn or not os.path.exists(jrn):
            messagebox.showwarning("Нет файла", "Укажите отчёт по договорам .xls.")
            return
        self.info.set("Анализирую…")
        self.update_idletasks()
        try:
            self.model, self.journal, self.plan = service.analyze(ods, jrn)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка анализа", str(e))
            self.info.set("Ошибка анализа. Проверьте файлы.")
            return
        self._refresh_tree()
        n = len(self.plan.changes)
        p = self.plan.period
        self.apply_btn.config(state=("normal" if n else "disabled"))
        if n:
            self.info.set(
                f"Период журнала {p[0]}–{p[1]}. Изменений: {n}. "
                "Снимите галочки с лишнего; новым клиентам двойным кликом назначьте "
                "соцработника, затем «Применить и сохранить».")
        else:
            self.info.set(f"Период журнала {p[0]}–{p[1]}. Изменений не найдено — "
                          "реестр уже соответствует журналу.")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._order = []
        order = list(service.CAT_TITLES)          # порядок категорий
        idx = sorted(range(len(self.plan.changes)),
                     key=lambda i: order.index(self.plan.changes[i].category))
        for i in idx:
            ch = self.plan.changes[i]
            tag = "new" if ch.category == service.CAT_NEW else (
                "snyat" if ch.category in (service.CAT_SNYAT, service.CAT_DOP_SNYAT) else "")
            self.tree.insert("", "end", iid=str(i), tags=(tag,) if tag else (),
                             values=self._row_values(ch))
            self._order.append(i)

    def _row_values(self, ch):
        worker = ch.worker or ("— назначьте —" if ch.category == service.CAT_NEW else "")
        return (_ON if ch.selected else _OFF, service.CAT_TITLES.get(ch.category, ch.category),
                ch.fio, worker, ch.detail)

    def _update_row(self, i):
        self.tree.item(str(i), values=self._row_values(self.plan.changes[i]))

    # ------------------------------------------------------------------ правки чеклиста
    def _on_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        rowid = self.tree.identify_row(event.y)
        if not rowid:
            return
        ch = self.plan.changes[int(rowid)]
        ch.selected = not ch.selected
        self._update_row(int(rowid))

    def _on_double_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        rowid = self.tree.identify_row(event.y)
        if not rowid or self.tree.identify_column(event.x) != "#4":
            return
        ch = self.plan.changes[int(rowid)]
        if ch.category != service.CAT_NEW:
            return
        bbox = self.tree.bbox(rowid, "#4")
        if not bbox:
            return
        x, y, w, h = bbox
        box = ttk.Combobox(self.tree, state="readonly", values=service.worker_names(self.model))
        box.place(x=x, y=y, width=w, height=h)
        if ch.worker:
            box.set(ch.worker)
        box.focus_set()

        def commit(_=None):
            val = box.get().strip()
            if val:
                ch.worker = val
                self._update_row(int(rowid))
            box.destroy()

        box.bind("<<ComboboxSelected>>", commit)
        box.bind("<FocusOut>", lambda _e: box.destroy())
        box.bind("<Escape>", lambda _e: box.destroy())

    def _mark_all(self, on):
        if not self.plan:
            return
        for ch in self.plan.changes:
            ch.selected = on
        for i in self._order:
            self._update_row(i)

    # ------------------------------------------------------------------ применение
    def _apply(self):
        sel = self.plan.selected if self.plan else []
        if not sel:
            messagebox.showwarning("Пусто", "Не отмечено ни одного изменения.")
            return
        unassigned = [c for c in sel if c.category == service.CAT_NEW and not c.worker]
        if unassigned:
            messagebox.showwarning(
                "Не назначен соцработник",
                "Для новых клиентов не выбран соцработник (двойной клик по столбцу "
                f"«Соцработник»):\n\n" + "\n".join(f"• {c.fio}" for c in unassigned[:12]))
            return

        default = os.path.basename(self.ods_var.get())
        out = filedialog.asksaveasfilename(
            title="Сохранить реестр как…", defaultextension=".ods", initialfile=default,
            initialdir=ui_state.last_dir("save") or os.path.dirname(self.ods_var.get()) or None,
            filetypes=[("OpenDocument Spreadsheet", "*.ods")])
        if not out:
            return
        ui_state.set_last_dir(out, "save")
        self.apply_btn.config(state="disabled")
        self.update_idletasks()
        try:
            from . import ods_editor as ed
            service.apply_plan(self.model, self.plan, self.journal)
            ed.save(self.model, out)
            month, year = self._period_my()
            documents.save_file("reestr_oplata", out, {"month": month, "year": year})
        except Exception as e:  # noqa: BLE001
            self.apply_btn.config(state="normal")
            messagebox.showerror("Ошибка применения", str(e))
            return
        self.info.set(f"Готово: применено {len(sel)} изм., сохранено в {out}")
        if messagebox.askyesno("Готово", f"Файл сохранён:\n{out}\n\nОткрыть?"):
            try:
                os.startfile(out)
            except Exception:  # noqa: BLE001
                pass
        self.destroy()

    def _period_my(self):
        try:
            _, mm, yy = self.plan.period[0].split(".")
            return int(mm), int(yy)
        except Exception:  # noqa: BLE001
            return None, None


def open_reestr_oplata(master):
    return ReestrOplataWindow(master)
