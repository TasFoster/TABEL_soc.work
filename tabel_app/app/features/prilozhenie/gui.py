"""Графический интерфейс функции «Приложение к табелю» (Tkinter)."""

import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..timesheet.calendar_ru import MONTHS_NOM
from . import FEATURE_TITLE, service, storage
from ...core import documents, feedback, ui_state
from .model import SECTOR_LABEL, THRESHOLD, Absence, Period, Redistribution

CODE_LABELS = {
    "Б": "Б — больничный",
    "ОТ": "ОТ — отпуск",
    "ОЖ": "ОЖ — отпуск по уходу за ребёнком",
}


def _absence_codes():
    codes = []
    for c in storage.get_setting("absence_codes", []) or []:
        if isinstance(c, dict) and c.get("counts_as_absence"):
            codes.append(c["code"])
    return codes or ["Б", "ОТ", "ОЖ"]


def _fmt(v):
    if v is None:
        return ""
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else str(round(f, 2))
    except (TypeError, ValueError):
        return str(v)


class PrilozhenieWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Приложение к табелю")
        self.geometry("1040x640")
        self.minsize(940, 560)

        storage.ensure_ready()
        self.departments = storage.list_departments()
        self.result = None
        self.workers = []

        self._build_ui()
        self._reload_departments_combo()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="Отделение:").grid(row=0, column=0, sticky="w")
        self.dept_var = tk.StringVar()
        self.dept_combo = ttk.Combobox(top, textvariable=self.dept_var, state="readonly", width=46)
        self.dept_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.dept_combo.bind("<<ComboboxSelected>>", lambda e: self._recompute())

        today = datetime.date.today()
        ttk.Label(top, text="Месяц:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.month_var = tk.StringVar(value=MONTHS_NOM[today.month])
        self.month_combo = ttk.Combobox(top, textvariable=self.month_var, state="readonly",
                                         values=MONTHS_NOM[1:], width=14)
        self.month_combo.grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        self.month_combo.bind("<<ComboboxSelected>>", lambda e: self._recompute())

        yf = ttk.Frame(top)
        yf.grid(row=1, column=1, sticky="e", pady=(6, 0))
        ttk.Label(yf, text="Год:").pack(side="left")
        self.year_var = tk.IntVar(value=today.year)
        self.year_spin = tk.Spinbox(yf, from_=2024, to=2035, textvariable=self.year_var,
                                    width=6, command=self._recompute)
        self.year_spin.pack(side="left", padx=4)
        self.year_spin.bind("<KeyRelease>", lambda e: self._recompute())

        self.info = ttk.Label(top, text="", foreground="#367")
        self.info.grid(row=2, column=1, sticky="w", padx=6)

        mid = ttk.LabelFrame(self, text="Соцработники (чел/день и итоги)")
        mid.pack(fill="both", expand=True, **pad)
        cols = ("n", "fio", "gor", "chast", "absence", "tot_gor", "tot_chast")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        heads = [("n", "№", 36), ("fio", "ФИО", 300), ("gor", "Город/день", 80),
                 ("chast", "Частный/день", 90), ("absence", "Отсутствия", 170),
                 ("tot_gor", "Всего город", 90), ("tot_chast", "Всего частн.", 90)]
        for c, t, w in heads:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        self.tree.column("fio", anchor="w")
        self.tree.tag_configure("over", background="#ffe0e0")
        self.tree.tag_configure("inactive", foreground="#999")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._edit_load())
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        btns = ttk.Frame(self)
        btns.pack(fill="x", **pad)
        ttk.Button(btns, text="Нагрузка сотрудника…", command=self._edit_load).pack(side="left")
        ttk.Button(btns, text="Нагрузка по периодам…", command=self._edit_periods).pack(side="left", padx=4)
        ttk.Button(btns, text="+ Отсутствие", command=self._add_absence).pack(side="left", padx=4)
        ttk.Button(btns, text="− Отсутствия", command=self._clear_absences).pack(side="left")
        ttk.Button(btns, text="Перераспределение чел/дней…", command=self._redistribute).pack(side="left", padx=4)

        self.warn = tk.Text(self, height=3, wrap="word", foreground="#b00", background="#fff7f7")
        self.warn.pack(fill="x", padx=8)
        self.warn.configure(state="disabled")

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", **pad)
        ttk.Label(bottom, text="(двойной клик по строке — нагрузка сотрудника)").pack(side="left")
        self.gen_btn = ttk.Button(bottom, text="Сформировать приложение", command=self._generate)
        self.gen_btn.pack(side="right")
        self.status = ttk.Label(bottom, text="")
        self.status.pack(side="right", padx=10)
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    # ----------------------------------------------------------- helpers
    def _current_dept_id(self):
        idx = self.dept_combo.current()
        if idx < 0 or idx >= len(self.departments):
            return None
        return self.departments[idx]["id"]

    def _year_month(self):
        try:
            year = int(self.year_var.get())
        except (tk.TclError, ValueError):
            year = datetime.date.today().year
        month = MONTHS_NOM.index(self.month_var.get())
        return year, month

    def _reload_departments_combo(self):
        names = [d["name"] for d in self.departments]
        self.dept_combo["values"] = names
        if self.departments and self.dept_combo.current() < 0:
            self.dept_combo.current(ui_state.dept_index("prilozhenie", names))
        self._recompute()

    def _selected_worker(self):
        sel = self.tree.selection()
        if not sel:
            return None
        eid = int(sel[0])
        for w in self.workers:
            if w.employee_id == eid:
                return w
        return None

    def _absence_text(self, eid):
        items = [a for a in (self._absences or []) if a.employee_id == eid]
        return "; ".join(f"{a.code}: {a.day_from}–{a.day_to}" for a in items)

    # ----------------------------------------------------------- recompute
    def _recompute(self):
        dept_id = self._current_dept_id()
        if dept_id is None:
            return
        year, month = self._year_month()
        try:
            dept, workers, result = service.compute_month(dept_id, year, month)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка расчёта", str(e))
            return
        self.workers = workers
        self.result = result
        self._absences = storage.get_absences(dept_id, year, month)
        self._refresh_tree()
        self._refresh_warnings()
        wd = result["nworkdays"]
        gt = result["grand_total"]
        self.info.config(
            text=f"Рабочих дней: {wd}.  Итого: город {_fmt(gt['gor'])}, "
                 f"частный {_fmt(gt['chast'])}, вместе {_fmt(result['grand_combined'])} чел/дней."
        )

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        by_id = {w["employee_id"]: w for w in self.result["workers"]}
        for w in self.workers:
            r = by_id.get(w.employee_id, {})
            tot = r.get("totals", {"gor": 0, "chast": 0})
            tags = []
            # пометить превышение порога в каком-либо дне
            over = any(
                (r.get("grid", {}).get(s, {}).get(d) or 0) > THRESHOLD[s]
                for s in ("gor", "chast")
                for d in self.result["working_days"]
            )
            if over:
                tags.append("over")
            self.tree.insert(
                "", "end", iid=str(w.employee_id),
                values=(w.n, w.fio, _fmt(w.load_gor), _fmt(w.load_chast),
                        self._absence_text(w.employee_id),
                        _fmt(tot["gor"]), _fmt(tot["chast"])),
                tags=tags,
            )

    def _refresh_warnings(self):
        self.warn.configure(state="normal")
        self.warn.delete("1.0", "end")
        ws = self.result.get("warnings", []) if self.result else []
        if ws:
            self.warn.insert("1.0", "⚠ Превышение порога (" +
                             f"город {THRESHOLD['gor']}, частный {THRESHOLD['chast']} чел/день):\n" +
                             "; ".join(ws[:12]) + (" …" if len(ws) > 12 else ""))
        self.warn.configure(state="disabled")

    # ----------------------------------------------------------- actions
    def _edit_load(self):
        w = self._selected_worker()
        if not w:
            messagebox.showinfo("Сотрудник", "Выберите сотрудника в списке.")
            return
        dlg = LoadEditor(self, w)
        self.wait_window(dlg)
        if dlg.saved:
            storage.save_worker_load(w.employee_id, dlg.load_gor, dlg.load_chast,
                                     dlg.norma_gor, dlg.norma_chast, dlg.active)
            self._recompute()

    def _edit_periods(self):
        w = self._selected_worker()
        if not w:
            messagebox.showinfo("Сотрудник", "Выберите сотрудника в списке.")
            return
        dept_id = self._current_dept_id()
        year, month = self._year_month()
        ndays = service.days_in_month(year, month)
        existing = [p for p in storage.get_periods(dept_id, year, month)
                    if p.employee_id == w.employee_id]
        dlg = PeriodsEditor(self, w, ndays, existing)
        self.wait_window(dlg)
        if dlg.saved:
            others = [p for p in storage.get_periods(dept_id, year, month)
                      if p.employee_id != w.employee_id]
            storage.save_periods(dept_id, year, month, others + dlg.periods)
            self._recompute()

    def _add_absence(self):
        w = self._selected_worker()
        if not w:
            messagebox.showinfo("Сотрудник", "Выберите сотрудника в списке.")
            return
        dept_id = self._current_dept_id()
        year, month = self._year_month()
        ndays = service.days_in_month(year, month)
        dlg = AbsenceDialog(self, w.fio, ndays, _absence_codes())
        self.wait_window(dlg)
        if dlg.result:
            items = storage.get_absences(dept_id, year, month)
            items.append(Absence(w.employee_id, dlg.result["start"], dlg.result["end"],
                                 dlg.result["code"]))
            storage.save_absences(dept_id, year, month, items)
            self._recompute()

    def _clear_absences(self):
        w = self._selected_worker()
        if not w:
            return
        dept_id = self._current_dept_id()
        year, month = self._year_month()
        items = [a for a in storage.get_absences(dept_id, year, month)
                 if a.employee_id != w.employee_id]
        storage.save_absences(dept_id, year, month, items)
        self._recompute()

    def _redistribute(self):
        dept_id = self._current_dept_id()
        if dept_id is None:
            return
        year, month = self._year_month()
        dlg = RedistributionDialog(self, dept_id, year, month, self.workers,
                                   self._absences, self.result)
        self.wait_window(dlg)
        if dlg.saved:
            storage.save_redistributions(dept_id, year, month, dlg.items)
            self._recompute()

    def _generate(self):
        dept_id = self._current_dept_id()
        if dept_id is None:
            messagebox.showwarning("Нет отделения", "Выберите отделение.")
            return
        if not self.workers:
            messagebox.showwarning("Нет сотрудников", "В отделении нет активных соцработников.")
            return
        year, month = self._year_month()
        if self.result and self.result.get("warnings"):
            if not messagebox.askyesno(
                "Превышение порога",
                "Есть превышения порога чел/день. Всё равно сформировать?"):
                return
        dept = storage.get_department(dept_id)
        num = dept["name"].split("№")[-1].strip() if "№" in dept["name"] else ""
        default_name = f"Приложение_{num}_{MONTHS_NOM[month]}_{year}.xls".replace(" ", "_")
        out = filedialog.asksaveasfilename(
            title="Сохранить приложение как…", defaultextension=".xls",
            initialfile=default_name, initialdir=ui_state.last_dir("save") or None,
            filetypes=[("Книга Excel 97-2003", "*.xls")],
        )
        if not out:
            return
        ui_state.set_last_dir(out, "save")
        ui_state.set_last_dept("prilozhenie", self.dept_var.get())
        self.status.config(text="Формирование файла…")
        self.gen_btn.config(state="disabled")
        self.update_idletasks()
        try:
            service.generate_prilozhenie(dept_id, year, month, out)
            documents.save_file("prilozhenie", out, {"year": year, "month": month})
        except Exception as e:  # noqa: BLE001
            self.status.config(text="")
            self.gen_btn.config(state="normal")
            messagebox.showerror("Ошибка при формировании", str(e))
            return
        self.status.config(text="Готово")
        self.gen_btn.config(state="normal")
        if messagebox.askyesno("Готово", f"Файл сохранён:\n{out}\n\nОткрыть?"):
            try:
                os.startfile(out)
            except Exception:  # noqa: BLE001
                pass


# ----------------------------------------------------------- диалоги

class LoadEditor(tk.Toplevel):
    def __init__(self, master, worker):
        super().__init__(master)
        self.title("Нагрузка сотрудника")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.saved = False

        ttk.Label(self, text=worker.fio, font=("", 10, "bold")).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="w")
        rows = [
            ("load_gor", "Город — чел/день", worker.load_gor),
            ("load_chast", "Частный — чел/день", worker.load_chast),
            ("norma_gor", "Норма города (чел/день)", worker.norma_gor),
            ("norma_chast", "Норма частного (чел/день)", worker.norma_chast),
        ]
        self.vars = {}
        for i, (key, label, val) in enumerate(rows, 1):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="e", padx=8, pady=3)
            v = tk.StringVar(value=_fmt(val))
            ttk.Entry(self, textvariable=v, width=10).grid(row=i, column=1, sticky="w", padx=8)
            self.vars[key] = v
        self.active_var = tk.BooleanVar(value=worker.active)
        ttk.Checkbutton(self, text="Участвует в приложении за месяц",
                        variable=self.active_var).grid(row=5, column=0, columnspan=2, padx=8, pady=4, sticky="w")
        bar = ttk.Frame(self)
        bar.grid(row=6, column=0, columnspan=2, pady=10)
        ttk.Button(bar, text="Сохранить", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="left", padx=6)

    def _ok(self):
        try:
            self.load_gor = float(self.vars["load_gor"].get().replace(",", ".") or 0)
            self.load_chast = float(self.vars["load_chast"].get().replace(",", ".") or 0)
            self.norma_gor = float(self.vars["norma_gor"].get().replace(",", ".") or 10)
            self.norma_chast = float(self.vars["norma_chast"].get().replace(",", ".") or 8)
        except ValueError:
            messagebox.showerror("Число", "Введите числовые значения.")
            return
        self.active = self.active_var.get()
        self.saved = True
        self.destroy()


class PeriodsEditor(tk.Toplevel):
    """Переопределение нагрузки по периодам дат (для одного сотрудника/месяца)."""

    def __init__(self, master, worker, ndays, existing):
        super().__init__(master)
        self.title("Нагрузка по периодам")
        self.geometry("460x360")
        self.transient(master)
        self.grab_set()
        self.saved = False
        self.ndays = ndays
        self.worker = worker
        self.periods = list(existing)

        ttk.Label(self, text=f"{worker.fio} — переопределение нагрузки по дням",
                  font=("", 10, "bold")).pack(padx=10, pady=(10, 4), anchor="w")
        ttk.Label(self, text="Если периодов нет — действует постоянная нагрузка сотрудника.",
                  foreground="#555").pack(padx=10, anchor="w")

        cols = ("sector", "from", "to", "value")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=8)
        for c, t, w in (("sector", "Сектор", 90), ("from", "С дня", 70),
                        ("to", "По день", 70), ("value", "Чел/день", 90)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)
        self._refresh()

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10)
        ttk.Button(bar, text="Добавить", command=self._add).pack(side="left")
        ttk.Button(bar, text="Удалить", command=self._del).pack(side="left", padx=4)
        bar2 = ttk.Frame(self)
        bar2.pack(fill="x", padx=10, pady=8)
        ttk.Button(bar2, text="Сохранить", command=self._save).pack(side="right")
        ttk.Button(bar2, text="Отмена", command=self.destroy).pack(side="right", padx=6)

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self.periods):
            self.tree.insert("", "end", iid=str(i),
                             values=(SECTOR_LABEL[p.sector], p.day_from, p.day_to, _fmt(p.value)))

    def _add(self):
        dlg = PeriodDialog(self, self.ndays)
        self.wait_window(dlg)
        if dlg.result:
            sector, df, dt, val = dlg.result
            self.periods.append(Period(self.worker.employee_id, sector, df, dt, val))
            self._refresh()

    def _del(self):
        sel = self.tree.selection()
        if sel:
            del self.periods[int(sel[0])]
            self._refresh()

    def _save(self):
        self.saved = True
        self.destroy()


class PeriodDialog(tk.Toplevel):
    def __init__(self, master, ndays):
        super().__init__(master)
        self.title("Период")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result = None
        self.ndays = ndays
        ttk.Label(self, text="Сектор:").grid(row=0, column=0, sticky="e", padx=8, pady=4)
        self.sector_var = tk.StringVar(value="гор.")
        ttk.Combobox(self, textvariable=self.sector_var, state="readonly",
                     values=["гор.", "част"], width=8).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(self, text=f"С дня (1–{ndays}):").grid(row=1, column=0, sticky="e", padx=8, pady=4)
        self.from_var = tk.IntVar(value=1)
        tk.Spinbox(self, from_=1, to=ndays, textvariable=self.from_var, width=6).grid(row=1, column=1, sticky="w", padx=8)
        ttk.Label(self, text=f"По день (1–{ndays}):").grid(row=2, column=0, sticky="e", padx=8, pady=4)
        self.to_var = tk.IntVar(value=ndays)
        tk.Spinbox(self, from_=1, to=ndays, textvariable=self.to_var, width=6).grid(row=2, column=1, sticky="w", padx=8)
        ttk.Label(self, text="Чел/день:").grid(row=3, column=0, sticky="e", padx=8, pady=4)
        self.val_var = tk.StringVar(value="10")
        ttk.Entry(self, textvariable=self.val_var, width=8).grid(row=3, column=1, sticky="w", padx=8)
        bar = ttk.Frame(self)
        bar.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(bar, text="ОК", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="left", padx=6)

    def _ok(self):
        df, dt = self.from_var.get(), self.to_var.get()
        if not (1 <= df <= dt <= self.ndays):
            messagebox.showerror("Период", f"Укажите диапазон 1–{self.ndays}.")
            return
        try:
            val = float(self.val_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Число", "Чел/день должно быть числом.")
            return
        sector = "gor" if self.sector_var.get().startswith("гор") else "chast"
        self.result = (sector, int(df), int(dt), val)
        self.destroy()


class AbsenceDialog(tk.Toplevel):
    def __init__(self, master, fio, ndays, codes):
        super().__init__(master)
        self.title("Период отсутствия")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result = None
        self.ndays = ndays
        ttk.Label(self, text=fio, font=("", 10, "bold")).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="w")
        ttk.Label(self, text="Тип:").grid(row=1, column=0, sticky="e", padx=8, pady=4)
        labels = [CODE_LABELS.get(c, c) for c in codes]
        self._code_by_label = {CODE_LABELS.get(c, c): c for c in codes}
        self._cb = ttk.Combobox(self, values=labels, state="readonly", width=34)
        self._cb.current(0)
        self._cb.grid(row=1, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(self, text=f"С какого числа (1–{ndays}):").grid(row=2, column=0, sticky="e", padx=8, pady=4)
        self.start_var = tk.IntVar(value=1)
        tk.Spinbox(self, from_=1, to=ndays, textvariable=self.start_var, width=6).grid(row=2, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(self, text=f"По какое число (1–{ndays}):").grid(row=3, column=0, sticky="e", padx=8, pady=4)
        self.end_var = tk.IntVar(value=ndays)
        tk.Spinbox(self, from_=1, to=ndays, textvariable=self.end_var, width=6).grid(row=3, column=1, sticky="w", padx=8, pady=4)
        bar = ttk.Frame(self)
        bar.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(bar, text="Добавить", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="left", padx=6)
        self.bind("<Return>", lambda e: self._ok())

    def _ok(self):
        s, e = self.start_var.get(), self.end_var.get()
        if not (1 <= s <= e <= self.ndays):
            messagebox.showerror("Период", f"Укажите диапазон 1–{self.ndays}.")
            return
        self.result = {"start": int(s), "end": int(e),
                       "code": self._code_by_label.get(self._cb.get(), self._cb.get())}
        self.destroy()


class RedistributionDialog(tk.Toplevel):
    """Перераспределение чел/дней: авто-черновик по отсутствиям + ручная правка.

    Получателей назначает пользователь. Каждая строка: сектор, ОТ кого, КОМУ,
    дни, чел/день.
    """

    def __init__(self, master, dept_id, year, month, workers, absences, result):
        super().__init__(master)
        self.title("Перераспределение чел/дней")
        self.geometry("720x460")
        self.transient(master)
        self.grab_set()
        self.saved = False
        self.dept_id = dept_id
        self.year, self.month = year, month
        self.workers = workers
        self.absences = absences or []
        self.by_id = {w.employee_id: w for w in workers}
        self.items = list(storage.get_redistributions(dept_id, year, month))

        info = ("Авто-черновик: освободившиеся чел/день отсутствующих можно раздать "
                "присутствующим. Получателя выбираете вручную. Город и частный — раздельно.")
        ttk.Label(self, text=info, wraplength=690, foreground="#444").pack(padx=10, pady=(8, 4), anchor="w")

        cols = ("sector", "frm", "to", "from_day", "to_day", "value")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        for c, t, w in (("sector", "Сектор", 70), ("frm", "От кого", 180),
                        ("to", "Кому", 180), ("from_day", "С дня", 55),
                        ("to_day", "По день", 60), ("value", "Чел/день", 70)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        self.tree.column("frm", anchor="w")
        self.tree.column("to", anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)
        self._refresh()

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10)
        ttk.Button(bar, text="Авто-черновик по отсутствиям", command=self._auto).pack(side="left")
        ttk.Button(bar, text="Добавить вручную", command=self._add).pack(side="left", padx=4)
        ttk.Button(bar, text="Удалить", command=self._del).pack(side="left")
        bar2 = ttk.Frame(self)
        bar2.pack(fill="x", padx=10, pady=8)
        ttk.Button(bar2, text="Сохранить", command=self._save).pack(side="right")
        ttk.Button(bar2, text="Отмена", command=self.destroy).pack(side="right", padx=6)

    def _emp_name(self, eid):
        # ВНИМАНИЕ: не называть метод _name — у tk.Toplevel это строковый атрибут
        # (имя виджета), он перекроет метод и вызов упадёт «'str' object is not callable».
        w = self.by_id.get(eid)
        return w.fio if w else "(?)"

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.items):
            self.tree.insert("", "end", iid=str(i), values=(
                SECTOR_LABEL[r.sector], self._emp_name(r.from_employee_id),
                self._emp_name(r.to_employee_id), r.day_from, r.day_to, _fmt(r.value)))

    def _auto(self):
        """Для каждого отсутствующего создать заготовки переноса (получатель пуст)."""
        ndays = service.days_in_month(self.year, self.month)
        added = 0
        for a in self.absences:
            w = self.by_id.get(a.employee_id)
            if not w:
                continue
            for sector in ("gor", "chast"):
                load = w.load(sector)
                if load > 0:
                    dlg = RedistRowDialog(self, self.workers, sector, a.employee_id,
                                          a.day_from, a.day_to, load, ndays,
                                          title=f"{w.fio}: {SECTOR_LABEL[sector]} {a.day_from}–{a.day_to}")
                    self.wait_window(dlg)
                    if dlg.result:
                        self.items.append(dlg.result)
                        added += 1
        self._refresh()
        if not added:
            messagebox.showinfo("Авто-черновик",
                                "Нет отсутствий с ненулевой нагрузкой для перераспределения.")

    def _add(self):
        ndays = service.days_in_month(self.year, self.month)
        dlg = RedistRowDialog(self, self.workers, "gor", None, 1, ndays, 0, ndays)
        self.wait_window(dlg)
        if dlg.result:
            self.items.append(dlg.result)
            self._refresh()

    def _del(self):
        sel = self.tree.selection()
        if sel:
            del self.items[int(sel[0])]
            self._refresh()

    def _save(self):
        self.saved = True
        self.destroy()


class RedistRowDialog(tk.Toplevel):
    def __init__(self, master, workers, sector, from_eid, df, dt, value, ndays, title="Перенос"):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result = None
        self.ndays = ndays
        self.workers = workers
        self._names = [w.fio for w in workers]
        self._ids = [w.employee_id for w in workers]

        ttk.Label(self, text="Сектор:").grid(row=0, column=0, sticky="e", padx=8, pady=4)
        self.sector_var = tk.StringVar(value=SECTOR_LABEL[sector])
        ttk.Combobox(self, textvariable=self.sector_var, state="readonly",
                     values=["гор.", "част"], width=8).grid(row=0, column=1, sticky="w", padx=8)

        ttk.Label(self, text="От кого:").grid(row=1, column=0, sticky="e", padx=8, pady=4)
        self.from_cb = ttk.Combobox(self, values=self._names, state="readonly", width=34)
        if from_eid in self._ids:
            self.from_cb.current(self._ids.index(from_eid))
        self.from_cb.grid(row=1, column=1, sticky="w", padx=8)

        ttk.Label(self, text="Кому:").grid(row=2, column=0, sticky="e", padx=8, pady=4)
        self.to_cb = ttk.Combobox(self, values=self._names, state="readonly", width=34)
        self.to_cb.grid(row=2, column=1, sticky="w", padx=8)

        ttk.Label(self, text=f"С дня (1–{ndays}):").grid(row=3, column=0, sticky="e", padx=8, pady=4)
        self.from_var = tk.IntVar(value=df)
        tk.Spinbox(self, from_=1, to=ndays, textvariable=self.from_var, width=6).grid(row=3, column=1, sticky="w", padx=8)
        ttk.Label(self, text=f"По день (1–{ndays}):").grid(row=4, column=0, sticky="e", padx=8, pady=4)
        self.to_var = tk.IntVar(value=dt)
        tk.Spinbox(self, from_=1, to=ndays, textvariable=self.to_var, width=6).grid(row=4, column=1, sticky="w", padx=8)
        ttk.Label(self, text="Чел/день:").grid(row=5, column=0, sticky="e", padx=8, pady=4)
        self.val_var = tk.StringVar(value=_fmt(value))
        ttk.Entry(self, textvariable=self.val_var, width=8).grid(row=5, column=1, sticky="w", padx=8)

        bar = ttk.Frame(self)
        bar.grid(row=6, column=0, columnspan=2, pady=10)
        ttk.Button(bar, text="ОК", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bar, text="Пропустить", command=self.destroy).pack(side="left", padx=6)

    def _ok(self):
        fi, ti = self.from_cb.current(), self.to_cb.current()
        if fi < 0 or ti < 0:
            messagebox.showerror("Сотрудники", "Выберите «от кого» и «кому».")
            return
        if fi == ti:
            messagebox.showerror("Сотрудники", "«От кого» и «кому» должны отличаться.")
            return
        df, dt = self.from_var.get(), self.to_var.get()
        if not (1 <= df <= dt <= self.ndays):
            messagebox.showerror("Период", f"Укажите диапазон 1–{self.ndays}.")
            return
        try:
            val = float(self.val_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Число", "Чел/день должно быть числом.")
            return
        sector = "gor" if self.sector_var.get().startswith("гор") else "chast"
        self.result = Redistribution(sector, self._ids[fi], self._ids[ti], int(df), int(dt), val)
        self.destroy()


def open_prilozhenie(master):
    return PrilozhenieWindow(master)


def run():
    root = tk.Tk()
    root.withdraw()
    win = PrilozhenieWindow(root)
    win.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
