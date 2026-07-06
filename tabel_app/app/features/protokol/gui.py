"""Представление (View) «Протокола» — Tkinter (тонкий слой)."""

import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import FEATURE_TITLE, service, storage
from .service import DEFAULTS, MONTHS_NOM
from ...core import documents, feedback, ui_state


class ProtokolWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Протокол")
        self.geometry("700x720")
        self.minsize(620, 600)
        self.departments = storage.list_departments()
        self._att_vars = {}        # fio -> BooleanVar (присутствовал)
        today = datetime.date.today()
        self.dept_var = tk.StringVar()
        self.number_var = tk.StringVar(value="1")
        self.month_var = tk.StringVar(value=MONTHS_NOM[today.month])
        self.year_var = tk.IntVar(value=today.year)
        self.date_var = tk.StringVar()
        self.dept_no_var = tk.StringVar(value=DEFAULTS["dept_no"])
        self.zav_var = tk.StringVar(value=DEFAULTS["zav"])
        self.info = tk.StringVar(
            value="Дата ставится автоматически (последняя рабочая среда месяца), повестка — из плана "
                  "методчаса. Снимите галочки у отсутствующих и сформируйте протокол.")
        self._build()
        self._reload_combo()
        self._update_date()
        self._fill_body_default()

    def _build(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Отделение:").grid(row=0, column=0, sticky="w")
        self.dept_combo = ttk.Combobox(top, textvariable=self.dept_var, state="readonly", width=44)
        self.dept_combo.grid(row=0, column=1, columnspan=3, sticky="w", padx=6)
        self.dept_combo.bind("<<ComboboxSelected>>", lambda e: self._reload_workers())

        ttk.Label(top, text="Месяц:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        mcombo = ttk.Combobox(top, textvariable=self.month_var, state="readonly", width=12,
                              values=list(MONTHS_NOM[1:]))
        mcombo.grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        mcombo.bind("<<ComboboxSelected>>", lambda e: self._on_period_change())
        ttk.Label(top, text="Год:").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ysp = tk.Spinbox(top, from_=2024, to=2035, textvariable=self.year_var, width=6,
                         command=self._on_period_change)
        ysp.grid(row=1, column=3, sticky="w", padx=6, pady=(6, 0))

        ttk.Label(top, text="№ протокола:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(top, textvariable=self.number_var, width=8).grid(row=2, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(top, text="Дата (авто):").grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(top, textvariable=self.date_var, width=12).grid(row=2, column=3, sticky="w", padx=6, pady=(6, 0))

        req = ttk.Frame(self)
        req.pack(fill="x", **pad)
        ttk.Label(req, text="Отд. №:").pack(side="left")
        ttk.Entry(req, textvariable=self.dept_no_var, width=5).pack(side="left", padx=(2, 12))
        ttk.Label(req, text="Зав. отделением:").pack(side="left")
        ttk.Entry(req, textvariable=self.zav_var, width=22).pack(side="left", padx=2)

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, **pad)

        box = ttk.LabelFrame(mid, text="Присутствовали (снимите отсутствующих)")
        box.pack(side="left", fill="both", expand=True)
        canvas = tk.Canvas(box, borderwidth=0, highlightthickness=0, width=260)
        sb = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._wlist = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=self._wlist, anchor="nw")
        self._wlist.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))

        bodybox = ttk.LabelFrame(mid, text="Повестка дня / решения / Разное")
        bodybox.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.body_text = tk.Text(bodybox, wrap="word", width=42, height=18)
        bsb = ttk.Scrollbar(bodybox, orient="vertical", command=self.body_text.yview)
        self.body_text.configure(yscrollcommand=bsb.set)
        bsb.pack(side="right", fill="y")
        self.body_text.pack(side="left", fill="both", expand=True)

        ttk.Label(self, textvariable=self.info, foreground="#555", wraplength=660,
                  justify="left").pack(fill="x", padx=10)
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        self.gen_btn = ttk.Button(bottom, text="Сформировать (.odt)", command=self._generate)
        self.gen_btn.pack(side="right")
        ttk.Button(bottom, text="Повестка из плана", command=self._fill_body_default).pack(side="right", padx=6)
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    def _month_num(self):
        m = self.month_var.get().strip()
        return MONTHS_NOM.index(m) if m in MONTHS_NOM else datetime.date.today().month

    def _on_period_change(self):
        self._update_date()
        self._fill_body_default()

    def _update_date(self):
        try:
            d = service.last_working_wednesday(int(self.year_var.get()), self._month_num())
            self.date_var.set(service.format_date(d))
        except Exception:  # noqa: BLE001
            pass

    def _fill_body_default(self):
        self.body_text.delete("1.0", "end")
        self.body_text.insert("1.0", service.default_body(self._month_num(), self.zav_var.get().strip()))

    def _reload_combo(self):
        names = [d["name"] for d in self.departments]
        self.dept_combo["values"] = names
        if self.departments:
            self.dept_combo.current(ui_state.dept_index("protokol", names))
            self._reload_workers()

    def _current_dept(self):
        i = self.dept_combo.current()
        return self.departments[i] if 0 <= i < len(self.departments) else None

    def _reload_workers(self):
        for w in self._wlist.winfo_children():
            w.destroy()
        self._att_vars = {}
        dept = self._current_dept()
        if not dept:
            return
        if "№" in dept.get("name", ""):
            self.dept_no_var.set(dept["name"].split("№")[-1].strip())
        for fio in storage.soc_workers(dept["id"]):
            var = tk.BooleanVar(value=True)   # по умолчанию присутствуют все
            self._att_vars[fio] = var
            ttk.Checkbutton(self._wlist, text=fio, variable=var).pack(fill="x", anchor="w", padx=4)

    def _generate(self):
        attendees = [fio for fio, var in self._att_vars.items() if var.get()]
        absentees = [fio for fio, var in self._att_vars.items() if not var.get()]
        if not attendees:
            messagebox.showwarning("Нет присутствующих", "Отметьте хотя бы одного присутствующего.")
            return
        number = self.number_var.get().strip()
        date_str = self.date_var.get().strip()
        if not number or not date_str:
            messagebox.showwarning("Не заполнено", "Укажите № протокола и дату совещания.")
            return
        default = f"Протокол_{number}_отд_{self.dept_no_var.get().strip()}.odt"
        out = filedialog.asksaveasfilename(title="Сохранить как…", defaultextension=".odt",
                                           initialfile=default,
                                           initialdir=ui_state.last_dir("save") or None,
                                           filetypes=[("Документ OpenDocument", "*.odt")])
        if not out:
            return
        ui_state.set_last_dir(out, "save")
        ui_state.set_last_dept("protokol", self.dept_var.get())
        body = self.body_text.get("1.0", "end").rstrip("\n")
        self.gen_btn.config(state="disabled")
        self.update_idletasks()
        try:
            service.generate(out, number, date_str, attendees, body,
                             self.dept_no_var.get().strip(), self.zav_var.get().strip(), absentees)
            documents.save_file("protokol", out, {"number": number, "date": date_str,
                                                  "dept": self.dept_no_var.get().strip(),
                                                  "month": self._month_num(), "year": int(self.year_var.get())})
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


def open_protokol(master):
    return ProtokolWindow(master)
