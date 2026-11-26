"""Проверка доступности кнопок на минимальном размере окна Tk."""
import gc
import sys
import tempfile
import tkinter as tk
import unittest
from datetime import date
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import db, feedback, storage
from app.features.file_completion import act_gui
from app.features.file_completion.gui import open_file_completion
from app.features.plany.gui import open_plany
from app.features.protokol.gui import open_protokol
from app.features.proverka_kachestva.gui import open_proverka_kachestva
from app.reference_gui import open_reference


def buttons(widget):
    if isinstance(widget, ttk.Notebook):
        yield from buttons(widget.nametowidget(widget.select()))
        return
    for child in widget.winfo_children():
        if isinstance(child, (tk.Toplevel, tk.Canvas)):
            continue
        if isinstance(child, (ttk.Button, tk.Button)):
            yield child
        yield from buttons(child)


class WindowLayoutTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.addCleanup(gc.collect)
        self.addCleanup(self.root.destroy)
        self.enterContext(patch.object(storage, "app_base_dir", return_value=folder))
        self.enterContext(patch.object(db, "_ENSURED", False))

    def assert_buttons_fit(self, window):
        self.root.update()
        if all(window.resizable()):
            width, height = window.wm_minsize()
            window.geometry(f"{width}x{height}")
            self.root.update()
        action_buttons = list(buttons(window))
        self.assertTrue(action_buttons, window.title())
        for button in action_buttons:
            with self.subTest(window=window.title(), button=button.cget("text")):
                self.assertTrue(button.winfo_ismapped(), "Кнопка не отображается")
                width, height = button.winfo_width(), button.winfo_height()
                self.assertGreaterEqual(width, button.winfo_reqwidth())
                self.assertGreaterEqual(height, button.winfo_reqheight())
                parent = button.master
                while parent is not None:
                    x = button.winfo_rootx() - parent.winfo_rootx()
                    y = button.winfo_rooty() - parent.winfo_rooty()
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + width, parent.winfo_width())
                    self.assertLessEqual(y + height, parent.winfo_height())
                    if parent is window:
                        break
                    parent = parent.master

    def test_main_windows(self):
        for open_window in (open_plany, open_protokol, open_proverka_kachestva,
                            open_file_completion, open_reference):
            with self.subTest(open_window=open_window.__name__):
                window = open_window(self.root)
                try:
                    self.assert_buttons_fit(window)
                    if open_window is open_protokol:
                        notebook = next(child for child in window.winfo_children()
                                        if isinstance(child, ttk.Notebook))
                        for tab in notebook.tabs()[1:]:
                            notebook.select(tab)
                            self.assert_buttons_fit(window)
                finally:
                    window.destroy()

    def test_subdialogs(self):
        for open_window, action in ((open_file_completion, "Правила"),
                                    (open_file_completion, "Редактор актов…"),
                                    (open_reference, "Экспорт / импорт данных…")):
            with self.subTest(action=action):
                window = open_window(self.root)
                try:
                    button = next(button for button in buttons(window) if button.cget("text") == action)
                    button.invoke()
                    dialog, = (child for child in window.winfo_children() if isinstance(child, tk.Toplevel))
                    self.assert_buttons_fit(dialog)
                finally:
                    window.destroy()
        dialog = feedback.open_feedback_dialog(self.root, "Проверка")
        self.assert_buttons_fit(dialog)

    def test_act_editor_uses_current_fields_on_each_batch(self):
        act_gui.open_editor(self.root)
        dialog, = self.root.winfo_children()
        button, = buttons(dialog)
        period, signing_date, worker, director = (
            child for child in dialog.winfo_children() if isinstance(child, ttk.Entry)
        )
        paths = ("исходный-ноябрь.rtf", "исходный-октябрь.docx")
        folder = Path("результаты")
        targets = (folder / "Получатель Первый акт.rtf", folder / "Получатель Второй акт.docx")
        finished = tk.BooleanVar(dialog)

        with (patch.object(act_gui.filedialog, "askopenfilenames", return_value=paths),
              patch.object(act_gui.filedialog, "askdirectory", return_value=str(folder)),
              patch.object(act_gui, "prepare", side_effect=targets * 2) as prepare,
              patch.object(act_gui.messagebox, "showinfo", side_effect=lambda *a, **k: finished.set(True)) as report):
            for expected in ((None, None, "", director.get()),
                             (date(2026, 12, 1), date(2026, 12, 30), "Работник Р.Р.", director.get())):
                if expected[0] is not None:
                    period.insert(0, "12.2026")
                    signing_date.insert(0, "30.12.2026")
                    worker.insert(0, "Работник Р.Р.")
                finished.set(False)
                button.invoke()
                timeout = dialog.after(3000, lambda: finished.set(False))
                dialog.wait_variable(finished)
                dialog.after_cancel(timeout)
                self.assertTrue(finished.get(), "Редактор не показал результаты")
                self.assertFalse(button.instate(["disabled"]))
                self.assertEqual([call.args for call in prepare.call_args_list[-2:]],
                                 [(Path(path), folder, *expected) for path in paths])
                self.assertIn(f"{paths[0]} → {targets[0].name}", report.call_args.args[1])
