"""Представление (View) функции «Услуги-Деньги» — Tkinter (тонкий слой)."""

import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import FEATURE_TITLE, service
from .service import MONTHS
from ...core import documents, feedback, ui_state


class UslugiDengiWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Услуги-Деньги")
        self.geometry("860x400")
        self.minsize(760, 340)
        self._data = None
        self.f071 = tk.StringVar()
        self.fben = tk.StringVar()
        self.fprev = tk.StringVar()
        today = datetime.date.today()
        self.month_var = tk.StringVar(value=MONTHS[today.month].capitalize())
        self.year_var = tk.IntVar(value=today.year)
        self.dept_var = tk.StringVar(value="9")
        self.info = tk.StringVar(value="Отчёт накопительный: H/I/J (частичная/бесплатно) = прошлый месяц + новые. "
                                       "Прошлый отчёт можно указать вручную; иначе берётся из архива.")
        self._build()

    def _build(self):
        pad = {"padx": 8, "pady": 5}
        fr = ttk.LabelFrame(self, text="Входные файлы")
        fr.pack(fill="x", **pad)
        g = ttk.Frame(fr)
        g.pack(fill="x", padx=6, pady=4)
        ttk.Label(g, text="Отчёт по количеству услуг (071), .xls:").grid(row=0, column=0, sticky="w")
        ttk.Entry(g, textvariable=self.f071, width=60).grid(row=0, column=1, padx=4)
        ttk.Button(g, text="Обзор…", command=self._pick_071).grid(row=0, column=2)
        ttk.Label(g, text="Бесплатники-частичники, .xlsx/.xls:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(g, textvariable=self.fben, width=60).grid(row=1, column=1, padx=4)
        ttk.Button(g, text="Обзор…", command=self._pick_ben).grid(row=1, column=2)
        ttk.Label(g, text="Отчёт за прошлый месяц (необязательно):").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(g, textvariable=self.fprev, width=60).grid(row=2, column=1, padx=4)
        ttk.Button(g, text="Обзор…", command=self._pick_prev).grid(row=2, column=2)

        pr = ttk.Frame(self)
        pr.pack(fill="x", **pad)
        ttk.Label(pr, text="Месяц:").pack(side="left")
        ttk.Combobox(pr, textvariable=self.month_var, state="readonly", width=12,
                     values=[m.capitalize() for m in MONTHS[1:]]).pack(side="left", padx=4)
        ttk.Label(pr, text="Год:").pack(side="left", padx=(8, 0))
        tk.Spinbox(pr, from_=2024, to=2035, textvariable=self.year_var, width=6).pack(side="left", padx=4)
        ttk.Label(pr, text="Отделение №:").pack(side="left", padx=(8, 0))
        ttk.Entry(pr, textvariable=self.dept_var, width=5).pack(side="left", padx=4)

        ttk.Label(self, textvariable=self.info, foreground="#555", wraplength=780,
                  justify="left").pack(fill="x", padx=10, pady=6)

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        self.gen_btn = ttk.Button(bottom, text="Сформировать (.xlsx)", command=self._generate)
        self.gen_btn.pack(side="right")
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    def _pick_071(self):
        f = filedialog.askopenfilename(title="Отчёт 071",
                                       initialdir=ui_state.last_dir("open") or None,
                                       filetypes=[("Excel 97-2003", "*.xls"), ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.f071.set(f)

    def _pick_ben(self):
        f = filedialog.askopenfilename(title="Бесплатники-частичники",
                                       initialdir=ui_state.last_dir("open") or None,
                                       filetypes=[("Excel", "*.xlsx *.xls"), ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.fben.set(f)

    def _pick_prev(self):
        f = filedialog.askopenfilename(title="Отчёт «Услуги-Деньги» за прошлый месяц",
                                       initialdir=ui_state.last_dir("open") or None,
                                       filetypes=[("Excel", "*.xlsx *.xls"), ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.fprev.set(f)

    def _month_num(self):
        m = self.month_var.get().strip().lower()
        return MONTHS.index(m) if m in MONTHS else 0

    def _generate(self):
        p071, pben = self.f071.get().strip(), self.fben.get().strip()
        if not p071 or not os.path.exists(p071):
            messagebox.showwarning("Нет файла", "Укажите отчёт 071 (.xls).")
            return
        if not pben or not os.path.exists(pben):
            messagebox.showwarning("Нет файла", "Укажите файл бесплатники-частичники (.xlsx).")
            return
        year = int(self.year_var.get())
        month = self._month_num()
        # Предыдущий отчёт: указанный вручную или авто-поиск в архиве (прошлый месяц).
        prev_path = self.fprev.get().strip()
        prev_auto = False
        if not prev_path or not os.path.exists(prev_path):
            prev_path = service.find_prev_report(month, year) or ""
            prev_auto = bool(prev_path)
        self.info.set("Чтение и формирование…")
        self.gen_btn.config(state="disabled")
        self.update_idletasks()
        try:
            data = service.prepare(p071, pben, prev_path or None)
        except Exception as e:  # noqa: BLE001
            self.gen_btn.config(state="normal")
            self.info.set("")
            messagebox.showerror("Ошибка чтения", str(e))
            return
        default = f"Услуги-Деньги_{self.month_var.get()}_{year}.xlsx"
        out = filedialog.asksaveasfilename(title="Сохранить как…", defaultextension=".xlsx",
                                           initialfile=default,
                                           initialdir=ui_state.last_dir("save") or None,
                                           filetypes=[("Книга Excel", "*.xlsx")])
        if not out:
            self.gen_btn.config(state="normal")
            self.info.set("")
            return
        ui_state.set_last_dir(out, "save")
        try:
            service.generate(data, out, month, year, self.dept_var.get().strip() or "9")
            documents.save_file("uslugi_dengi", out, {"month": month, "year": year})
        except Exception as e:  # noqa: BLE001
            self.gen_btn.config(state="normal")
            messagebox.showerror("Ошибка формирования", str(e))
            return
        self.gen_btn.config(state="normal")
        free = len(data.get("free_clients", []))
        part = len(data.get("part_cnt_clients", []))
        if data.get("prev_ud"):
            base = "из прошлого отчёта (архив)" if prev_auto else "из указанного отчёта"
            base_note = f" Накоплено к значениям {base}."
        else:
            base_note = " Прошлый отчёт не найден — значения только за текущий месяц."
        self.info.set(f"Готово. Бесплатников: {free}, частичников: {part}.{base_note} Файл: {out}")
        if messagebox.askyesno("Готово", f"Файл сохранён:\n{out}\n\nОткрыть?"):
            try:
                os.startfile(out)
            except Exception:  # noqa: BLE001
                pass


def open_uslugi_dengi(master):
    return UslugiDengiWindow(master)
