"""Представление (View) функции «Проезд» — Tkinter.

Тонкий слой: ввод/отображение и вызовы контроллера (service). Бизнес-логика
(подготовка строк, даты по календарю, нормализация серий, цена, запись .ods) —
в app/features/proezd/service.py."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import FEATURE_TITLE, service, storage
from ...core import documents, feedback, ui_state

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
        self._prepared = None
        self._lexicon = {}                  # словарь подсказок по колонкам
        self.trips_var = tk.StringVar()
        self.scan_var = tk.StringVar()
        self.gen_var = tk.StringVar()
        self.short_var = tk.StringVar()
        months = self.settings.get("months_upper", [""] * 13)
        self.month_var = tk.StringVar(value=months[1] if len(months) > 1 else "")
        self.year_var = tk.IntVar(value=2026)
        self.info_var = tk.StringVar(value="Выберите файл с поездками и (по желанию) скан билетов.")
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
        ttk.Entry(fr, textvariable=self.trips_var, width=64).grid(row=0, column=1, padx=4)
        ttk.Button(fr, text="Обзор…", command=self._pick_trips).grid(row=0, column=2)
        ttk.Label(fr, text="Скан билетов:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(fr, textvariable=self.scan_var, width=64).grid(row=1, column=1, padx=4)
        sb = ttk.Frame(fr)
        sb.grid(row=1, column=2)
        ttk.Button(sb, text="Обзор…", command=self._pick_scan).pack(side="left")
        ttk.Button(sb, text="Открыть", command=self._open_scan, width=8).pack(side="left", padx=2)
        ttk.Button(fr, text="Прочитать", command=self._read).grid(row=0, column=3, rowspan=2, padx=10)

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
        ttk.Button(prm, text="Проставить даты по месяцу", command=self._recalc_dates).pack(side="left", padx=10)

        nm = ttk.LabelFrame(self, text="Заявление — ФИО соцработника")
        nm.pack(fill="x", **pad)
        nf = ttk.Frame(nm)
        nf.pack(fill="x", padx=6, pady=4)
        ttk.Label(nf, text="Родительный падеж:").grid(row=0, column=0, sticky="w")
        ttk.Entry(nf, textvariable=self.gen_var, width=40).grid(row=0, column=1, padx=4)
        ttk.Label(nf, text="Кратко (Фамилия И.О.):").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(nf, textvariable=self.short_var, width=22).grid(row=0, column=3, padx=4)

        mid = ttk.LabelFrame(self, text="Поездки — двойной клик по ячейке для правки (серия меняет цену)")
        mid.pack(fill="both", expand=True, **pad)
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
        ttk.Label(self, textvariable=self.info_var, foreground="#555", wraplength=1140,
                  justify="left").pack(fill="x", padx=10)

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        ttk.Label(bottom, textvariable=self.total_var, font=("", 10, "bold")).pack(side="left")
        self.gen_btn = ttk.Button(bottom, text="Сформировать (.ods)", command=self._generate,
                                  state="disabled")
        self.gen_btn.pack(side="right")
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    # --------------------------------------------------------------- helpers
    def _selected_month(self):
        months = [m.upper() for m in self.settings.get("months_upper", [])]
        mu = self.month_var.get().strip().upper()
        return months.index(mu) if mu in months else 0

    def _selected_year(self):
        try:
            return int(self.year_var.get())
        except (tk.TclError, ValueError):
            return 2026

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
                d["price"] = float(str(d.get("price", "")).replace(",", ".") or 0)
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

    def _pick_scan(self):
        f = filedialog.askopenfilename(title="Скан билетов",
                                       initialdir=ui_state.last_dir("open") or None,
                                       filetypes=[("Изображения", "*.jpg *.jpeg *.png"),
                                                  ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.scan_var.set(f)

    def _open_scan(self):
        scan = self.scan_var.get().strip()
        if scan and os.path.exists(scan):
            try:
                os.startfile(scan)
            except Exception:  # noqa: BLE001
                pass
        else:
            messagebox.showinfo("Скан", "Сначала выберите файл скана.")

    def _read(self):
        tp = self.trips_var.get().strip()
        if not tp or not os.path.exists(tp):
            messagebox.showwarning("Нет файла", "Укажите файл с поездками.")
            return
        scan = self.scan_var.get().strip() or None
        self.info_var.set("Чтение…")
        self.update_idletasks()
        try:
            self._prepared = service.prepare(tp, scan)
        except Exception as e:  # noqa: BLE001
            self.info_var.set("")
            messagebox.showerror("Ошибка чтения", str(e))
            return

        header = self._prepared["header"]
        # предзаполнить месяц/год из шапки файла
        mu = (header.get("month_upper", "") or "").strip().upper()
        months = [m.upper() for m in self.settings.get("months_upper", [])]
        if mu in months:
            self.month_var.set(self.settings["months_upper"][months.index(mu)])
        ys = str(header.get("year", "")).strip()
        if ys.isdigit():
            self.year_var.set(int(ys))
        forms = storage.forms_for(header.get("worker_full", ""))
        self.gen_var.set(forms["genitive"])
        self.short_var.set(forms["short"])

        rows, note = service.build_rows(self._prepared, self._selected_year(),
                                        self._selected_month(), self.settings)
        self._fill_table(rows)
        self._lexicon = service.build_lexicon(rows, self.settings)  # подсказки

        ocr = self._prepared.get("tickets", [])
        ser_ok = sum(1 for n, s in ocr if s)
        ocr_note = (f"распознано серий: {ser_ok}/{len(ocr)}; номера со скана впишите/сверьте"
                    if scan else "скан не выбран")
        self.info_var.set(
            f"Соцработник: {header.get('worker_full','?')} · "
            f"поездок: {len(rows)} · {ocr_note}."
            + ("" if self._prepared["ocr_available"] else " (OCR недоступен)")
            + f"\n{note}")
        self.gen_btn.config(state="normal")

    def _recalc_dates(self):
        if not self.tree.get_children():
            return
        rows = self._collect_rows()
        rows, note = service.reassign_dates(rows, self._selected_year(), self._selected_month())
        self._fill_table(rows)
        self.info_var.set(note)

    def _add_row(self):
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
        sel = self.tree.selection()
        if sel:
            self.tree.delete(sel[0])
            self._renumber()
            self._recalc_total()

    # колонки с подсказками (автодополнение целыми значениями) и их пул в лексиконе
    _AC_POOL = {"frm": "place", "to": "place", "purpose": "purpose",
                "series": "series", "number": "number"}

    def _column_pool(self, key):
        """Значения-подсказки для колонки: лексикон + текущие значения этой колонки."""
        pool = self._lexicon.get(self._AC_POOL.get(key, ""), []) if key in self._AC_POOL else []
        vals = set(pool)
        for iid in self.tree.get_children():
            v = str(self.tree.set(iid, key)).strip()
            if v:
                vals.add(v)
        return sorted(vals)

    def _edit_cell(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        col = self.tree.identify_column(event.x)
        rowid = self.tree.identify_row(event.y)
        if not rowid:
            return
        key = self.tree["columns"][int(col[1:]) - 1]
        if key in EDITABLE:
            self._begin_edit(rowid, col, key)

    def _begin_edit(self, rowid, col, key):
        """Редактирование ячейки: автодополнение (подсказки) + Enter → ячейка ниже."""
        self.tree.see(rowid)
        bbox = self.tree.bbox(rowid, col)
        if not bbox:
            return
        x, y, w, h = bbox
        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, self.tree.set(rowid, key))
        entry.focus_set()
        entry.select_range(0, "end")
        pool = self._column_pool(key)
        st = {"popup": None, "lb": None, "pending": None}

        def close_popup():
            if st["popup"] is not None:
                st["popup"].destroy()
                st["popup"] = None
                st["lb"] = None

        def cancel_pending():
            if st["pending"] is not None:
                try:
                    self.after_cancel(st["pending"])
                except Exception:  # noqa: BLE001
                    pass
                st["pending"] = None

        def show_ac(ev=None):
            if ev is not None and getattr(ev, "keysym", "") in (
                    "Up", "Down", "Return", "Escape", "Left", "Right", "Tab"):
                return
            if not pool:
                return
            txt = entry.get().strip().lower()
            matches = [v for v in pool if txt in v.lower()] if txt else list(pool)
            matches = matches[:12]
            if not matches or (len(matches) == 1 and matches[0].lower() == txt):
                close_popup()
                return
            if st["popup"] is None:
                pu = tk.Toplevel(self)
                pu.wm_overrideredirect(True)
                pu.attributes("-topmost", True)
                lb = tk.Listbox(pu, activestyle="dotbox", exportselection=False)
                lb.pack(fill="both", expand=True)
                lb.bind("<ButtonRelease-1>", lambda e: accept())
                st["popup"], st["lb"] = pu, lb
            lb = st["lb"]
            lb.delete(0, "end")
            for m in matches:
                lb.insert("end", m)
            lb.selection_set(0)
            lb.activate(0)
            lb.configure(height=min(8, len(matches)))
            rx = self.tree.winfo_rootx() + x
            ry = self.tree.winfo_rooty() + y + h
            st["popup"].update_idletasks()
            st["popup"].geometry(f"{max(w, 220)}x{st['popup'].winfo_reqheight()}+{rx}+{ry}")

        def move(delta):
            lb = st["lb"]
            if lb is None or not lb.size():
                return
            cur = lb.curselection()
            i = max(0, min(lb.size() - 1, (cur[0] if cur else -1) + delta))
            lb.selection_clear(0, "end")
            lb.selection_set(i)
            lb.activate(i)
            lb.see(i)

        def accept():
            cancel_pending()
            lb = st["lb"]
            if lb is not None and lb.curselection():
                entry.delete(0, "end")
                entry.insert(0, lb.get(lb.curselection()[0]))
            close_popup()
            entry.focus_set()

        def save(advance=False):
            cancel_pending()
            val = entry.get().strip()
            self.tree.set(rowid, key, val)
            if key == "series":  # цена пересчитывается по серии
                self.tree.set(rowid, "price", service.default_price_for(val, self.settings))
            close_popup()
            entry.destroy()
            self._recalc_total()
            if advance:
                nxt = self.tree.next(rowid)
                if nxt:
                    self._begin_edit(nxt, col, key)

        def cancel_edit():
            cancel_pending()
            close_popup()
            entry.destroy()

        def on_return(ev):
            if st["popup"] is not None:       # есть подсказки — принять выбранную
                accept()
            else:                              # иначе — сохранить и перейти ниже
                save(advance=True)
            return "break"

        def on_down(ev):
            if st["popup"] is not None:
                move(1)
            else:
                show_ac()
            return "break"

        def on_up(ev):
            move(-1)
            return "break"

        def on_escape(ev):
            if st["popup"] is not None:
                close_popup()
            else:
                cancel_edit()
            return "break"

        def on_focusout(ev):
            # отложенно: клик по подсказке вызовет accept и отменит это сохранение
            st["pending"] = self.after(150, lambda: save(advance=False))

        entry.bind("<KeyRelease>", show_ac)
        entry.bind("<Down>", on_down)
        entry.bind("<Up>", on_up)
        entry.bind("<Return>", on_return)
        entry.bind("<Escape>", on_escape)
        entry.bind("<FocusOut>", on_focusout)
        show_ac()

    def _recalc_total(self):
        total = 0.0
        for iid in self.tree.get_children():
            try:
                total += float(str(self.tree.set(iid, "price")).replace(",", ".") or 0)
            except ValueError:
                pass
        self.total_var.set(f"Сумма: {total:g} ₽")

    def _generate(self):
        if not self._prepared:
            return
        rows = self._collect_rows()
        if not rows:
            messagebox.showwarning("Нет поездок", "Таблица пуста.")
            return
        header = self._prepared["header"]
        worker = header.get("worker_full", "")
        short = (self.short_var.get().strip() or "соцработник").split()[0]
        month_up = self.month_var.get().strip()
        default = (f"Проезд_{short}_{month_up}_{self._selected_year()}.ods").replace(" ", "_")
        out = filedialog.asksaveasfilename(title="Сохранить как…", defaultextension=".ods",
                                           initialfile=default,
                                           initialdir=ui_state.last_dir("save") or None,
                                           filetypes=[("OpenDocument Spreadsheet", "*.ods")])
        if not out:
            return
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
                os.startfile(out)
            except Exception:  # noqa: BLE001
                pass


def open_proezd(master):
    return ProezdWindow(master)
