"""Графический интерфейс функции «Реестр»."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import FEATURE_TITLE, parser, service, storage
from ...core import documents, feedback, ui_state


def _decimal_fraction(path):
    """Доля сумм с копейками (нецелых) — у дополнительных услуг она высокая."""
    try:
        reg = parser.parse_registry(path, "gos")
    except Exception:
        return -1.0, 0
    vals = [r.nachisleno for r in reg.records]
    if not vals:
        return 0.0, 0
    frac = sum(1 for v in vals if abs(v - round(v)) > 0.005) / len(vals)
    return frac, len(vals)


def _detect(folder):
    """Распознать в папке три файла: реестр гос, реестр доп, отчёт ИПСУ.
    Если в имени нет слов «государственные/дополнительные», гос/доп различаются
    по содержимому (у доп много сумм с копейками)."""
    found = {"gos": "", "dop": "", "ipsu": "", "journal": ""}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return found
    ambiguous = []
    for n in names:
        low = n.lower()
        if not low.endswith((".xls", ".xlsx")):
            continue
        path = os.path.join(folder, n)
        if "заключенных договоров" in low or "заключённых договоров" in low:
            if not found["journal"]:
                found["journal"] = path
        elif any(p in low for p in ("иппсу", "ипсу", "формированию реестра")):
            if not found["ipsu"]:
                found["ipsu"] = path
        elif "государственн" in low:
            if not found["gos"]:
                found["gos"] = path
        elif "дополнительн" in low:
            if not found["dop"]:
                found["dop"] = path
        elif "реестр" in low and "оплат" in low:
            ambiguous.append(path)

    # Разнести неоднозначные «реестр по оплате» по содержимому.
    if ambiguous and (not found["gos"] or not found["dop"]):
        scored = sorted((_decimal_fraction(p) + (p,) for p in ambiguous))  # по возрастанию доли копеек
        order = [p for *_x, p in scored]
        if not found["gos"] and order:
            found["gos"] = order[0]          # меньше копеек -> государственные
        if not found["dop"] and len(order) > 1:
            found["dop"] = order[-1]          # больше копеек -> дополнительные
    return found


class ReestrWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Реестр по оплате за оказанные услуги")
        self.geometry("780x470")
        self.minsize(720, 420)
        self.settings = storage.load_settings()
        self._prepared = None
        self._peresmotr = set()        # норм. ФИО с пометкой «пересмотр»
        self._new = None               # норм. ФИО «новый» (из журнала) или None
        self._marks_active = False      # переопределять ли авто-пометки
        self.vars = {k: tk.StringVar() for k in ("gos", "dop", "ipsu", "journal")}
        self._build()

    def _build(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.LabelFrame(self, text="Входные файлы")
        top.pack(fill="x", **pad)

        fr = ttk.Frame(top)
        fr.pack(fill="x", padx=6, pady=4)
        ttk.Label(fr, text="Папка с файлами:").grid(row=0, column=0, sticky="w")
        self.folder_var = tk.StringVar()
        ttk.Entry(fr, textvariable=self.folder_var, width=58).grid(row=0, column=1, padx=4)
        ttk.Button(fr, text="Обзор…", command=self._pick_folder).grid(row=0, column=2)

        labels = [("gos", "Реестр государственных:"), ("dop", "Реестр дополнительных:"),
                  ("ipsu", "Отчёт ИПСУ:"),
                  ("journal", "Журнал договоров (необяз.):")]
        for i, (key, text) in enumerate(labels, start=1):
            ttk.Label(fr, text=text).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(fr, textvariable=self.vars[key], width=58).grid(row=i, column=1, padx=4)
            ttk.Button(fr, text="файл…", command=lambda k=key: self._pick_file(k)).grid(row=i, column=2)

        mid = ttk.Frame(self)
        mid.pack(fill="x", **pad)
        ttk.Label(mid, text="Отделение:").grid(row=0, column=0, sticky="w")
        self.dept_var = tk.StringVar()
        depts = self.settings.get("departments", [])
        _dnames = [f"№{d['number']} — {d.get('zav_fio', '')}" for d in depts]
        self.dept_combo = ttk.Combobox(mid, textvariable=self.dept_var, state="readonly", width=40,
                                       values=_dnames)
        if depts:
            self.dept_combo.current(ui_state.dept_index("reestr", _dnames))
        self.dept_combo.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Button(mid, text="Подготовить", command=self._prepare).grid(row=0, column=2, padx=10)
        ttk.Button(mid, text="Клиенты и группы…", command=self._open_clients).grid(
            row=0, column=3, padx=4)
        self.peres_btn = ttk.Button(mid, text="Пометки «пересмотр»…",
                                    command=self._open_peresmotr, state="disabled")
        self.peres_btn.grid(row=1, column=2, columnspan=2, padx=4, pady=(4, 0), sticky="w")

        self.status = ttk.Label(self, text="Выберите файлы и нажмите «Подготовить».", foreground="#555")
        self.status.pack(fill="x", padx=10)

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        self.gen_btn = ttk.Button(bottom, text="Сформировать РЕЕСТР (.ods)", command=self._generate,
                                  state="disabled")
        self.gen_btn.pack(side="right")
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    # ---------------------------------------------------------- actions
    def _pick_folder(self):
        d = filedialog.askdirectory(title="Папка с реестрами",
                                    initialdir=ui_state.last_dir("open") or None)
        if not d:
            return
        ui_state.set_last_dir(d, "open")
        self.folder_var.set(d)
        found = _detect(d)
        for k, v in found.items():
            if v:
                self.vars[k].set(v)
        self.status.config(text="Файлы распознаны. Проверьте и нажмите «Подготовить».")

    def _pick_file(self, key):
        f = filedialog.askopenfilename(title="Выберите файл",
                                       initialdir=ui_state.last_dir("open") or None,
                                       filetypes=[("Excel", "*.xls *.xlsx"), ("Все файлы", "*.*")])
        if f:
            ui_state.set_last_dir(f, "open")
            self.vars[key].set(f)

    def _open_clients(self):
        dlg = ClientsManager(self)
        self.wait_window(dlg)

    def _open_peresmotr(self):
        if not self._prepared:
            return
        clients = self._prepared.get("client_fios", {})
        if not clients:
            messagebox.showinfo("Нет клиентов", "Сначала нажмите «Подготовить».")
            return
        dlg = PeresmotrDialog(self, clients, self._peresmotr)
        self.wait_window(dlg)
        if dlg.saved:
            self._peresmotr = dlg.result
            self._marks_active = True
            self.status.config(text=f"Пометок «пересмотр»: {len(self._peresmotr)}. "
                                    f"Можно формировать.")

    def _cur_dept(self):
        depts = self.settings.get("departments", [])
        i = self.dept_combo.current()
        return depts[i] if 0 <= i < len(depts) else {"number": "9", "zav_fio": ""}

    def _prepare(self):
        paths = {k: self.vars[k].get().strip() for k in self.vars}
        for k in ("gos", "dop", "ipsu"):           # журнал — необязателен
            if not paths[k] or not os.path.exists(paths[k]):
                messagebox.showwarning("Нет файла", f"Укажите корректный файл: {k}.")
                return
        journal = paths["journal"] if paths["journal"] and os.path.exists(paths["journal"]) else None
        self.status.config(text="Чтение файлов…")
        self.update_idletasks()
        try:
            self._prepared = service.prepare(paths["gos"], paths["dop"], paths["ipsu"], journal)
        except Exception as e:  # noqa: BLE001
            self.status.config(text="")
            messagebox.showerror("Ошибка чтения", str(e))
            return

        un = self._prepared["unassigned_fios"]
        if un:
            workers = list(dict.fromkeys(service.employee_workers()
                                         + service.all_workers()
                                         + self._prepared.get("registry_workers", [])))
            dlg = AssignDialog(self, un, workers,
                               self._prepared.get("unassigned_suggest", {}))
            self.wait_window(dlg)
            if not dlg.saved:
                self.status.config(text="Не назначены новые клиенты — формирование недоступно.")
                self.gen_btn.config(state="disabled")
                return
            service.assign_new(dlg.result)
            self._prepared = service.prepare(paths["gos"], paths["dop"], paths["ipsu"], journal)

        self._init_marks()
        n = len(self._prepared["gos"].records) + len(self._prepared["dop"].records)
        msg = f"Готово к формированию. Записей: {n}. Период: {self._prepared['period_start']}."
        j = self._prepared.get("journal")
        if j:
            msg += (f" Журнал: новых {len(j['auto_new'])}, пересмотр {len(j['auto_peresmotr'])}"
                    f", снято {len(j['snyat'])}.")
            if not j.get("had_prev"):
                msg += " (Первый журнал — отметки появятся при сравнении со следующим месяцем.)"
        self.status.config(text=msg)
        self.peres_btn.config(state="normal")
        self.gen_btn.config(state="normal")

    def _init_marks(self):
        """Инициализировать пометки из журнала (или сбросить, если журнала нет)."""
        j = (self._prepared or {}).get("journal")
        if j and j.get("had_prev"):
            self._peresmotr = set(j.get("auto_peresmotr", []))
            self._new = set(j.get("auto_new", []))
            self._marks_active = True
        else:
            # нет журнала ИЛИ первый журнал (сравнивать не с чем) — авто-эвристика как раньше,
            # ручная пометка «пересмотр» по-прежнему доступна
            self._peresmotr = set()
            self._new = None
            self._marks_active = False

    def _generate(self):
        if not self._prepared:
            return
        dept = self._cur_dept()
        default = f"РЕЕСТР_{dept['number']}_{self._prepared['period_start'].replace('.', '-')}.ods"
        out = filedialog.asksaveasfilename(title="Сохранить РЕЕСТР как…", defaultextension=".ods",
                                           initialfile=default,
                                           initialdir=ui_state.last_dir("save") or None,
                                           filetypes=[("OpenDocument Spreadsheet", "*.ods")])
        if not out:
            return
        ui_state.set_last_dir(out, "save")
        ui_state.set_last_dept("reestr", self.dept_var.get())
        self.status.config(text="Формирование файла…")
        self.gen_btn.config(state="disabled")
        self.update_idletasks()
        try:
            mark_new = self._new if self._marks_active else None
            mark_per = self._peresmotr if self._marks_active else None
            service.generate(self._prepared, dept["number"], dept.get("zav_fio", ""), out,
                             mark_new_fios=mark_new, mark_peresmotr_fios=mark_per)
            documents.save_file("reestr", out, {"dept": dept.get("number", "")})
        except Exception as e:  # noqa: BLE001
            self.status.config(text="")
            self.gen_btn.config(state="normal")
            messagebox.showerror("Ошибка формирования", str(e))
            return
        self.status.config(text="Готово.")
        self.gen_btn.config(state="normal")
        if messagebox.askyesno("Готово", f"РЕЕСТР сохранён:\n{out}\n\nОткрыть файл?"):
            try:
                os.startfile(out)
            except Exception:  # noqa: BLE001
                pass


class AssignDialog(tk.Toplevel):
    """Назначение новых клиентов соцработникам."""

    def __init__(self, master, fios, workers, suggest=None):
        super().__init__(master)
        self.title("Новые клиенты — назначьте соцработника")
        self.geometry("620x440")
        self.transient(master)
        self.grab_set()
        self.result = {}
        self.saved = False
        self.workers = workers
        self._suggest = suggest or {}

        ttk.Label(self, text="Эти клиенты появились впервые. Укажите для каждого соцработника:",
                  wraplength=580).pack(padx=10, pady=8, anchor="w")

        canvas = tk.Canvas(self, borderwidth=0)
        frame = ttk.Frame(canvas)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=8)
        canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._vars = {}
        for i, fio in enumerate(fios):
            ttk.Label(frame, text=fio, width=40).grid(row=i, column=0, sticky="w", pady=2)
            v = tk.StringVar()
            cb = ttk.Combobox(frame, textvariable=v, state="readonly", width=32, values=workers)
            sug = self._suggest.get(fio, "")
            if sug in workers:
                v.set(sug)  # подсказка из колонки реестра
            cb.grid(row=i, column=1, padx=4, pady=2)
            self._vars[fio] = v

        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", pady=6)
        ttk.Button(bar, text="Сохранить и продолжить", command=self._ok).pack(side="right", padx=8)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Принять все подсказки", command=self._accept_all).pack(side="left", padx=8)

    def _accept_all(self):
        for fio, v in self._vars.items():
            sug = self._suggest.get(fio, "")
            if sug in self.workers:
                v.set(sug)

    def _ok(self):
        res = {fio: v.get() for fio, v in self._vars.items() if v.get()}
        if len(res) != len(self._vars):
            if not messagebox.askyesno("Не все назначены",
                                       "Некоторые клиенты не назначены — они не попадут в реестр. Продолжить?"):
                return
        self.result = res
        self.saved = True
        self.destroy()


class _PickOrTypeDialog(tk.Toplevel):
    """Выбор из списка ИЛИ ввод нового значения (редактируемый combobox)."""

    def __init__(self, master, title, prompt, choices):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result = None
        ttk.Label(self, text=prompt, wraplength=380).grid(
            row=0, column=0, padx=10, pady=(10, 4), sticky="w")
        self.var = tk.StringVar()
        cb = ttk.Combobox(self, textvariable=self.var, values=list(choices), width=46)
        cb.grid(row=1, column=0, padx=10, pady=4)
        cb.focus_set()
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, pady=10)
        ttk.Button(bar, text="ОК", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="left", padx=6)
        self.bind("<Return>", lambda e: self._ok())

    def _ok(self):
        self.result = self.var.get().strip()
        self.destroy()


class ClientsManager(tk.Toplevel):
    """Управление клиентами и их группами (соцработниками) в единой базе.

    Слева — соцработники (группы) и их порядок; справа — клиенты выбранной группы.
    Все правки идут в память, а по кнопке «Сохранить» — одним вызовом в app.db.
    """

    def __init__(self, master):
        super().__init__(master)
        self.title("Клиенты и группы (соцработники)")
        self.geometry("840x560")
        self.transient(master)
        self.grab_set()
        self.saved = False

        wm = storage.load_worker_map()
        self.order = list(wm.get("worker_order", []))
        self.cw = dict(wm.get("client_worker", {}))
        # Соцработники, на которых есть клиенты, но которых нет в порядке — добавить.
        for w in self.cw.values():
            if w and w not in self.order:
                self.order.append(w)
        try:
            self.db_workers = service.employee_workers()
        except Exception:  # noqa: BLE001
            self.db_workers = []

        self._build()
        self._reload_workers()
        self._snapshot = self._state()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _state(self):
        return (tuple(self.order), tuple(sorted(self.cw.items())))

    def _is_dirty(self):
        return self._state() != self._snapshot

    def _build(self):
        left = ttk.LabelFrame(self, text="Соцработники (группы)")
        left.pack(side="left", fill="y", padx=8, pady=8)
        self.w_list = tk.Listbox(left, width=36, exportselection=False)
        self.w_list.pack(fill="y", expand=True, padx=4, pady=4)
        self.w_list.bind("<<ListboxSelect>>", lambda e: self._reload_clients())
        wb = ttk.Frame(left)
        wb.pack(fill="x")
        ttk.Button(wb, text="Добавить", command=self._add_worker).pack(side="left", padx=2, pady=2)
        ttk.Button(wb, text="Удалить", command=self._del_worker).pack(side="left", padx=2)
        ttk.Button(wb, text="↑", width=3, command=lambda: self._move_worker(-1)).pack(side="left", padx=2)
        ttk.Button(wb, text="↓", width=3, command=lambda: self._move_worker(1)).pack(side="left", padx=2)

        right = ttk.LabelFrame(self, text="Клиенты выбранного соцработника")
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        self.c_list = tk.Listbox(right, exportselection=False)
        self.c_list.pack(fill="both", expand=True, padx=4, pady=4)
        cb = ttk.Frame(right)
        cb.pack(fill="x")
        ttk.Button(cb, text="Добавить", command=self._add_client).pack(side="left", padx=2, pady=2)
        ttk.Button(cb, text="Удалить", command=self._del_client).pack(side="left", padx=2)
        ttk.Button(cb, text="Переименовать", command=self._rename_client).pack(side="left", padx=2)
        ttk.Button(cb, text="Переназначить…", command=self._reassign_client).pack(side="left", padx=2)

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", pady=6)
        ttk.Button(bottom, text="Сохранить", command=self._save).pack(side="right", padx=8)
        ttk.Button(bottom, text="Закрыть без сохранения", command=self._discard).pack(side="right")
        self.count_lbl = ttk.Label(bottom, text="", foreground="#555")
        self.count_lbl.pack(side="left", padx=10)

    # ----------------------------------------------------------- helpers
    def _reload_workers(self, select=0):
        self.w_list.delete(0, "end")
        for w in self.order:
            n = sum(1 for ww in self.cw.values() if ww == w)
            self.w_list.insert("end", f"{w}  ({n})")
        if self.order:
            sel = min(max(select, 0), len(self.order) - 1)
            self.w_list.selection_clear(0, "end")
            self.w_list.selection_set(sel)
            self.w_list.see(sel)
        self._reload_clients()

    def _cur_worker(self):
        sel = self.w_list.curselection()
        if not sel:
            return None
        return self.order[sel[0]]

    def _reload_clients(self):
        self.c_list.delete(0, "end")
        w = self._cur_worker()
        clients = sorted(c for c, ww in self.cw.items() if ww == w) if w else []
        for c in clients:
            self.c_list.insert("end", c)
        self.count_lbl.config(
            text=f"Всего клиентов: {len(self.cw)}; соцработников: {len(self.order)}")

    def _selected_client(self):
        sel = self.c_list.curselection()
        if not sel:
            return None
        return self.c_list.get(sel[0])

    # ----------------------------------------------------------- соцработники
    def _add_worker(self):
        choices = [w for w in self.db_workers if w not in self.order]
        dlg = _PickOrTypeDialog(self, "Соцработник",
                                "Выберите из базы или введите ФИО:", choices)
        self.wait_window(dlg)
        name = (dlg.result or "").strip()
        if not name:
            return
        if name in self.order:
            messagebox.showinfo("Уже есть", "Такой соцработник уже в списке.")
            return
        self.order.append(name)
        self._reload_workers(len(self.order) - 1)

    def _del_worker(self):
        w = self._cur_worker()
        if not w:
            return
        sel = self.w_list.curselection()[0]
        n = sum(1 for ww in self.cw.values() if ww == w)
        if n and not messagebox.askyesno(
                "Удалить соцработника",
                f"Удалить «{w}»? Его клиенты ({n}) будут удалены из групп "
                f"(при следующем импорте их снова попросят назначить)."):
            return
        self.order.remove(w)
        for c, ww in list(self.cw.items()):
            if ww == w:
                del self.cw[c]
        self._reload_workers(max(0, sel - 1))

    def _move_worker(self, delta):
        sel = self.w_list.curselection()
        if not sel:
            return
        i = sel[0]
        j = i + delta
        if 0 <= j < len(self.order):
            self.order[i], self.order[j] = self.order[j], self.order[i]
            self._reload_workers(j)

    # ----------------------------------------------------------- клиенты
    def _add_client(self):
        w = self._cur_worker()
        if not w:
            messagebox.showinfo("Соцработник", "Сначала выберите соцработника слева.")
            return
        name = simpledialog.askstring("Новый клиент", "ФИО клиента:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.cw:
            messagebox.showinfo("Уже есть",
                                f"Клиент «{name}» уже привязан к «{self.cw[name]}».")
            return
        self.cw[name] = w
        self._reload_workers(self.order.index(w))

    def _del_client(self):
        c = self._selected_client()
        if not c:
            return
        if messagebox.askyesno("Удалить клиента", f"Удалить клиента «{c}» из групп?"):
            self.cw.pop(c, None)
            w = self._cur_worker()
            self._reload_workers(self.order.index(w) if w in self.order else 0)

    def _rename_client(self):
        c = self._selected_client()
        if not c:
            return
        name = simpledialog.askstring("Переименовать клиента", "Новое ФИО:",
                                      initialvalue=c, parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name == c:
            return
        if name in self.cw:
            messagebox.showinfo("Уже есть", "Клиент с таким ФИО уже есть.")
            return
        self.cw[name] = self.cw.pop(c)
        w = self._cur_worker()
        self._reload_workers(self.order.index(w) if w in self.order else 0)

    def _reassign_client(self):
        c = self._selected_client()
        if not c:
            return
        dlg = _PickOrTypeDialog(self, "Переназначить клиента",
                                f"Кому передать «{c}»:", self.order)
        self.wait_window(dlg)
        target = (dlg.result or "").strip()
        if not target:
            return
        if target not in self.order:
            self.order.append(target)
        self.cw[c] = target
        self._reload_workers(self.order.index(target))

    def _save(self):
        try:
            storage.save_worker_map({"worker_order": self.order, "client_worker": self.cw})
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка сохранения",
                                 f"Не удалось сохранить изменения:\n{e}")
            return
        self.saved = True
        self._snapshot = self._state()
        messagebox.showinfo("Сохранено", "Изменения сохранены.")
        self.destroy()

    def _on_close(self):
        if self._is_dirty():
            ans = messagebox.askyesnocancel(
                "Сохранить изменения?",
                "Есть несохранённые изменения. Сохранить перед закрытием?")
            if ans is None:
                return
            if ans:
                self._save()
                return
        self.destroy()

    def _discard(self):
        if self._is_dirty() and not messagebox.askyesno(
                "Закрыть без сохранения",
                "Несохранённые изменения будут потеряны. Закрыть?"):
            return
        self.destroy()


class PeresmotrDialog(tk.Toplevel):
    """Ручная пометка «пересмотр» по клиентам (галочки; предзаполнено из журнала)."""

    def __init__(self, master, clients, selected):
        super().__init__(master)
        self.title("Пометки «пересмотр»")
        self.geometry("520x560")
        self.transient(master)
        self.grab_set()
        self.result = set()
        self.saved = False

        ttk.Label(self, text="Отметьте клиентов, у которых пересмотр договора:",
                  wraplength=480).pack(padx=10, pady=8, anchor="w")
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        frame = ttk.Frame(canvas)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=8)
        win = canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))

        self._vars = {}
        for norm, disp in sorted(clients.items(), key=lambda kv: kv[1].lower()):
            v = tk.BooleanVar(value=norm in (selected or set()))
            self._vars[norm] = v
            ttk.Checkbutton(frame, text=disp, variable=v).pack(fill="x", anchor="w", padx=4)

        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", pady=6)
        ttk.Button(bar, text="ОК", command=self._ok).pack(side="right", padx=8)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="right")

    def _ok(self):
        self.result = {n for n, v in self._vars.items() if v.get()}
        self.saved = True
        self.destroy()


def open_reestr(master):
    return ReestrWindow(master)


def run():
    root = tk.Tk()
    root.withdraw()
    win = ReestrWindow(root)
    win.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
