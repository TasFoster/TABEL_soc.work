"""Представление (View) функции «Проезд» — Tkinter.

Тонкий слой: ввод/отображение и вызовы контроллера (service). Бизнес-логика
(подготовка строк, даты из файла поездок, нормализация серий, цена, запись .ods) —
в app/features/proezd/service.py."""

import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...core.desktop import open_path
from . import FEATURE_KEY, FEATURE_TITLE, service, storage
from ...core import checklist_gui, documents, feedback, ui_state

# Колонки таблицы = ключи строки (service.ROW_KEYS) + заголовки/ширины.
COLUMNS = [("num", "№", 36), ("date", "Дата", 92), ("frm", "Откуда", 230),
           ("to", "Куда", 230), ("purpose", "Цель", 170),
           ("number", "№ билета", 90), ("series", "Серия", 80), ("price", "Цена", 60)]
EDITABLE = ("date", "frm", "to", "purpose", "number", "series", "price")


class ProezdWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Проезд — компенсация")
        self.geometry("1180x660")
        self.minsize(1000, 560)
        self.settings = storage.load_settings()
        self._header = {}
        self._lexicon = {}                  # словарь подсказок по колонкам
        self._save_edit = None
        self._forms_worker = ""
        self.trips_var = tk.StringVar()
        self.worker_var = tk.StringVar()
        self.gen_var = tk.StringVar()
        self.short_var = tk.StringVar()
        today = datetime.date.today()
        months = self.settings.get("months_upper", [""] * 13)
        self.month_var = tk.StringVar(value=months[today.month] if len(months) > today.month else "")
        self.year_var = tk.IntVar(value=today.year)
        self.info_var = tk.StringVar(value="Загрузите отчёт, заполните по графику или добавьте поездки вручную.")
        self.total_var = tk.StringVar(value="Сумма: 0 ₽")
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.LabelFrame(self, text="Входные данные")
        top.pack(fill="x", **pad)
        fr = ttk.Frame(top)
        fr.pack(fill="x", padx=6, pady=4)
        ttk.Label(fr, text="Файл с поездками:").grid(row=0, column=0, sticky="w")
        ttk.Entry(fr, textvariable=self.trips_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(fr, text="Обзор…", command=self._pick_trips).grid(row=0, column=2)
        ttk.Button(fr, text="Прочитать", command=self._read).grid(row=0, column=3, padx=10)
        fr.columnconfigure(1, weight=1)

        # период (месяц/год) + ФИО
        prm = ttk.Frame(self)
        prm.pack(fill="x", **pad)
        ttk.Label(prm, text="Месяц:").pack(side="left")
        months = self.settings.get("months_upper", [])
        self.month_combo = ttk.Combobox(prm, textvariable=self.month_var, state="readonly",
                                        values=[m for m in months if m], width=12)
        self.month_combo.pack(side="left", padx=4)
        ttk.Label(prm, text="Год:").pack(side="left", padx=(8, 0))
        tk.Spinbox(prm, from_=2024, to=2035, textvariable=self.year_var, width=6).pack(side="left", padx=4)
        ttk.Button(prm, text="Заполнить по графику", command=self._fill_schedule).pack(side="left", padx=12)

        nm = ttk.LabelFrame(self, text="Заявление — ФИО соцработника")
        nm.pack(fill="x", **pad)
        nf = ttk.Frame(nm)
        nf.pack(fill="x", padx=6, pady=4)
        ttk.Label(nf, text="Полное ФИО:").grid(row=0, column=0, sticky="w")
        worker = ttk.Entry(nf, textvariable=self.worker_var, width=40)
        worker.grid(row=0, column=1, sticky="ew", padx=4, pady=(0, 3))
        worker.bind("<FocusOut>", self._update_worker_forms)
        worker.bind("<Return>", self._update_worker_forms)
        ttk.Label(nf, text="Родительный падеж:").grid(row=1, column=0, sticky="w")
        ttk.Entry(nf, textvariable=self.gen_var, width=40).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Label(nf, text="Кратко (Фамилия И.О.):").grid(row=1, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(nf, textvariable=self.short_var, width=22).grid(row=1, column=3, padx=4)

        mid = ttk.LabelFrame(self, text="Поездки — двойной клик по ячейке для правки (серия меняет цену)")
        cols = [c[0] for c in COLUMNS] + ["dop"]   # dop — скрытая служебная колонка
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse",
                                 displaycolumns=[c[0] for c in COLUMNS])
        for key, title, width in COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width,
                             anchor="w" if key in ("frm", "to", "purpose") else "center")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.tree.bind("<Double-1>", self._edit_cell)

        rowbtns = ttk.Frame(self)
        rowbtns.pack(fill="x", **pad)
        ttk.Button(rowbtns, text="+ Строка", command=self._add_row).pack(side="left")
        ttk.Button(rowbtns, text="− Строка", command=self._del_row).pack(side="left", padx=4)
        ttk.Label(rowbtns, text="(новая строка добавляется после выделенной)",
                  foreground="#888").pack(side="left", padx=8)
        info = ttk.Label(self, textvariable=self.info_var, foreground="#555", justify="left")
        info.pack(fill="x", padx=10)
        info.bind("<Configure>", lambda ev: info.configure(wraplength=ev.width))

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        ttk.Label(bottom, textvariable=self.total_var, font=("", 10, "bold")).pack(side="left")
        self.gen_btn = ttk.Button(bottom, text="Сформировать отчёт", command=self._generate,
                                  state="disabled")
        self.gen_btn.pack(side="right")
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)
        checklist_gui.add_button(bottom, self, FEATURE_KEY, FEATURE_TITLE, side="left", padx=0)
        mid.pack(before=rowbtns, fill="both", expand=True, **pad)

    # --------------------------------------------------------------- helpers
    def _selected_month(self):
        months = [m.upper() for m in self.settings.get("months_upper", [])]
        mu = self.month_var.get().strip().upper()
        return months.index(mu) if mu in months else 0

    def _selected_year(self):
        try:
            return int(self.year_var.get())
        except (tk.TclError, ValueError):
            return datetime.date.today().year

    def _update_worker_forms(self, event=None):
        worker = self.worker_var.get().strip()
        if worker != self._forms_worker:
            forms = storage.forms_for(worker)
            self.gen_var.set(forms["genitive"])
            self.short_var.set(forms["short"])
            self._forms_worker = worker

    def _fill_table(self, rows):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(rows, 1):
            self.tree.insert("", "end", values=(
                i, r.get("date", ""), r.get("frm", ""), r.get("to", ""),
                r.get("purpose", ""), r.get("number", ""), r.get("series", ""),
                r.get("price", ""), "1" if r.get("dop") else ""))
        self._recalc_total()

    def _collect_rows(self):
        rows = []
        for i, iid in enumerate(self.tree.get_children(), 1):
            # читаем КАЖДУЮ ячейку через tree.set (строкой!) — иначе Tkinter превращает
            # «0123456» в число и теряет ведущий ноль в номере билета
            d = {k: self.tree.set(iid, k) for k, _t, _w in COLUMNS}
            try:
                d["price"] = service.parse_price(d.get("price") or 0)
            except ValueError:
                d["price"] = 0
            d["num"] = i
            d["number"] = str(d.get("number", "")).strip()
            d["series"] = str(d.get("series", "")).strip()
            d["dop"] = str(self.tree.set(iid, "dop")) == "1"
            rows.append(d)
        return rows

    def _renumber(self):
        for i, iid in enumerate(self.tree.get_children(), 1):
            self.tree.set(iid, "num", i)

    # --------------------------------------------------------------- actions
    def _pick_trips(self):
        f = filedialog.askopenfilename(title="Файл с поездками",
                                       initialdir=ui_state.last_dir("open") or None,
                                       filetypes=[("Таблицы", "*.ods *.xls *.xlsx"),
                                                  ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.trips_var.set(f)

    def _read(self):
        if not self._finish_edit():
            return
        tp = self.trips_var.get().strip()
        if not tp or not os.path.exists(tp):
            messagebox.showwarning("Нет файла", "Укажите файл с поездками.")
            return
        self.info_var.set("Чтение…")
        self.update_idletasks()
        try:
            prepared = service.prepare(tp)
        except Exception as e:  # noqa: BLE001
            self.info_var.set("")
            messagebox.showerror("Ошибка чтения", str(e))
            return

        header = prepared["header"]
        self._header = header
        # предзаполнить месяц/год из шапки файла
        mu = (header.get("month_upper", "") or "").strip().upper()
        months = [m.upper() for m in self.settings.get("months_upper", [])]
        if mu in months:
            self.month_var.set(self.settings["months_upper"][months.index(mu)])
        ys = str(header.get("year", "")).strip()
        if ys.isdigit():
            self.year_var.set(int(ys))
        self.worker_var.set(header.get("worker_full", ""))
        self._forms_worker = None
        self._update_worker_forms()

        rows, note = service.build_rows(prepared, self._selected_year(),
                                        self._selected_month(), self.settings)
        self._fill_table(rows)
        self._lexicon = service.build_lexicon(rows, self.settings)  # подсказки
        self.info_var.set(f"Загружено поездок: {len(rows)}. {note}")
        self.gen_btn.config(state="normal" if rows else "disabled")

    def _fill_schedule(self):
        if not self._finish_edit():
            return
        current = self._collect_rows()
        if current and not messagebox.askyesno(
                "Заполнение по графику",
                "Заменить строки таблицы поездками по графику на выбранный месяц? "
                "Номера и серии билетов нужно будет ввести заново.",
                parent=self):
            return
        try:
            rows, note = service.build_monthly_rows(
                self._selected_year(), self._selected_month(),
                settings=self.settings, source_rows=current)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка заполнения по графику", str(e), parent=self)
            return
        self._fill_table(rows)
        self.gen_btn.config(state="normal" if rows else "disabled")
        self.info_var.set(f"{note} Проверьте и при необходимости исправьте план поездок перед формированием отчёта.")

    def _add_row(self):
        if not self._finish_edit():
            return
        # вставка ПОСЛЕ выделенной строки (или в конец, если ничего не выделено)
        sel = self.tree.selection()
        idx = (self.tree.index(sel[0]) + 1) if sel else "end"
        iid = self.tree.insert("", idx, values=(0, "", "", "", "", "", "", 0, ""))
        self._renumber()
        self._recalc_total()
        self.tree.selection_set(iid)
        self.tree.see(iid)
        if self.tree.get_children():
            self.gen_btn.config(state="normal")

    def _del_row(self):
        if not self._finish_edit():
            return
        sel = self.tree.selection()
        if sel:
            self.tree.delete(sel[0])
            self._renumber()
            self._recalc_total()
            if not self.tree.get_children():
                self.gen_btn.config(state="disabled")

    # колонки с подсказками (автодополнение целыми значениями) и их пул в лексиконе
    _AC_POOL = {"frm": "place", "to": "place", "purpose": "purpose",
                "series": "series", "number": "number"}

    def _column_pool(self, key):
        """Значения из загруженного отчёта и текущих строк в начале списка."""
        keys = ("frm", "to") if key in ("frm", "to") else (key,)
        current = [str(self.tree.set(iid, col)).strip()
                   for iid in self.tree.get_children() for col in keys]
        pool = self._lexicon.get(self._AC_POOL[key], [])
        if key == "series":
            pool = [*self.settings.get("ticket_series_prices", {}), *pool]
        return list(dict.fromkeys(value for value in [*current, *pool] if value))

    def _finish_edit(self):
        return self._save_edit is None or self._save_edit()

    def _edit_cell(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        col = self.tree.identify_column(event.x)
        rowid = self.tree.identify_row(event.y)
        if not rowid:
            return
        key = self.tree["columns"][int(col[1:]) - 1]
        if key in EDITABLE and self._finish_edit():
            self._begin_edit(rowid, col, key)

    def _begin_edit(self, rowid, col, key):
        self.tree.see(rowid)
        bbox = self.tree.bbox(rowid, col)
        if not bbox:
            return
        x, y, w, h = bbox
        original = self.tree.set(rowid, key)
        if key in self._AC_POOL:
            pool = self._column_pool(key)
            entry = ttk.Combobox(self.tree, values=pool, state="normal")

            def filter_choices(event):
                if event.char or event.keysym in ("BackSpace", "Delete"):
                    fragment = entry.get().strip().casefold()
                    entry.configure(values=[value for value in pool if fragment in value.casefold()])

            entry.bind("<KeyRelease>", filter_choices)
        else:
            entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, original)
        entry.focus_set()
        entry.select_range(0, "end")

        def close():
            self._save_edit = None
            entry.destroy()

        def save():
            val = entry.get().strip()
            if val != original:
                if key == "price":
                    try:
                        val = service.remember_series_price(
                            self.tree.set(rowid, "series"), val, self.settings)
                    except ValueError:
                        self.info_var.set("Введите цену билета числом, например 43,50.")
                        entry.focus_set()
                        return False
                    except OSError as e:
                        self.info_var.set(f"Не удалось запомнить цену билета: {e}")
                        entry.focus_set()
                        return False
                self.tree.set(rowid, key, val)
                if key == "series":
                    self.tree.set(rowid, "price", service.default_price_for(val, self.settings))
            close()
            self._recalc_total()
            return True

        def advance(event):
            if save():
                nxt = self.tree.next(rowid)
                if nxt:
                    self._begin_edit(nxt, col, key)
            return "break"

        def save_after_focusout():
            if self._save_edit is save:
                focus = str(self.tk.call("focus", "-displayof", entry))
                # Встроенный список Combobox временно получает фокус.
                if focus != str(entry) and not focus.startswith(f"{entry}."):
                    save()

        def cancel(event):
            close()
            return "break"

        self._save_edit = save
        entry.bind("<Return>", advance)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", lambda event: self.after_idle(save_after_focusout))

    def _recalc_total(self):
        total = 0.0
        for iid in self.tree.get_children():
            try:
                total += service.parse_price(self.tree.set(iid, "price") or 0)
            except ValueError:
                pass
        self.total_var.set(f"Сумма: {total:g} ₽")

    def _generate(self):
        if not self._finish_edit():
            return
        self._update_worker_forms()
        rows = self._collect_rows()
        if not rows:
            messagebox.showwarning("Нет поездок", "Таблица пуста.")
            return
        worker = self.worker_var.get().strip()
        header = {**self._header, "worker_full": worker}
        short = (self.short_var.get().strip() or "соцработник").split()[0]
        month_up = self.month_var.get().strip()
        default = (f"Проезд_{short}_{month_up}_{self._selected_year()}").replace(" ", "_")
        file_type = tk.StringVar(self, value="Excel")
        out = filedialog.asksaveasfilename(title="Сохранить как…", typevariable=file_type,
                                           initialfile=default,
                                           initialdir=ui_state.last_dir("save") or None,
                                           filetypes=[("Excel", "*.xlsx"), ("OpenDocument Spreadsheet", "*.ods")])
        if not out:
            return
        if not os.path.splitext(out)[1]:
            out += ".ods" if file_type.get() == "OpenDocument Spreadsheet" else ".xlsx"
        ui_state.set_last_dir(out, "save")
        overrides = {"worker_genitive": self.gen_var.get().strip(),
                     "worker_short": self.short_var.get().strip()}
        self.info_var.set("Формирование файла…")
        self.gen_btn.config(state="disabled")
        self.update_idletasks()
        try:
            service.generate(rows, header, self._selected_year(), self._selected_month(),
                             out, overrides)
            documents.save_file("proezd", out, {"worker": worker,
                                                "year": self._selected_year()})
            if worker:
                storage.remember_forms(worker, self.gen_var.get().strip(),
                                       self.short_var.get().strip())
        except Exception as e:  # noqa: BLE001
            self.info_var.set("")
            self.gen_btn.config(state="normal")
            messagebox.showerror("Ошибка формирования", str(e))
            return
        self.info_var.set("Готово.")
        self.gen_btn.config(state="normal")
        if messagebox.askyesno("Готово", f"Файл сохранён:\n{out}\n\nОткрыть?"):
            try:
                open_path(out)
            except Exception:  # noqa: BLE001
                pass


def open_proezd(master):
    return ProezdWindow(master)
