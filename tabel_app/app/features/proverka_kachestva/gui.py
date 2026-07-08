"""Представление (View) «Проверки качества» — Tkinter (тонкий слой).

Соцработники и их клиенты берутся из реестра .xls; заведующая выбирает соцработника,
четверг месяца и его клиентов (галочками) — строки попадают в таблицу-превью, где
любую ячейку можно отредактировать двойным кликом. Телефоны запоминаются в БД.
"""

import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import FEATURE_TITLE, service, storage
from .service import DEFAULTS, MONTHS_NOM
from .writer import COLS
from ...core import documents, feedback, ui_state

_KEYS = ("date", "worker", "client", "address", "phone", "result")
_TREE_WIDTHS = (80, 190, 190, 260, 120, 160)


class ProverkaKachestvaWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title(FEATURE_TITLE)
        self.geometry("960x720")
        self.minsize(860, 640)

        self._wc = {"order": [], "by_worker": {}}   # результат разбора реестра
        self._rows = []                             # источник правды превью: list[dict]
        self._client_vars = []                      # [(client, address, BooleanVar)]
        self._thursdays = []                        # list[date]

        today = datetime.date.today()
        self.month_var = tk.StringVar(value=MONTHS_NOM[today.month])
        self.year_var = tk.IntVar(value=today.year)
        self.dept_var = tk.StringVar(value=ui_state.get("pk_dept", DEFAULTS["dept_no"]))
        self.zav_var = tk.StringVar(value=ui_state.get("pk_zav", DEFAULTS["zav"]))
        self.title_var = tk.StringVar()
        self.sign_var = tk.StringVar()
        self.src_var = tk.StringVar()
        self.worker_var = tk.StringVar()
        self.thu_var = tk.StringVar()
        self.info = tk.StringVar(
            value="Выберите файл реестра .xls и нажмите «Загрузить». Затем: соцработник → "
                  "четверг → отметьте его клиентов → «Добавить в таблицу».")

        # начальные заголовок/подпись + запомненные значения-дефолты
        self._title_default = service.default_title(self.dept_var.get().strip())
        self._sign_default = service.default_sign(self.dept_var.get().strip(),
                                                  self.zav_var.get().strip())
        self.title_var.set(self._title_default)
        self.sign_var.set(self._sign_default)

        self._build()
        self._reload_thursdays()
        # правка реквизитов обновляет дефолтные заголовок/подпись (если их не меняли)
        self.dept_var.trace_add("write", self._refresh_defaults)
        self.zav_var.trace_add("write", self._refresh_defaults)

    # ---------------------------------------------------------------- разметка
    def _build(self):
        pad = {"padx": 8, "pady": 4}

        top = ttk.LabelFrame(self, text="Период и реквизиты")
        top.pack(fill="x", **pad)
        g = ttk.Frame(top)
        g.pack(fill="x", padx=6, pady=4)
        ttk.Label(g, text="Месяц:").grid(row=0, column=0, sticky="w")
        mcombo = ttk.Combobox(g, textvariable=self.month_var, state="readonly", width=12,
                              values=list(MONTHS_NOM[1:]))
        mcombo.grid(row=0, column=1, sticky="w", padx=4)
        mcombo.bind("<<ComboboxSelected>>", lambda e: self._reload_thursdays())
        ttk.Label(g, text="Год:").grid(row=0, column=2, sticky="w")
        tk.Spinbox(g, from_=2024, to=2035, textvariable=self.year_var, width=6,
                   command=self._reload_thursdays).grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(g, text="Отд. №:").grid(row=0, column=4, sticky="w", padx=(12, 0))
        ttk.Entry(g, textvariable=self.dept_var, width=5).grid(row=0, column=5, sticky="w", padx=4)
        ttk.Label(g, text="Зав. отделением:").grid(row=0, column=6, sticky="w", padx=(12, 0))
        ttk.Entry(g, textvariable=self.zav_var, width=22).grid(row=0, column=7, sticky="w", padx=4)

        h = ttk.Frame(top)
        h.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Label(h, text="Заголовок:").grid(row=0, column=0, sticky="w")
        ttk.Entry(h, textvariable=self.title_var).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Label(h, text="Подпись:").grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Entry(h, textvariable=self.sign_var).grid(row=1, column=1, sticky="we", padx=4, pady=(3, 0))
        h.columnconfigure(1, weight=1)

        src = ttk.LabelFrame(self, text="Источник (реестр .xls)")
        src.pack(fill="x", **pad)
        s = ttk.Frame(src)
        s.pack(fill="x", padx=6, pady=4)
        ttk.Entry(s, textvariable=self.src_var, width=64).grid(row=0, column=0, sticky="we", padx=(0, 4))
        ttk.Button(s, text="Обзор…", command=self._pick_source).grid(row=0, column=1)
        ttk.Button(s, text="Загрузить", command=self._load_registry).grid(row=0, column=2, padx=6)
        s.columnconfigure(0, weight=1)

        assign = ttk.LabelFrame(self, text="Добавление проверок")
        assign.pack(fill="x", **pad)
        a = ttk.Frame(assign)
        a.pack(fill="x", padx=6, pady=4)
        ttk.Label(a, text="Соцработник:").grid(row=0, column=0, sticky="w")
        self.worker_combo = ttk.Combobox(a, textvariable=self.worker_var, state="readonly", width=40)
        self.worker_combo.grid(row=0, column=1, sticky="w", padx=4)
        self.worker_combo.bind("<<ComboboxSelected>>", lambda e: self._reload_clients())
        ttk.Label(a, text="Четверг:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.thu_combo = ttk.Combobox(a, textvariable=self.thu_var, state="readonly", width=12)
        self.thu_combo.grid(row=0, column=3, sticky="w", padx=4)
        ttk.Button(a, text="Добавить в таблицу", command=self._add_selected).grid(
            row=0, column=4, padx=(12, 0))

        cbox = ttk.LabelFrame(assign, text="Клиенты соцработника (отметьте нужных)")
        cbox.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        canvas = tk.Canvas(cbox, borderwidth=0, highlightthickness=0, height=130)
        sb = ttk.Scrollbar(cbox, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._clist = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=self._clist, anchor="nw")
        self._clist.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))

        prev = ttk.LabelFrame(self, text="Таблица (двойной клик по ячейке — редактировать)")
        prev.pack(fill="both", expand=True, **pad)
        self.tree = ttk.Treeview(prev, columns=_KEYS, show="headings", selectmode="browse")
        for key, head, w in zip(_KEYS, COLS, _TREE_WIDTHS):
            self.tree.heading(key, text=head)
            self.tree.column(key, width=w, anchor="w", stretch=(key in ("address", "worker", "client")))
        tsb = ttk.Scrollbar(prev, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self._on_double_click)

        tbtn = ttk.Frame(self)
        tbtn.pack(fill="x", padx=8)
        ttk.Button(tbtn, text="Добавить пустую строку", command=self._add_empty).pack(side="left")
        ttk.Button(tbtn, text="Удалить строку", command=self._delete_row).pack(side="left", padx=6)

        ttk.Label(self, textvariable=self.info, foreground="#555", wraplength=900,
                  justify="left").pack(fill="x", padx=10, pady=(2, 0))
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        self.gen_btn = ttk.Button(bottom, text="Сформировать (.ods)", command=self._generate)
        self.gen_btn.pack(side="right")
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    # ---------------------------------------------------------------- реквизиты
    def _refresh_defaults(self, *_):
        dept = self.dept_var.get().strip()
        zav = self.zav_var.get().strip()
        new_title = service.default_title(dept)
        new_sign = service.default_sign(dept, zav)
        if self.title_var.get() == self._title_default:
            self.title_var.set(new_title)
        if self.sign_var.get() == self._sign_default:
            self.sign_var.set(new_sign)
        self._title_default = new_title
        self._sign_default = new_sign

    def _month_num(self):
        return service.month_num(self.month_var.get()) or datetime.date.today().month

    def _reload_thursdays(self):
        try:
            self._thursdays = service.month_thursdays(int(self.year_var.get()), self._month_num())
        except Exception:  # noqa: BLE001
            self._thursdays = []
        labels = [service.format_date(d) for d in self._thursdays]
        self.thu_combo["values"] = labels
        if labels and self.thu_var.get() not in labels:
            self.thu_var.set(labels[0])

    # ---------------------------------------------------------------- источник
    def _pick_source(self):
        f = filedialog.askopenfilename(
            title="Файл реестра (.xls)", initialdir=ui_state.last_dir("open") or None,
            filetypes=[("Excel 97-2003", "*.xls"), ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.src_var.set(f)

    def _load_registry(self):
        path = self.src_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Нет файла", "Укажите файл реестра (.xls).")
            return
        try:
            self._wc = service.parse_workers_clients(path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка чтения", str(e))
            return
        self.worker_combo["values"] = self._wc["order"]
        self.worker_var.set("")
        for w in self._clist.winfo_children():
            w.destroy()
        self._client_vars = []
        self.info.set(f"Загружено соцработников: {len(self._wc['order'])}. "
                      f"Выберите соцработника и четверг, отметьте клиентов.")

    def _reload_clients(self):
        for w in self._clist.winfo_children():
            w.destroy()
        self._client_vars = []
        worker = self.worker_var.get().strip()
        for client, address in self._wc["by_worker"].get(worker, []):
            var = tk.BooleanVar(value=False)
            self._client_vars.append((client, address, var))
            text = f"{client} — {address}" if address else client
            ttk.Checkbutton(self._clist, text=text, variable=var).pack(fill="x", anchor="w", padx=4)

    # ---------------------------------------------------------------- строки
    def _add_selected(self):
        worker = self.worker_var.get().strip()
        date = self.thu_var.get().strip()
        if not worker:
            messagebox.showwarning("Нет соцработника", "Выберите соцработника.")
            return
        if not date:
            messagebox.showwarning("Нет даты", "Выберите четверг.")
            return
        added = 0
        for client, address, var in self._client_vars:
            if var.get():
                self._rows.append({
                    "date": date, "worker": worker, "client": client,
                    "address": address, "phone": storage.load_phone(client) or "",
                    "result": "нет"})
                var.set(False)
                added += 1
        if not added:
            messagebox.showinfo("Никто не отмечен", "Отметьте хотя бы одного клиента.")
            return
        self._refresh_tree()

    def _add_empty(self):
        date = self.thu_var.get().strip() or (
            service.format_date(self._thursdays[0]) if self._thursdays else "")
        self._rows.append({"date": date, "worker": "", "client": "", "address": "",
                           "phone": "", "result": "нет"})
        self._refresh_tree()

    def _delete_row(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Не выбрано", "Выделите строку в таблице.")
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._rows):
            del self._rows[idx]
            self._refresh_tree()

    def _refresh_tree(self):
        self._rows.sort(key=service._date_key)
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self._rows):
            self.tree.insert("", "end", iid=str(i),
                             values=tuple(r.get(k, "") for k in _KEYS))

    def _on_double_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        rowid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        if not rowid:
            return
        ci = int(colid[1:]) - 1
        if not (0 <= ci < len(_KEYS)):
            return
        bbox = self.tree.bbox(rowid, colid)
        if not bbox:
            return
        x, y, w, h = bbox
        key = _KEYS[ci]
        ed = ttk.Entry(self.tree)
        ed.place(x=x, y=y, width=w, height=h)
        ed.insert(0, self._rows[int(rowid)].get(key, ""))
        ed.focus_set()
        ed._done = False

        def commit(_=None):
            if ed._done:
                return
            ed._done = True
            row = self._rows[int(rowid)]
            row[key] = ed.get().strip()
            # при ручном вводе/правке ФИО клиента подтянуть сохранённый телефон
            if key == "client" and row[key] and not row.get("phone"):
                row["phone"] = storage.load_phone(row[key]) or ""
            ed.destroy()
            self._refresh_tree()

        def cancel(_=None):
            ed._done = True
            ed.destroy()

        ed.bind("<Return>", commit)
        ed.bind("<FocusOut>", commit)
        ed.bind("<Escape>", cancel)

    # ---------------------------------------------------------------- генерация
    def _generate(self):
        if not self._rows:
            messagebox.showwarning("Нет строк", "Добавьте хотя бы одну строку проверки.")
            return
        dept = self.dept_var.get().strip()
        zav = self.zav_var.get().strip()
        default = f"Проверка_качества_отд_{dept}_{self.month_var.get()}_{self.year_var.get()}.ods"
        out = filedialog.asksaveasfilename(
            title="Сохранить как…", defaultextension=".ods", initialfile=default,
            initialdir=ui_state.last_dir("save") or None,
            filetypes=[("OpenDocument Spreadsheet", "*.ods")])
        if not out:
            return
        ui_state.set_last_dir(out, "save")
        ui_state.set_key("pk_dept", dept)
        ui_state.set_key("pk_zav", zav)
        ctx = {"title": self.title_var.get().strip(), "sign": self.sign_var.get().strip(),
               "dept_no": dept, "zav": zav}
        rows = list(self._rows)
        self.gen_btn.config(state="disabled")
        self.update_idletasks()
        try:
            service.generate(out, ctx, rows)
            for r in rows:                       # запомнить введённые телефоны
                if r.get("phone"):
                    storage.save_phone(r["client"], r["phone"])
            documents.save_file("proverka_kachestva", out,
                                 {"month": self._month_num(), "year": int(self.year_var.get()),
                                  "dept": dept})
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


class PhonesManager(tk.Toplevel):
    """Редактор сохранённых телефонов клиентов (для «Справочников»).

    Телефоны вводятся вручную в «Проверке качества» и запоминаются по ФИО (в реестре
    их нет). Здесь их можно посмотреть, поправить, удалить или добавить заранее."""

    def __init__(self, master=None):
        super().__init__(master)
        self.title("Телефоны клиентов (Проверка качества)")
        self.geometry("560x460")
        self.minsize(460, 360)
        self.transient(master)
        self._build()
        self._reload()

    def _build(self):
        ttk.Label(self, wraplength=530, foreground="#555", justify="left",
                  text=("Телефоны запоминаются по ФИО клиента и подставляются при следующем "
                        "формировании листа проверки качества. Двойной клик — изменить.")
                  ).pack(fill="x", padx=12, pady=(10, 6))
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=12)
        self.tree = ttk.Treeview(frm, columns=("fio", "phone"), show="headings",
                                 selectmode="browse")
        self.tree.heading("fio", text="ФИО клиента")
        self.tree.heading("phone", text="Телефон")
        self.tree.column("fio", width=340, anchor="w")
        self.tree.column("phone", width=150, anchor="w")
        sb = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self._edit)

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=8)
        ttk.Button(btns, text="Добавить", command=self._add).pack(side="left")
        ttk.Button(btns, text="Удалить", command=self._delete).pack(side="left", padx=6)
        ttk.Button(btns, text="Закрыть", command=self.destroy).pack(side="right")

    def _reload(self):
        self.tree.delete(*self.tree.get_children())
        for fio, phone in sorted(storage.load_all_phones().items()):
            self.tree.insert("", "end", values=(fio, phone))

    def _edit(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        rowid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        if not rowid:
            return
        col = "fio" if colid == "#1" else "phone"
        bbox = self.tree.bbox(rowid, colid)
        if not bbox:
            return
        x, y, w, h = bbox
        old_fio = self.tree.set(rowid, "fio")
        old_phone = self.tree.set(rowid, "phone")
        ed = ttk.Entry(self)
        ed.place(in_=self.tree, x=x, y=y, width=w, height=h)
        ed.insert(0, self.tree.set(rowid, col))
        ed.focus_set()
        ed._done = False

        def commit(_=None):
            if ed._done:
                return
            ed._done = True
            val = ed.get().strip()
            ed.destroy()
            if col == "phone":
                storage.save_phone(old_fio, val)
            else:  # переименование ФИО = перенос телефона на новый ключ
                if val and val != old_fio:
                    storage.delete_phone(old_fio)
                    storage.save_phone(val, old_phone)
            self._reload()

        ed.bind("<Return>", commit)
        ed.bind("<FocusOut>", commit)
        ed.bind("<Escape>", lambda e: (setattr(ed, "_done", True), ed.destroy()))

    def _add(self):
        from tkinter import simpledialog
        fio = simpledialog.askstring("Новый клиент", "ФИО клиента:", parent=self)
        if not fio or not fio.strip():
            return
        phone = simpledialog.askstring("Телефон", "Телефон:", parent=self) or ""
        storage.save_phone(fio.strip(), phone.strip())
        self._reload()

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Не выбрано", "Выделите строку.", parent=self)
            return
        fio = self.tree.set(sel[0], "fio")
        if messagebox.askyesno("Удаление", f"Удалить телефон клиента «{fio}»?", parent=self):
            storage.delete_phone(fio)
            self._reload()


def open_proverka_kachestva(master):
    return ProverkaKachestvaWindow(master)
