"""Представление (View) «Графика проверок» — Tkinter (тонкий слой)."""

import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import FEATURE_TITLE, service, storage
from .service import DEFAULTS
from ...core import documents, feedback, ui_state


class GrafikiWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("График проверок")
        self.geometry("640x620")
        self.minsize(560, 520)
        self.departments = storage.list_departments()
        self._self_vars = {}        # fio -> BooleanVar (самоконтроль)
        today = datetime.date.today()
        self.dept_var = tk.StringVar()
        self.half_var = tk.IntVar(value=1 if today.month <= 6 else 2)
        self.year_var = tk.IntVar(value=today.year)
        self.dept_no_var = tk.StringVar(value=DEFAULTS["dept_no"])
        self.director_var = tk.StringVar(value=DEFAULTS["director"])
        self.zav_var = tk.StringVar(value=DEFAULTS["zav"])
        self.info = tk.StringVar(value="Отметьте «самоконтроль» у нужных соцработников и сформируйте график.")
        self._build()
        self._reload_combo()

    def _build(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Отделение:").grid(row=0, column=0, sticky="w")
        self.dept_combo = ttk.Combobox(top, textvariable=self.dept_var, state="readonly", width=44)
        self.dept_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.dept_combo.bind("<<ComboboxSelected>>", lambda e: self._reload_workers())
        ttk.Label(top, text="Полугодие:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        hf = ttk.Frame(top)
        hf.grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Radiobutton(hf, text="1-е (янв–июнь)", value=1, variable=self.half_var).pack(side="left")
        ttk.Radiobutton(hf, text="2-е (июль–дек)", value=2, variable=self.half_var).pack(side="left", padx=(8, 0))
        ttk.Label(hf, text="Год:").pack(side="left", padx=(12, 0))
        tk.Spinbox(hf, from_=2024, to=2035, textvariable=self.year_var, width=6).pack(side="left", padx=4)

        req = ttk.Frame(self)
        req.pack(fill="x", **pad)
        ttk.Label(req, text="Отд. №:").pack(side="left")
        ttk.Entry(req, textvariable=self.dept_no_var, width=5).pack(side="left", padx=(2, 10))
        ttk.Label(req, text="Директор:").pack(side="left")
        ttk.Entry(req, textvariable=self.director_var, width=18).pack(side="left", padx=(2, 10))
        ttk.Label(req, text="Зав.:").pack(side="left")
        ttk.Entry(req, textvariable=self.zav_var, width=16).pack(side="left", padx=2)

        box = ttk.LabelFrame(self, text="Соцработники (отметьте «самоконтроль»)")
        box.pack(fill="both", expand=True, **pad)
        canvas = tk.Canvas(box, borderwidth=0, highlightthickness=0)
        sb = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._wlist = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=self._wlist, anchor="nw")
        self._wlist.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))

        ttk.Label(self, textvariable=self.info, foreground="#555", wraplength=600,
                  justify="left").pack(fill="x", padx=10)
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        self.gen_btn = ttk.Button(bottom, text="Сформировать (.xlsx)", command=self._generate)
        self.gen_btn.pack(side="right")
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    def _reload_combo(self):
        names = [d["name"] for d in self.departments]
        self.dept_combo["values"] = names
        if self.departments:
            self.dept_combo.current(ui_state.dept_index("grafiki", names))
            self._reload_workers()

    def _current_dept(self):
        i = self.dept_combo.current()
        return self.departments[i] if 0 <= i < len(self.departments) else None

    def _reload_workers(self):
        for w in self._wlist.winfo_children():
            w.destroy()
        self._self_vars = {}
        dept = self._current_dept()
        if not dept:
            return
        if "№" in dept.get("name", ""):
            self.dept_no_var.set(dept["name"].split("№")[-1].strip())
        for fio in storage.soc_workers(dept["id"]):
            var = tk.BooleanVar(value=False)
            self._self_vars[fio] = var
            row = ttk.Frame(self._wlist)
            row.pack(fill="x", anchor="w")
            ttk.Label(row, text=fio, width=36, anchor="w").pack(side="left", padx=(4, 6))
            ttk.Checkbutton(row, text="самоконтроль", variable=var).pack(side="left")

    def _generate(self):
        if not self._self_vars:
            messagebox.showwarning("Нет соцработников", "В отделении нет соцработников.")
            return
        workers = [{"fio": fio, "self_control": var.get()}
                   for fio, var in self._self_vars.items()]
        half, year = self.half_var.get(), int(self.year_var.get())
        default = f"График_проверок_{half}-полугодие_{year}.xlsx"
        out = filedialog.asksaveasfilename(title="Сохранить как…", defaultextension=".xlsx",
                                           initialfile=default,
                                           initialdir=ui_state.last_dir("save") or None,
                                           filetypes=[("Книга Excel", "*.xlsx")])
        if not out:
            return
        ui_state.set_last_dir(out, "save")
        ui_state.set_last_dept("grafiki", self.dept_var.get())
        self.gen_btn.config(state="disabled")
        self.update_idletasks()
        try:
            service.generate(out, workers, half, year, self.dept_no_var.get().strip(),
                             self.director_var.get().strip(), self.zav_var.get().strip())
            documents.save_file("grafiki", out, {"half": half, "year": year,
                                                 "dept": self.dept_no_var.get().strip()})
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


def open_grafiki(master):
    return GrafikiWindow(master)
