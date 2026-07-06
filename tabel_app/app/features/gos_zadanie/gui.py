"""Представление (View) «Отчёта по госзаданию» — Tkinter (тонкий слой)."""

import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import FEATURE_TITLE, service, storage
from .service import DEFAULT_ZAV, MONTHS
from ...core import documents, feedback, ui_state


def _resolve_worker(source_name, db_list):
    """Подобрать полное ФИО из базы по фамилии из источника (иначе вернуть как есть)."""
    s = (source_name or "").strip()
    if not s:
        return s
    surname = s.split()[0].rstrip(".,")
    for full in db_list:
        if full.strip().lower().startswith(surname.lower()):
            return full.strip()
    return s


class GosZadanieWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title(FEATURE_TITLE)
        self.geometry("780x420")
        self.minsize(700, 380)
        self._prepared = None
        self._workers = storage.soc_worker_fios()
        today = datetime.date.today()
        self.src_var = tk.StringVar()
        self.worker_var = tk.StringVar()
        self.dept_var = tk.StringVar(value="9")
        self.zav_var = tk.StringVar(value=DEFAULT_ZAV)
        self.month_var = tk.StringVar(value=MONTHS[today.month].capitalize())
        self.year_var = tk.IntVar(value=today.year)
        self.info = tk.StringVar(value="Выберите файл «Отчёт по количеству оказанных услуг … "
                                       "в разбивке» и нажмите «Подготовить».")
        self._build()

    def _build(self):
        pad = {"padx": 8, "pady": 5}
        fr = ttk.LabelFrame(self, text="Источник данных")
        fr.pack(fill="x", **pad)
        g = ttk.Frame(fr)
        g.pack(fill="x", padx=6, pady=4)
        ttk.Label(g, text="Отчёт по количеству услуг (.xls):").grid(row=0, column=0, sticky="w")
        ttk.Entry(g, textvariable=self.src_var, width=58).grid(row=0, column=1, padx=4)
        ttk.Button(g, text="Обзор…", command=self._pick_source).grid(row=0, column=2)
        ttk.Button(g, text="Подготовить", command=self._prepare).grid(row=0, column=3, padx=6)

        req = ttk.LabelFrame(self, text="Реквизиты (заполняются из файла, можно править)")
        req.pack(fill="x", **pad)
        r = ttk.Frame(req)
        r.pack(fill="x", padx=6, pady=4)
        ttk.Label(r, text="Соцработник:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(r, textvariable=self.worker_var, width=38,
                     values=self._workers).grid(row=0, column=1, columnspan=3, sticky="w", padx=4)
        ttk.Label(r, text="Отделение №:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(r, textvariable=self.dept_var, width=6).grid(row=1, column=1, sticky="w", padx=4, pady=(4, 0))
        ttk.Label(r, text="Зав. отделением:").grid(row=1, column=2, sticky="w", pady=(4, 0))
        ttk.Entry(r, textvariable=self.zav_var, width=22).grid(row=1, column=3, sticky="w", padx=4, pady=(4, 0))
        ttk.Label(r, text="Месяц:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Combobox(r, textvariable=self.month_var, state="readonly", width=12,
                     values=[m.capitalize() for m in MONTHS[1:]]).grid(row=2, column=1, sticky="w", padx=4, pady=(4, 0))
        ttk.Label(r, text="Год:").grid(row=2, column=2, sticky="w", pady=(4, 0))
        tk.Spinbox(r, from_=2024, to=2035, textvariable=self.year_var, width=6).grid(
            row=2, column=3, sticky="w", padx=4, pady=(4, 0))

        ttk.Label(self, textvariable=self.info, foreground="#555", wraplength=740,
                  justify="left").pack(fill="x", padx=10, pady=6)

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        self.gen_btn = ttk.Button(bottom, text="Сформировать (.ods)", command=self._generate,
                                  state="disabled")
        self.gen_btn.pack(side="right")
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    def _pick_source(self):
        f = filedialog.askopenfilename(title="Отчёт по количеству оказанных услуг",
                                       initialdir=ui_state.last_dir("open") or None,
                                       filetypes=[("Excel 97-2003", "*.xls"), ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.src_var.set(f)

    def _month_num(self):
        m = self.month_var.get().strip().lower()
        return MONTHS.index(m) if m in MONTHS else datetime.date.today().month

    def _prepare(self):
        path = self.src_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Нет файла", "Укажите файл-источник (.xls).")
            return
        self.info.set("Чтение файла…")
        self.update_idletasks()
        try:
            self._prepared = service.prepare(path)
        except Exception as e:  # noqa: BLE001
            self.info.set("")
            messagebox.showerror("Ошибка чтения", str(e))
            return
        p = self._prepared
        self.worker_var.set(_resolve_worker(p.get("worker"), self._workers))
        if p.get("dept"):
            self.dept_var.set(p["dept"])
        if p.get("month"):
            self.month_var.set(MONTHS[p["month"]].capitalize())
        if p.get("year"):
            self.year_var.set(p["year"])
        msg = (f"Получателей: {len(p['clients'])}; основных услуг: {len(p['main_services'])}, "
               f"дополнительных: {len(p['dop_services'])}.")
        if p.get("new_services"):
            msg += (f" Новые услуги (добавлены как «дополнительные», можно переклассифицировать "
                    f"в справочнике): {', '.join(p['new_services'])}.")
        self.info.set(msg)
        self.gen_btn.config(state="normal")

    def _generate(self):
        if not self._prepared:
            return
        worker = self.worker_var.get().strip()
        if not worker:
            messagebox.showwarning("Не заполнено", "Укажите соцработника.")
            return
        default = f"Отчёт_госзадание_{worker.split()[0]}_{self.month_var.get()}_{self.year_var.get()}.ods"
        out = filedialog.asksaveasfilename(title="Сохранить как…", defaultextension=".ods",
                                           initialfile=default,
                                           initialdir=ui_state.last_dir("save") or None,
                                           filetypes=[("OpenDocument Spreadsheet", "*.ods")])
        if not out:
            return
        ui_state.set_last_dir(out, "save")
        self.gen_btn.config(state="disabled")
        self.update_idletasks()
        try:
            service.generate(self._prepared, out, worker=worker,
                             dept=self.dept_var.get().strip(), month=self._month_num(),
                             year=int(self.year_var.get()), zav=self.zav_var.get().strip())
            documents.save_file("gos_zadanie", out, {"worker": worker,
                                                     "month": self._month_num(),
                                                     "year": int(self.year_var.get()),
                                                     "dept": self.dept_var.get().strip()})
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


def open_gos_zadanie(master):
    return GosZadanieWindow(master)
