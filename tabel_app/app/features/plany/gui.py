"""Представление (View) функции «Планы» — Tkinter (тонкий слой).

Заведующая выбирает отделение и год; таблица показывает 12 месяцев с редактируемым
соцработником «Заслушивания» (двойной клик по ячейке; запоминается в БД по
отд+год+месяц). Кнопки формируют план выбранного месяца или сразу все 12 → .odt.
Список задач фиксирован (шаблон), меняются только год в датах и этот соцработник.
"""

import datetime
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import FEATURE_TITLE, service, storage
from .service import MONTHS_NOM
from ...core import documents, feedback, ui_state

_KEYS = ("month", "worker", "sign")
_HEADS = ("Месяц", "Соцработник «Заслушивания»", "Есть заслушивание")
_WIDTHS = (150, 320, 130)


class PlanyWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title(FEATURE_TITLE)
        self.geometry("720x560")
        self.minsize(640, 480)

        depts = storage.departments()
        today = datetime.date.today()
        self.dept_var = tk.StringVar(value=ui_state.get("plany_dept", depts[0] if depts else ""))
        if self.dept_var.get() not in depts:
            self.dept_var.set(depts[0] if depts else "")
        self.year_var = tk.IntVar(value=today.year)
        self.info = tk.StringVar(
            value="Выберите отделение и год. При необходимости поправьте соцработника "
                  "«Заслушивания» (двойной клик). Затем сформируйте месяц или все 12.")

        self._build(depts)
        self._reload()

    # ---------------------------------------------------------------- разметка
    def _build(self, depts):
        pad = {"padx": 8, "pady": 4}
        top = ttk.LabelFrame(self, text="Отделение и год")
        top.pack(fill="x", **pad)
        g = ttk.Frame(top)
        g.pack(fill="x", padx=6, pady=4)
        ttk.Label(g, text="Отделение №:").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(g, textvariable=self.dept_var, state="readonly", width=6, values=depts)
        cb.grid(row=0, column=1, sticky="w", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self._reload())
        ttk.Label(g, text="Год:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        sp = tk.Spinbox(g, from_=2024, to=2035, textvariable=self.year_var, width=6,
                        command=self._reload)
        sp.grid(row=0, column=3, sticky="w", padx=4)
        sp.bind("<KeyRelease>", lambda e: self._reload())

        mid = ttk.LabelFrame(self, text="Месяцы (двойной клик по соцработнику — изменить)")
        mid.pack(fill="both", expand=True, **pad)
        self.tree = ttk.Treeview(mid, columns=_KEYS, show="headings", selectmode="browse")
        for key, head, w in zip(_KEYS, _HEADS, _WIDTHS):
            self.tree.heading(key, text=head)
            self.tree.column(key, width=w, anchor="w", stretch=(key == "worker"))
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self._on_double_click)

        ttk.Label(self, textvariable=self.info, foreground="#555", wraplength=680,
                  justify="left").pack(fill="x", padx=10, pady=(2, 0))
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", **pad)
        self.gen_btn = ttk.Button(bottom, text="Сформировать месяц (.odt)",
                                  command=self._generate_one)
        self.gen_btn.pack(side="right")
        self.gen_all_btn = ttk.Button(bottom, text="Сформировать все 12 (в папку)",
                                      command=self._generate_all)
        self.gen_all_btn.pack(side="right", padx=6)
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left", padx=12)

    # ---------------------------------------------------------------- данные
    def _dept(self):
        return self.dept_var.get().strip()

    def _year(self):
        try:
            return int(self.year_var.get())
        except (tk.TclError, ValueError):
            return datetime.date.today().year

    def _reload(self, *_):
        dept = self._dept()
        if not dept:
            return
        ui_state.set_key("plany_dept", dept)
        year = self._year()
        self.tree.delete(*self.tree.get_children())
        for m in range(1, 13):
            has = service.has_sign(dept, m)
            worker = service.effective_worker(dept, year, m) if has else "—"
            self.tree.insert("", "end", iid=str(m),
                             values=(MONTHS_NOM[m].capitalize(), worker,
                                     "да" if has else "нет"))

    def _on_double_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        rowid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        if not rowid or colid != "#2":            # править можно только «Соцработник»
            return
        month = int(rowid)
        if not service.has_sign(self._dept(), month):
            messagebox.showinfo("Нет заслушивания",
                                "В этом месяце нет пункта «Заслушивание» — соцработник не нужен.")
            return
        bbox = self.tree.bbox(rowid, colid)
        if not bbox:
            return
        x, y, w, h = bbox
        ed = ttk.Entry(self.tree)
        ed.place(x=x, y=y, width=w, height=h)
        ed.insert(0, self.tree.set(rowid, "worker"))
        ed.focus_set()
        ed._done = False

        def commit(_=None):
            if ed._done:
                return
            ed._done = True
            val = ed.get().strip()
            ed.destroy()
            storage.worker_save(self._dept(), self._year(), month, val)
            self.tree.set(rowid, "worker",
                          val or storage.default_worker(self._dept(), month))
            # если очистили — вернётся значение из шаблона
            if not val:
                self._reload()

        def cancel(_=None):
            ed._done = True
            ed.destroy()

        ed.bind("<Return>", commit)
        ed.bind("<FocusOut>", commit)
        ed.bind("<Escape>", cancel)

    # ---------------------------------------------------------------- генерация
    def _selected_month(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _generate_one(self):
        month = self._selected_month()
        if not month:
            messagebox.showinfo("Не выбран месяц", "Выделите месяц в таблице.")
            return
        dept, year = self._dept(), self._year()
        default = "План_отд%s_%s_%d.odt" % (dept, MONTHS_NOM[month], year)
        out = filedialog.asksaveasfilename(
            title="Сохранить как…", defaultextension=".odt", initialfile=default,
            initialdir=ui_state.last_dir("save") or None,
            filetypes=[("OpenDocument Text", "*.odt")])
        if not out:
            return
        ui_state.set_last_dir(out, "save")
        self.gen_btn.config(state="disabled")
        self.update_idletasks()
        try:
            service.generate(out, dept, month, year)
            documents.save_file("plany", out, {"dept": dept, "month": month, "year": year})
        except Exception as e:  # noqa: BLE001
            self.gen_btn.config(state="normal")
            messagebox.showerror("Ошибка формирования", str(e))
            return
        self.gen_btn.config(state="normal")
        self.info.set("Готово: %s" % out)
        if messagebox.askyesno("Готово", "Файл сохранён:\n%s\n\nОткрыть?" % out):
            try:
                os.startfile(out)
            except Exception:  # noqa: BLE001
                pass

    def _generate_all(self):
        dept, year = self._dept(), self._year()
        folder = filedialog.askdirectory(
            title="Папка для 12 планов", initialdir=ui_state.last_dir("save") or None)
        if not folder:
            return
        ui_state.set_last_dir(folder, "save")
        self.gen_all_btn.config(state="disabled")
        self.update_idletasks()
        ok, errors = 0, []
        for month in range(1, 13):
            out = os.path.join(folder, "План_отд%s_%02d_%s_%d.odt"
                               % (dept, month, MONTHS_NOM[month], year))
            try:
                service.generate(out, dept, month, year)
                documents.save_file("plany", out, {"dept": dept, "month": month, "year": year})
                ok += 1
            except Exception as e:  # noqa: BLE001
                errors.append("%s: %s" % (MONTHS_NOM[month], e))
        self.gen_all_btn.config(state="normal")
        msg = "Сформировано планов: %d из 12\nПапка: %s" % (ok, folder)
        if errors:
            msg += "\n\nОшибки:\n" + "\n".join(errors)
        self.info.set(msg.replace("\n", " "))
        messagebox.showinfo("Готово", msg)
        if ok and messagebox.askyesno("Открыть папку", "Открыть папку с планами?"):
            try:
                os.startfile(folder)
            except Exception:  # noqa: BLE001
                pass


def open_plany(master):
    return PlanyWindow(master)
