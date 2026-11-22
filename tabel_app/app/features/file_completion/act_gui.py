from datetime import date, datetime
from pathlib import Path
import threading
from queue import SimpleQueue
from tkinter import Toplevel, StringVar, filedialog, messagebox, ttk

from ..timesheet.calendar_ru import ProductionCalendar
from ..timesheet.storage import load_calendar
from .act_editor import prepare, signing_day


def open_editor(parent):
    window = Toplevel(parent)
    window.title("Редактор актов")
    month = date.today()
    production = ProductionCalendar(load_calendar())
    ttk.Label(window, text=f"Период услуг: {month:%m.%Y}").pack(pady=5)
    fields = []
    for title, initial in (("Дата подписания", signing_day(month, production).strftime("%d.%m.%Y")),
                           ("Социальный работник (пусто — оставить из акта)", ""),
                           ("Директор филиала", "Колесниченко Е.И.")):
        ttk.Label(window, text=title).pack()
        value = StringVar(window, initial)
        ttk.Entry(window, textvariable=value, width=48).pack(padx=12, pady=4)
        fields.append(value)
    status = StringVar(window, "Для проверки одной страницы нужен Word или LibreOffice.")
    ttk.Label(window, textvariable=status).pack(padx=12)

    def run():
        try:
            signed = datetime.strptime(fields[0].get(), "%d.%m.%Y").date()
        except ValueError:
            return messagebox.showerror("Дата", "Введите дату в формате ДД.ММ.ГГГГ.", parent=window)
        worker, director = [v.get().strip() for v in fields[1:]]
        if not director:
            return messagebox.showerror("Директор", "Укажите ФИО директора.", parent=window)
        paths = filedialog.askopenfilenames(parent=window, filetypes=[("Акты (RTF, DOC, DOCX)", "*.rtf *.doc *.docx")])
        folder = filedialog.askdirectory(parent=window) if paths else None
        if not folder:
            return
        button.state(["disabled"])
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        status.set("Подготовка документов…")
        queue = SimpleQueue()
        def process():
            report = []
            for name in paths:
                try:
                    target = prepare(Path(name), Path(folder), month, signed, worker, director)
                    report.append(target.name)
                except Exception as exc:
                    report.append(f"{Path(name).name}: {exc}")
            queue.put(report)
        def poll():
            if queue.empty():
                window.after(200, poll)
                return
            status.set("Обработка завершена")
            button.state(["!disabled"])
            window.protocol("WM_DELETE_WINDOW", window.destroy)
            messagebox.showinfo("Результаты", "\n".join(queue.get()), parent=window)
        threading.Thread(target=process, daemon=True).start()
        window.after(200, poll)
    button = ttk.Button(window, text="Выбрать акты и папку результата…", command=run)
    button.pack(pady=10)
