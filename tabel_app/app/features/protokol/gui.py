"""Редактор рабочего протокола."""

from datetime import date
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import FEATURE_TITLE, service, storage
from ...core import documents, feedback, ui_state


class ProtokolWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title(FEATURE_TITLE)
        self.geometry("820x650")
        self.minsize(660, 540)
        self.departments = storage.list_departments()
        self.calendar = storage.load_calendar()
        self.context = None
        self.original = None
        self.people = []

        today = date.today()
        self.year = tk.StringVar(value=str(today.year))
        self.number = tk.StringVar()
        self.meeting_date = tk.StringVar()
        self.head = tk.StringVar()
        self.speaker = tk.StringVar()
        self.status = tk.StringVar()
        self.fields = {}
        self._build()
        names = [d["name"] for d in self.departments]
        self.department.current(ui_state.dept_index("protokol", names))
        self.month.current(today.month - 1)
        self._load_period()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        period = ttk.Frame(self, padding=8)
        period.pack(fill="x")
        self.department = ttk.Combobox(period, values=[d["name"] for d in self.departments],
                                       state="readonly", width=44)
        self.department.pack(side="left")
        self.month = ttk.Combobox(period, values=service.MONTHS_NOM[1:], state="readonly", width=12)
        self.month.pack(side="left", padx=6)
        ttk.Spinbox(period, from_=1900, to=9999, textvariable=self.year, width=6).pack(side="left")
        ttk.Button(period, text="Открыть период", command=self._load_period).pack(side="left", padx=6)

        details = ttk.Frame(self, padding=(8, 0, 8, 8))
        details.pack(fill="x")
        for label, variable, width in (("Номер", self.number, 7), ("Дата", self.meeting_date, 13),
                                       ("Заведующая", self.head, 28)):
            ttk.Label(details, text=label).pack(side="left", padx=(0, 4))
            ttk.Entry(details, textvariable=variable, width=width).pack(side="left", padx=(0, 8))

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=8)
        people = ttk.Frame(tabs, padding=8)
        tabs.add(people, text="Участники")
        actions = ttk.Frame(people)
        actions.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(actions, text="Добавить", command=lambda: self._edit_person(None)).pack(side="left")
        ttk.Button(actions, text="Изменить", command=self._edit_selected).pack(side="left", padx=6)
        ttk.Button(actions, text="Удалить", command=self._delete_person).pack(side="left")

        self.table = ttk.Treeview(people, columns=("name", "present", "reason"), show="headings",
                                  selectmode="browse")
        for key, label, width in (("name", "ФИО", 270), ("present", "Статус", 115),
                                  ("reason", "Причина отсутствия", 190)):
            self.table.heading(key, text=label)
            self.table.column(key, width=width)
        scroll = ttk.Scrollbar(people, command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.table.pack(fill="both", expand=True)
        self.table.bind("<Double-1>", lambda event: self._edit_selected())

        agenda = ttk.Frame(tabs, padding=8)
        tabs.add(agenda, text="Повестка и докладчик")
        ttk.Label(agenda, text="Повестка из плана методического часа, по одному пункту на строку").pack(anchor="w")
        self._text_field(agenda, "agenda", 5)
        ttk.Label(agenda, text="Тема и докладчик из плана (формулировку можно изменить)").pack(anchor="w")
        self._text_field(agenda, "planned_report", 3)
        ttk.Label(agenda, text="Замена докладчика (выберите сотрудника или впишите ФИО)").pack(anchor="w")
        self.speaker_box = ttk.Combobox(agenda, textvariable=self.speaker)
        self.speaker_box.pack(fill="x")

        decisions = ttk.Frame(tabs, padding=8)
        tabs.add(decisions, text="Решения")
        self._text_field(decisions, "decisions", 10)
        other = ttk.Frame(tabs, padding=8)
        tabs.add(other, text="Разное")
        ttk.Label(other, text="Добавляйте, правьте и удаляйте строки. Кнопка «Сохранить черновик» запомнит текст.").pack(anchor="w")
        self._text_field(other, "other", 10)

        ttk.Label(self, textvariable=self.status, wraplength=760).pack(fill="x", padx=8, pady=5)
        bottom = ttk.Frame(self, padding=8)
        bottom.pack(fill="x")
        feedback.add_button(bottom, self, FEATURE_TITLE, side="left")
        ttk.Button(bottom, text="Сформировать ODT", command=self._generate).pack(side="right")
        ttk.Button(bottom, text="Сохранить черновик", command=self._save).pack(side="right", padx=6)

    def _text_field(self, parent, key, height):
        field = ScrolledText(parent, wrap="word", height=height)
        field.pack(fill="both", expand=True, pady=4)
        self.fields[key] = field

    def _read_draft(self):
        return {
            "number": self.number.get(), "date": self.meeting_date.get(),
            "head": self.head.get(), "speaker": self.speaker.get(),
            "people": [dict(person) for person in self.people],
            **{key: field.get("1.0", "end-1c") for key, field in self.fields.items()},
        }

    def _load_period(self):
        try:
            year = int(self.year.get())
            if not 1900 <= year <= 9999:
                raise ValueError
            department = self.departments[self.department.current()]
            month = self.month.current() + 1
        except (ValueError, IndexError):
            messagebox.showerror("Период", "Выберите отделение, месяц и корректный год.", parent=self)
            return
        if self.context == (department, year, month):
            return
        if not self._confirm_leave():
            return
        try:
            draft = storage.load_draft(department, year, month)
            if draft is None:
                draft = service.new_draft(department, year, month, self.calendar)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Протокол", str(exc), parent=self)
            return
        self.context = department, year, month
        self.people = draft["people"]
        self.number.set(draft["number"])
        self.meeting_date.set(draft["date"])
        self.head.set(draft["head"])
        self.speaker.set(draft["speaker"])
        for key, field in self.fields.items():
            field.delete("1.0", "end")
            field.insert("1.0", draft[key])
        self._refresh_people()
        self.original = self._read_draft()
        self._show_period()

    def _show_period(self, note=""):
        dept, year, month = self.context
        text = f"Открыт ОСОД № {storage.department_number(dept)}, {service.MONTHS_NOM[month].lower()} {year}."
        if not self.calendar.has_year(year):
            text += " В справочнике нет календаря этого года. Проверьте дату совещания."
        elif not self.meeting_date.get():
            text += " Рабочих сред в месяце нет. Укажите дату вручную."
        self.status.set(f"{text} {note}".strip())

    def _refresh_people(self):
        self.table.delete(*self.table.get_children())
        for i, person in enumerate(self.people):
            status = "Присутствует" if person["present"] else "Отсутствует"
            self.table.insert("", "end", iid=str(i), values=(person["name"], status, person["reason"]))
        self.speaker_box.configure(values=[p["name"] for p in self.people if p["present"]])

    def _edit_selected(self):
        selected = self.table.selection()
        if selected:
            self._edit_person(int(selected[0]))

    def _delete_person(self):
        selected = self.table.selection()
        if selected:
            del self.people[int(selected[0])]
            self._refresh_people()

    def _edit_person(self, index):
        person = self.people[index] if index is not None else {"name": "", "present": True, "reason": ""}
        win = tk.Toplevel(self)
        win.title("Участник")
        win.transient(self)
        win.grab_set()
        form = ttk.Frame(win, padding=12)
        form.pack(fill="both", expand=True)
        name = tk.StringVar(master=win, value=person["name"])
        present = tk.BooleanVar(master=win, value=person["present"])
        reason = tk.StringVar(master=win, value=person["reason"])
        ttk.Label(form, text="ФИО").pack(anchor="w")
        entry = ttk.Entry(form, textvariable=name, width=44)
        entry.pack(fill="x")
        ttk.Checkbutton(form, text="Присутствует", variable=present).pack(anchor="w", pady=6)
        ttk.Label(form, text="Причина отсутствия").pack(anchor="w")
        ttk.Combobox(form, textvariable=reason, values=service.REASONS).pack(fill="x")

        def apply():
            if not name.get().strip():
                messagebox.showwarning("Участник", "Введите ФИО.", parent=win)
                return
            row = {"name": name.get().strip(), "present": present.get(),
                   "reason": "" if present.get() else reason.get().strip()}
            if index is None:
                self.people.append(row)
            else:
                self.people[index] = row
            self._refresh_people()
            win.destroy()

        ttk.Button(form, text="Сохранить", command=apply).pack(pady=(8, 0))
        entry.focus_set()

    def _save(self):
        if self.context is None:
            return False
        draft = self._read_draft()
        try:
            storage.save_draft(*self.context, draft)
        except OSError as exc:
            messagebox.showerror("Черновик", str(exc), parent=self)
            return False
        self.original = draft
        self._show_period("Черновик сохранён.")
        return True

    def _confirm_leave(self):
        if self.context is None or self._read_draft() == self.original:
            return True
        save = messagebox.askyesnocancel("Протокол", "Сохранить изменения в черновике?", parent=self)
        return save is not None and (not save or self._save())

    def _close(self):
        if self._confirm_leave():
            self.destroy()

    def _generate(self):
        if self.context is None:
            return
        dept, year, month = self.context
        draft = self._read_draft()
        try:
            service.validate(draft, year, month)
        except ValueError as exc:
            messagebox.showwarning("Протокол", str(exc), parent=self)
            return
        number = storage.department_number(dept)
        out = filedialog.asksaveasfilename(parent=self, defaultextension=".odt",
                                          initialfile=f"Протокол_ОСОД_{number}_{year}_{month:02d}.odt",
                                          initialdir=ui_state.last_dir("save") or None,
                                          filetypes=[("Документ OpenDocument", "*.odt")])
        if not out:
            return
        try:
            service.generate(out, dept, year, month, draft)
        except Exception as exc:
            messagebox.showerror("Ошибка формирования", str(exc), parent=self)
            return
        ui_state.set_last_dir(out, "save")
        ui_state.set_last_dept("protokol", dept["name"])
        archived = documents.save_file("protokol", out, {"dept": number, "year": year, "month": month,
                                                      "number": draft["number"], "date": draft["date"]})
        saved = self._save()
        note = f"Создан документ: {os.path.basename(out)}."
        if saved:
            note += " Черновик сохранён."
        if not archived:
            note += " Копию в архив сохранить не удалось."
        self._show_period(note)


def open_protokol(master):
    return ProtokolWindow(master)
