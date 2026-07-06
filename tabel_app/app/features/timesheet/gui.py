"""Графический интерфейс приложения «Табель» (Tkinter)."""

import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import FEATURE_TITLE, storage
from ...core import documents, feedback, ui_state
from .calendar_ru import MONTHS_NOM, month_title
from .service import generate_timesheet
from .timesheet import days_in_month, validate_absences

CODE_LABELS = {
    "Б": "Б — больничный",
    "ОТ": "ОТ — отпуск",
    "ОЖ": "ОЖ — отпуск по уходу за ребёнком",
}


def _absence_codes(settings):
    codes = []
    for c in settings.get("absence_codes", []):
        if c.get("counts_as_absence"):
            codes.append(c["code"])
    return codes or ["Б", "ОТ", "ОЖ"]


class TimesheetWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Табель учёта рабочего времени")
        self.geometry("900x620")
        self.minsize(820, 560)

        self.departments = storage.load_departments()
        self.settings = storage.load_settings()
        self.calendar = storage.load_calendar()

        # Отсутствия для текущего отделения и месяца: {employee_n: [{start,end,code}]}
        self.absences = {}

        self._build_ui()
        self._reload_departments_combo()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="Отделение:").grid(row=0, column=0, sticky="w")
        self.dept_var = tk.StringVar()
        self.dept_combo = ttk.Combobox(top, textvariable=self.dept_var, state="readonly", width=48)
        self.dept_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.dept_combo.bind("<<ComboboxSelected>>", lambda e: self._on_context_change())
        ttk.Button(top, text="Отделения и сотрудники…", command=self._open_departments).grid(
            row=0, column=2, padx=6
        )

        today = datetime.date.today()
        ttk.Label(top, text="Месяц:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.month_var = tk.StringVar(value=MONTHS_NOM[today.month])
        self.month_combo = ttk.Combobox(
            top, textvariable=self.month_var, state="readonly",
            values=MONTHS_NOM[1:], width=14,
        )
        self.month_combo.grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        self.month_combo.bind("<<ComboboxSelected>>", lambda e: self._on_context_change())

        year_frame = ttk.Frame(top)
        year_frame.grid(row=1, column=1, sticky="e", pady=(6, 0))
        ttk.Label(year_frame, text="Год:").pack(side="left")
        self.year_var = tk.IntVar(value=today.year)
        self.year_spin = tk.Spinbox(
            year_frame, from_=2024, to=2035, textvariable=self.year_var, width=6,
            command=self._on_context_change,
        )
        self.year_spin.pack(side="left", padx=4)
        self.year_spin.bind("<KeyRelease>", lambda e: self._on_context_change())

        self.cal_warn = ttk.Label(top, text="", foreground="#b00")
        self.cal_warn.grid(row=2, column=1, sticky="w", padx=6)

        # Период табеля: весь месяц / первая половина (1–15) / вторая (16–конец)
        self.period_var = tk.StringVar(value="month")
        pf = ttk.Frame(top)
        pf.grid(row=3, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(pf, text="Период:").pack(side="left")
        for val, txt in (("month", "весь месяц"), ("first", "1–15"), ("second", "16–конец")):
            ttk.Radiobutton(pf, text=txt, value=val, variable=self.period_var).pack(
                side="left", padx=(6, 0))

        # Таблица сотрудников и отсутствий
        mid = ttk.LabelFrame(self, text="Сотрудники и отсутствия")
        mid.pack(fill="both", expand=True, **pad)

        cols = ("n", "fio", "position", "absence")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("n", text="№")
        self.tree.heading("fio", text="Фамилия, имя, отчество")
        self.tree.heading("position", text="Должность")
        self.tree.heading("absence", text="Отсутствия (Б/ОТ/ОЖ)")
        self.tree.column("n", width=40, anchor="center")
        self.tree.column("fio", width=320)
        self.tree.column("position", width=160)
        self.tree.column("absence", width=240)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._add_absence())
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        btns = ttk.Frame(self)
        btns.pack(fill="x", **pad)
        ttk.Button(btns, text="+ Добавить отсутствие", command=self._add_absence).pack(side="left")
        ttk.Button(btns, text="− Убрать отсутствия у сотрудника", command=self._clear_absence).pack(
            side="left", padx=6
        )
        ttk.Label(btns, text="(двойной клик по строке — добавить отсутствие)").pack(side="left", padx=10)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", **pad)
        ttk.Button(bottom, text="Реквизиты и подписи…", command=self._open_settings).pack(side="left")
        ttk.Button(bottom, text="Производственный календарь…", command=self._open_calendar).pack(
            side="left", padx=6
        )
        self.gen_btn = ttk.Button(bottom, text="Сформировать табель", command=self._generate)
        self.gen_btn.pack(side="right")
        self.status = ttk.Label(bottom, text="")
        self.status.pack(side="right", padx=10)
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    # ----------------------------------------------------------- helpers
    def _current_dept(self):
        idx = self.dept_combo.current()
        if idx < 0 or idx >= len(self.departments["departments"]):
            return None
        return self.departments["departments"][idx]

    def _current_year_month(self):
        try:
            year = int(self.year_var.get())
        except (tk.TclError, ValueError):
            year = datetime.date.today().year
        month = MONTHS_NOM.index(self.month_var.get())
        return year, month

    def _selected_period(self, ndays):
        """Период табеля: None — весь месяц; (1,15) или (16,ndays) — половина."""
        p = self.period_var.get()
        if p == "first":
            return (1, 15)
        if p == "second":
            return (16, ndays)
        return None

    def _reload_departments_combo(self):
        names = [d["name"] for d in self.departments["departments"]]
        self.dept_combo["values"] = names
        if names:
            if self.dept_combo.current() < 0:
                self.dept_combo.current(ui_state.dept_index("timesheet", names))
        self._on_context_change()

    def _on_context_change(self):
        self.absences = {}
        self._refresh_tree()
        self._check_calendar()

    def _check_calendar(self):
        year, month = self._current_year_month()
        if str(year) not in self.calendar:
            self.cal_warn.config(
                text=f"⚠ Нет данных календаря на {year} год — выходными будут только сб/вс. "
                     f"Заполните его в «Производственный календарь…»."
            )
        else:
            self.cal_warn.config(text="")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        dept = self._current_dept()
        if not dept:
            return
        for emp in dept["employees"]:
            self.tree.insert("", "end", iid=str(emp["n"]),
                             values=(emp["n"], emp["fio"], emp.get("position", ""),
                                     self._absence_text(emp["n"])))

    def _absence_text(self, n):
        items = self.absences.get(n, [])
        return "; ".join(f"{a['code']}: {a['start']}–{a['end']}" for a in items)

    def _selected_emp(self):
        sel = self.tree.selection()
        if not sel:
            return None
        dept = self._current_dept()
        n = int(sel[0])
        for emp in dept["employees"]:
            if emp["n"] == n:
                return emp
        return None

    # ----------------------------------------------------------- actions
    def _add_absence(self):
        emp = self._selected_emp()
        if not emp:
            messagebox.showinfo("Выбор сотрудника", "Сначала выберите сотрудника в списке.")
            return
        year, month = self._current_year_month()
        ndays = days_in_month(year, month)
        dlg = AbsenceDialog(self, emp["fio"], ndays, _absence_codes(self.settings))
        self.wait_window(dlg)
        if dlg.result:
            self.absences.setdefault(emp["n"], []).append(dlg.result)
            self.tree.set(str(emp["n"]), "absence", self._absence_text(emp["n"]))

    def _clear_absence(self):
        emp = self._selected_emp()
        if not emp:
            return
        if self.absences.pop(emp["n"], None) is not None:
            self.tree.set(str(emp["n"]), "absence", "")

    def _generate(self):
        dept = self._current_dept()
        if not dept:
            messagebox.showwarning("Нет отделения", "Сначала выберите отделение.")
            return
        if not dept["employees"]:
            messagebox.showwarning("Нет сотрудников", "В отделении нет сотрудников.")
            return
        year, month = self._current_year_month()
        ndays = days_in_month(year, month)

        # Проверка периодов отсутствия.
        for emp in dept["employees"]:
            errs = validate_absences(self.absences.get(emp["n"], []), ndays)
            if errs:
                messagebox.showerror("Ошибка в периодах", f"{emp['fio']}:\n" + "\n".join(errs))
                return

        period = self._selected_period(ndays)
        suffix = {"first": "_1-15", "second": "_16-конец"}.get(self.period_var.get(), "")
        default_name = (f"Табель_{dept['name'].split('№')[-1].strip()}_"
                        f"{MONTHS_NOM[month]}_{year}{suffix}.xls")
        default_name = default_name.replace(" ", "_")
        out = filedialog.asksaveasfilename(
            title="Сохранить табель как…",
            defaultextension=".xls",
            initialfile=default_name,
            initialdir=ui_state.last_dir("save") or None,
            filetypes=[("Книга Excel 97-2003", "*.xls")],
        )
        if not out:
            return
        ui_state.set_last_dir(out, "save")
        ui_state.set_last_dept("timesheet", self.dept_var.get())

        self.status.config(text="Формирование файла…")
        self.gen_btn.config(state="disabled")
        self.update_idletasks()

        try:
            generate_timesheet(dept, year, month, dict(self.absences), out, period=period)
            documents.save_file("timesheet", out, {"year": year, "month": month,
                                                   "period": self.period_var.get()})
        except Exception as e:  # noqa: BLE001
            self.status.config(text="")
            self.gen_btn.config(state="normal")
            messagebox.showerror("Ошибка при формировании", str(e))
            return

        self.status.config(text="Готово")
        self.gen_btn.config(state="normal")
        if messagebox.askyesno("Готово", f"Табель сохранён:\n{out}\n\nОткрыть файл?"):
            try:
                os.startfile(out)  # noqa: незадокументированный для не-Windows
            except Exception:  # noqa: BLE001
                pass

    def _open_departments(self):
        dlg = DepartmentManager(self, self.departments, self.settings)
        self.wait_window(dlg)
        if dlg.saved:
            self.departments = storage.load_departments()
            cur = self.dept_combo.current()
            self._reload_departments_combo()
            if 0 <= cur < len(self.departments["departments"]):
                self.dept_combo.current(cur)
                self._on_context_change()

    def _open_settings(self):
        dlg = SettingsDialog(self, self.settings)
        self.wait_window(dlg)
        if dlg.saved:
            self.settings = storage.load_settings()

    def _open_calendar(self):
        dlg = CalendarDialog(self, self.calendar)
        self.wait_window(dlg)
        if dlg.saved:
            self.calendar = storage.load_calendar()
            self._check_calendar()


# ----------------------------------------------------------- диалоги

class AbsenceDialog(tk.Toplevel):
    def __init__(self, master, fio, ndays, codes):
        super().__init__(master)
        self.title("Период отсутствия")
        self.resizable(False, False)
        self.result = None
        self.ndays = ndays
        self.transient(master)
        self.grab_set()

        ttk.Label(self, text=fio, font=("", 10, "bold")).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="w"
        )
        ttk.Label(self, text="Тип:").grid(row=1, column=0, sticky="e", padx=8, pady=4)
        self.code_var = tk.StringVar(value=codes[0])
        labels = [CODE_LABELS.get(c, c) for c in codes]
        self._code_by_label = {CODE_LABELS.get(c, c): c for c in codes}
        cb = ttk.Combobox(self, values=labels, state="readonly", width=34)
        cb.current(0)
        cb.grid(row=1, column=1, sticky="w", padx=8, pady=4)
        self._cb = cb

        ttk.Label(self, text=f"С какого числа (1–{ndays}):").grid(row=2, column=0, sticky="e", padx=8, pady=4)
        self.start_var = tk.IntVar(value=1)
        tk.Spinbox(self, from_=1, to=ndays, textvariable=self.start_var, width=6).grid(
            row=2, column=1, sticky="w", padx=8, pady=4
        )
        ttk.Label(self, text=f"По какое число (1–{ndays}):").grid(row=3, column=0, sticky="e", padx=8, pady=4)
        self.end_var = tk.IntVar(value=ndays)
        tk.Spinbox(self, from_=1, to=ndays, textvariable=self.end_var, width=6).grid(
            row=3, column=1, sticky="w", padx=8, pady=4
        )

        bar = ttk.Frame(self)
        bar.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(bar, text="Добавить", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="left", padx=6)
        self.bind("<Return>", lambda e: self._ok())

    def _ok(self):
        s, e = self.start_var.get(), self.end_var.get()
        if not (1 <= s <= e <= self.ndays):
            messagebox.showerror("Неверный период", f"Укажите корректный диапазон 1–{self.ndays}.")
            return
        code = self._code_by_label.get(self._cb.get(), self._cb.get())
        self.result = {"start": int(s), "end": int(e), "code": code}
        self.destroy()


class DepartmentManager(tk.Toplevel):
    """Управление отделениями и их сотрудниками."""

    def __init__(self, master, departments, settings):
        super().__init__(master)
        self.title("Отделения и сотрудники")
        self.geometry("760x520")
        self.transient(master)
        self.grab_set()
        self.data = departments
        self.saved = False

        left = ttk.LabelFrame(self, text="Отделения")
        left.pack(side="left", fill="y", padx=8, pady=8)
        self.dept_list = tk.Listbox(left, width=34, exportselection=False)
        self.dept_list.pack(fill="y", expand=True, padx=4, pady=4)
        self.dept_list.bind("<<ListboxSelect>>", lambda e: self._refresh_emps())
        dbtn = ttk.Frame(left)
        dbtn.pack(fill="x")
        ttk.Button(dbtn, text="Добавить", command=self._add_dept).pack(side="left", padx=2, pady=2)
        ttk.Button(dbtn, text="Изменить", command=self._edit_dept).pack(side="left", padx=2)
        ttk.Button(dbtn, text="Удалить", command=self._del_dept).pack(side="left", padx=2)

        right = ttk.LabelFrame(self, text="Сотрудники отделения")
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        cols = ("n", "fio", "tab", "oklad", "position")
        self.emp_tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("n", "№", 36), ("fio", "ФИО", 220), ("tab", "Таб.№", 60),
                        ("oklad", "Оклад", 70), ("position", "Должность", 130)):
            self.emp_tree.heading(c, text=t)
            self.emp_tree.column(c, width=w, anchor="w")
        self.emp_tree.pack(fill="both", expand=True, padx=4, pady=4)
        self.emp_tree.bind("<Double-1>", lambda e: self._edit_emp())
        ebtn = ttk.Frame(right)
        ebtn.pack(fill="x")
        ttk.Button(ebtn, text="Добавить", command=self._add_emp).pack(side="left", padx=2, pady=2)
        ttk.Button(ebtn, text="Изменить", command=self._edit_emp).pack(side="left", padx=2)
        ttk.Button(ebtn, text="Удалить", command=self._del_emp).pack(side="left", padx=2)
        ttk.Button(ebtn, text="↑", width=3, command=lambda: self._move_emp(-1)).pack(side="left", padx=2)
        ttk.Button(ebtn, text="↓", width=3, command=lambda: self._move_emp(1)).pack(side="left", padx=2)

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", pady=6)
        ttk.Button(bottom, text="Сохранить", command=self._save).pack(side="right", padx=8)
        ttk.Button(bottom, text="Закрыть без сохранения", command=self._discard).pack(side="right")
        ttk.Label(bottom, text="После изменений нажмите «Сохранить».",
                  foreground="#888").pack(side="left", padx=10)

        self._reload_depts()
        self.dirty = False  # есть несохранённые изменения
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _reload_depts(self, select=0):
        self.dept_list.delete(0, "end")
        for d in self.data["departments"]:
            self.dept_list.insert("end", d["name"])
        if self.data["departments"]:
            self.dept_list.selection_clear(0, "end")
            self.dept_list.selection_set(select)
            self.dept_list.see(select)
        self._refresh_emps()

    def _cur_dept(self):
        sel = self.dept_list.curselection()
        if not sel:
            return None
        return self.data["departments"][sel[0]]

    def _refresh_emps(self):
        self.emp_tree.delete(*self.emp_tree.get_children())
        d = self._cur_dept()
        if not d:
            return
        for emp in d["employees"]:
            self.emp_tree.insert("", "end", values=(emp["n"], emp["fio"], emp.get("tab_number", ""),
                                                    emp.get("oklad", ""), emp.get("position", "")))

    def _renumber(self, d):
        for i, emp in enumerate(d["employees"], 1):
            emp["n"] = i

    def _add_dept(self):
        dlg = DeptEditor(self, None)
        self.wait_window(dlg)
        if dlg.result:
            dlg.result["employees"] = []
            self.data["departments"].append(dlg.result)
            self.dirty = True
            self._reload_depts(len(self.data["departments"]) - 1)

    def _edit_dept(self):
        d = self._cur_dept()
        if not d:
            return
        dlg = DeptEditor(self, d)
        self.wait_window(dlg)
        if dlg.result:
            d.update(dlg.result)
            self.dirty = True
            sel = self.dept_list.curselection()[0]
            self._reload_depts(sel)

    def _del_dept(self):
        sel = self.dept_list.curselection()
        if not sel:
            return
        d = self.data["departments"][sel[0]]
        if messagebox.askyesno("Удалить отделение", f"Удалить «{d['name']}» со всеми сотрудниками?"):
            del self.data["departments"][sel[0]]
            self.dirty = True
            self._reload_depts(max(0, sel[0] - 1))

    def _selected_emp_index(self):
        sel = self.emp_tree.selection()
        if not sel:
            return None
        return self.emp_tree.index(sel[0])

    def _add_emp(self):
        d = self._cur_dept()
        if not d:
            messagebox.showinfo("Отделение", "Сначала выберите или создайте отделение.")
            return
        dlg = EmployeeEditor(self, None)
        self.wait_window(dlg)
        if dlg.result:
            d["employees"].append(dlg.result)
            self._renumber(d)
            self.dirty = True
            self._refresh_emps()

    def _edit_emp(self):
        d = self._cur_dept()
        i = self._selected_emp_index()
        if d is None or i is None:
            return
        dlg = EmployeeEditor(self, d["employees"][i])
        self.wait_window(dlg)
        if dlg.result:
            d["employees"][i].update(dlg.result)
            self.dirty = True
            self._refresh_emps()

    def _del_emp(self):
        d = self._cur_dept()
        i = self._selected_emp_index()
        if d is None or i is None:
            return
        del d["employees"][i]
        self._renumber(d)
        self.dirty = True
        self._refresh_emps()

    def _move_emp(self, delta):
        d = self._cur_dept()
        i = self._selected_emp_index()
        if d is None or i is None:
            return
        j = i + delta
        if 0 <= j < len(d["employees"]):
            d["employees"][i], d["employees"][j] = d["employees"][j], d["employees"][i]
            self._renumber(d)
            self.dirty = True
            self._refresh_emps()
            kids = self.emp_tree.get_children()
            self.emp_tree.selection_set(kids[j])

    def _save(self):
        try:
            storage.save_departments(self.data)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка сохранения",
                                 f"Не удалось сохранить изменения:\n{e}")
            return
        self.saved = True
        self.dirty = False
        messagebox.showinfo("Сохранено", "Изменения сохранены.")
        self.destroy()

    def _on_close(self):
        """Закрытие окна крестиком: предложить сохранить несохранённое."""
        if self.dirty:
            ans = messagebox.askyesnocancel(
                "Сохранить изменения?",
                "Есть несохранённые изменения. Сохранить перед закрытием?")
            if ans is None:
                return  # Отмена — остаёмся в окне
            if ans:
                self._save()
                return
        self.destroy()

    def _discard(self):
        if self.dirty and not messagebox.askyesno(
                "Закрыть без сохранения",
                "Несохранённые изменения будут потеряны. Закрыть?"):
            return
        self.destroy()


class DeptEditor(tk.Toplevel):
    def __init__(self, master, dept):
        super().__init__(master)
        self.title("Отделение")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result = None
        d = dept or {}
        self.vars = {}
        fields = [
            ("name", "Название отделения", 50),
            ("organization", "Организация (наименование)", 50),
            ("responsible_fio", "Ответственное лицо (ФИО, напр. Т.И.Иванова)", 50),
            ("responsible_position", "Должность ответственного (напр. зав. Отд. № 9)", 50),
        ]
        for i, (key, label, w) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            v = tk.StringVar(value=d.get(key, ""))
            ttk.Entry(self, textvariable=v, width=w).grid(row=i, column=1, padx=8, pady=4)
            self.vars[key] = v
        bar = ttk.Frame(self)
        bar.grid(row=len(fields), column=0, columnspan=2, pady=10)
        ttk.Button(bar, text="ОК", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="left", padx=6)

    def _ok(self):
        name = self.vars["name"].get().strip()
        if not name:
            messagebox.showerror("Название", "Укажите название отделения.")
            return
        self.result = {k: v.get().strip() for k, v in self.vars.items()}
        self.destroy()


class EmployeeEditor(tk.Toplevel):
    def __init__(self, master, emp):
        super().__init__(master)
        self.title("Сотрудник")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result = None
        e = emp or {}
        self.vars = {}
        fields = [
            ("fio", "ФИО (полностью)", str(e.get("fio", ""))),
            ("tab_number", "Табельный номер", str(e.get("tab_number", ""))),
            ("oklad", "Оклад (число)", str(e.get("oklad", ""))),
            ("position", "Должность", str(e.get("position", "соц. работник"))),
        ]
        for i, (key, label, val) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            v = tk.StringVar(value=val)
            ttk.Entry(self, textvariable=v, width=40).grid(row=i, column=1, padx=8, pady=4)
            self.vars[key] = v
        bar = ttk.Frame(self)
        bar.grid(row=len(fields), column=0, columnspan=2, pady=10)
        ttk.Button(bar, text="ОК", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="left", padx=6)

    def _ok(self):
        fio = self.vars["fio"].get().strip()
        if not fio:
            messagebox.showerror("ФИО", "Укажите ФИО сотрудника.")
            return
        oklad_raw = self.vars["oklad"].get().strip().replace(" ", "")
        try:
            oklad = int(float(oklad_raw)) if oklad_raw else ""
        except ValueError:
            messagebox.showerror("Оклад", "Оклад должен быть числом.")
            return
        self.result = {
            "fio": fio,
            "tab_number": self.vars["tab_number"].get().strip(),
            "oklad": oklad,
            "position": self.vars["position"].get().strip(),
        }
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, settings):
        super().__init__(master)
        self.title("Реквизиты и подписи")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.saved = False
        self.settings = settings
        self.vars = {}
        fields = [
            ("director_fio", "Директор (ФИО)"),
            ("director_label", "Подпись «Директор …»"),
            ("approve_line", "Строка «Утверждаю …»"),
            ("hr_specialist_line", "Строка «Специалист ОК …»"),
        ]
        for i, (key, label) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            v = tk.StringVar(value=settings.get(key, ""))
            ttk.Entry(self, textvariable=v, width=60).grid(row=i, column=1, padx=8, pady=4)
            self.vars[key] = v

        ttk.Label(self, text="Часов в рабочем дне").grid(row=10, column=0, sticky="w", padx=8, pady=4)
        self.hours_var = tk.IntVar(value=settings.get("workday_hours", 8))
        tk.Spinbox(self, from_=1, to=12, textvariable=self.hours_var, width=6).grid(
            row=10, column=1, sticky="w", padx=8
        )
        ttk.Label(self, text="Часов в предпраздничный день").grid(row=11, column=0, sticky="w", padx=8, pady=4)
        self.pre_var = tk.IntVar(value=settings.get("preholiday_hours", 7))
        tk.Spinbox(self, from_=1, to=12, textvariable=self.pre_var, width=6).grid(
            row=11, column=1, sticky="w", padx=8
        )

        bar = ttk.Frame(self)
        bar.grid(row=12, column=0, columnspan=2, pady=10)
        ttk.Button(bar, text="Сохранить", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="left", padx=6)

    def _ok(self):
        for k, v in self.vars.items():
            self.settings[k] = v.get()
        self.settings["workday_hours"] = int(self.hours_var.get())
        self.settings["preholiday_hours"] = int(self.pre_var.get())
        storage.save_settings(self.settings)
        self.saved = True
        self.destroy()


class CalendarDialog(tk.Toplevel):
    """Просмотр и правка производственного календаря по годам."""

    def __init__(self, master, calendar):
        super().__init__(master)
        self.title("Производственный календарь")
        self.geometry("560x540")
        self.transient(master)
        self.grab_set()
        self.saved = False
        self.calendar = calendar

        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="Год:").pack(side="left")
        self.year_var = tk.StringVar()
        self.year_combo = ttk.Combobox(top, textvariable=self.year_var, state="readonly", width=8)
        self.year_combo.pack(side="left", padx=6)
        self.year_combo.bind("<<ComboboxSelected>>", lambda e: self._load_year())
        ttk.Button(top, text="Добавить год", command=self._add_year).pack(side="left", padx=6)

        info = ("Формат: даты через запятую как ДД.ММ. Праздничные/перенесённые нерабочие дни — "
                "это дни, помеченные «В» (кроме обычных сб/вс). Сокращённые — рабочие дни на 1 час короче. "
                "Перенесённые рабочие дни — рабочая суббота/среда по переносу (для «Проезда» именно так "
                "среда становится рабочей).")
        ttk.Label(self, text=info, wraplength=520, foreground="#444").pack(fill="x", padx=8)

        ttk.Label(self, text="Нерабочие праздничные и перенесённые дни:").pack(anchor="w", padx=8, pady=(8, 0))
        self.hol_text = tk.Text(self, height=6, width=64)
        self.hol_text.pack(fill="x", padx=8)
        ttk.Label(self, text="Сокращённые предпраздничные дни (−1 час):").pack(anchor="w", padx=8, pady=(8, 0))
        self.short_text = tk.Text(self, height=3, width=64)
        self.short_text.pack(fill="x", padx=8)
        ttk.Label(self, text="Перенесённые РАБОЧИЕ дни (рабочая суббота/среда):").pack(anchor="w", padx=8, pady=(8, 0))
        self.work_text = tk.Text(self, height=3, width=64)
        self.work_text.pack(fill="x", padx=8)

        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", pady=8)
        ttk.Button(bar, text="Сохранить", command=self._save).pack(side="right", padx=8)
        ttk.Button(bar, text="Закрыть", command=self.destroy).pack(side="right")

        self._reload_years()

    def _reload_years(self):
        years = sorted(self.calendar.keys())
        self.year_combo["values"] = years
        if years:
            self.year_combo.current(len(years) - 1)
            self._load_year()

    def _fmt(self, items):
        # "MM-DD" -> "DD.MM"
        out = []
        for s in items:
            try:
                m, d = s.split("-")
                out.append(f"{int(d):02d}.{int(m):02d}")
            except ValueError:
                out.append(s)
        return ", ".join(out)

    def _parse(self, text):
        res = []
        for token in text.replace("\n", ",").split(","):
            token = token.strip()
            if not token:
                continue
            try:
                d, m = token.split(".")[:2]
                res.append(f"{int(m):02d}-{int(d):02d}")
            except ValueError:
                raise ValueError(f"Не разобрать дату: «{token}» (нужен формат ДД.ММ)")
        return sorted(set(res))

    def _load_year(self):
        y = self.year_var.get()
        data = self.calendar.get(y, {})
        self.hol_text.delete("1.0", "end")
        self.hol_text.insert("1.0", self._fmt(data.get("holidays", [])))
        self.short_text.delete("1.0", "end")
        self.short_text.insert("1.0", self._fmt(data.get("short_days", [])))
        self.work_text.delete("1.0", "end")
        self.work_text.insert("1.0", self._fmt(data.get("work_days", [])))

    def _add_year(self):
        from tkinter.simpledialog import askinteger
        y = askinteger("Новый год", "Введите год (например, 2027):", parent=self,
                       minvalue=2024, maxvalue=2100)
        if y:
            self.calendar.setdefault(str(y), {"holidays": [], "short_days": [], "work_days": []})
            self._reload_years()
            self.year_combo.set(str(y))
            self._load_year()

    def _save(self):
        y = self.year_var.get()
        if not y:
            return
        try:
            hol = self._parse(self.hol_text.get("1.0", "end"))
            short = self._parse(self.short_text.get("1.0", "end"))
            work = self._parse(self.work_text.get("1.0", "end"))
        except ValueError as e:
            messagebox.showerror("Ошибка формата", str(e))
            return
        self.calendar[y] = {"holidays": hol, "short_days": short, "work_days": work}
        storage.save_calendar(self.calendar)
        self.saved = True
        messagebox.showinfo("Сохранено", f"Календарь на {y} год сохранён.")


def open_timesheet(master):
    """Открыть окно функции «Табель» (вызывается из главного меню)."""
    return TimesheetWindow(master)


def run():
    """Запуск функции отдельно (без главного меню) — для разработки/тестов."""
    root = tk.Tk()
    root.withdraw()
    win = TimesheetWindow(root)
    win.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
