from datetime import datetime
from pathlib import Path
import threading
from queue import SimpleQueue
from tkinter import Toplevel, StringVar, filedialog, messagebox, ttk

from ..timesheet.calendar_ru import ProductionCalendar
from ..timesheet.storage import load_calendar
from .act_editor import prepare


def open_editor(parent):
    window = Toplevel(parent)
    window.title("Редактор актов")
    window.resizable(False, False)
    production = ProductionCalendar(load_calendar())
    fields = []
    for title, initial in (("Период услуг (ММ.ГГГГ)", ""),
                           ("Дата подписания (ДД.ММ.ГГГГ)", ""),
                           ("Социальный работник (пусто — оставить из акта)", ""),
                           ("Директор филиала", "Колесниченко Е.И.")):
        ttk.Label(window, text=title).pack(pady=(5, 0))
        value = StringVar(window, initial)
        ttk.Entry(window, textvariable=value, width=48).pack(padx=12, pady=4)
        fields.append(value)
    ttk.Label(window, text="Пустой период — следующий месяц от периода каждого акта.\n"
                          "Пустая дата — последний рабочий день нового периода.",
              justify="center").pack(padx=12, pady=5)
    status = StringVar(window, "Для проверки одной страницы нужен Word или LibreOffice.")
    ttk.Label(window, textvariable=status).pack(padx=12)

    def run():
        period, signing_date, worker, director = [value.get().strip() for value in fields]
        try:
            month = datetime.strptime(period, "%m.%Y").date() if period else None
        except ValueError:
            return messagebox.showerror("Период услуг", "Введите период в формате ММ.ГГГГ.", parent=window)
        try:
            signed = datetime.strptime(signing_date, "%d.%m.%Y").date() if signing_date else None
        except ValueError:
            return messagebox.showerror("Дата", "Введите дату в формате ДД.ММ.ГГГГ.", parent=window)
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
                source = Path(name)
                try:
                    target = prepare(source, Path(folder), month, signed, worker, director,
                                     production=production)
                    result = f"{source.name} → {target.name}"
                    if target.suffix == ".rtf":
                        result += " — проверьте разбивку на страницы перед печатью."
                    report.append(result)
                except Exception as exc:
                    report.append(f"{source.name}: {exc}")
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
