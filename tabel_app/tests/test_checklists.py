"""Хранение и отправка чек-листов без обращения к почтовому сервису."""

from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import checklist_gui, checklists, db, feedback, storage
from app.features.registry import get_features


class ChecklistTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(storage, "app_base_dir", return_value=str(self.folder)))
        self.enterContext(patch.object(db, "_ENSURED", False))

    def test_versions_are_separate_and_preserve_an_empty_revision(self):
        self.assertEqual(checklists.load("timesheet"), checklists.Checklist())
        first = checklists.save("timesheet", ["Первый", "Второй"], 0)
        self.assertEqual(first, checklists.Checklist(1, ("Первый", "Второй")))
        self.assertEqual(checklists.load("proezd"), checklists.Checklist())
        checklists.save("proezd", ["Проезд"], 0)
        with self.assertRaises(checklists.ChecklistConflict):
            checklists.save("timesheet", ["Устаревший вариант"], 0)
        self.assertEqual(checklists.save("timesheet", first.items, 1), first)

        empty = checklists.save("timesheet", [], 1)
        self.assertEqual(checklists.load("timesheet"), checklists.Checklist(2))
        self.assertEqual(checklists.load("proezd").items, ("Проезд",))
        self.assertEqual(empty.message("Табель"),
                         "Раздел: Табель\nВерсия чек-листа: 2\n\nЧек-лист пуст.")

    def test_old_database_migrates_and_checklist_is_exported(self):
        db.settings_save({"checklist-test-existing-setting": 42})
        with closing(db.get_conn()) as conn, conn:
            conn.execute("DROP TABLE feature_checklists")
        with patch.object(db, "_ENSURED", False):
            self.assertEqual(checklists.load("timesheet"), checklists.Checklist())
        self.assertEqual(db.settings_load()["checklist-test-existing-setting"], 42)
        checklists.save("timesheet", ["Проверка"], 0)
        exported = db.export_db(self.folder / "export.db")
        with closing(sqlite3.connect(exported)) as conn:
            self.assertEqual(conn.execute("SELECT feature_key, version, items FROM feature_checklists").fetchall(),
                             [("timesheet", 1, '["Проверка"]')])


class ChecklistGuiTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.root.destroy)
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(storage, "app_base_dir", return_value=folder))
        self.enterContext(patch.object(db, "_ENSURED", False))

    def test_edit_save_and_send_full_snapshot(self):
        editor = checklist_gui.open_editor(self.root, "timesheet", "Табель")
        with patch.object(checklist_gui.simpledialog, "askstring", side_effect=["Первый", "Второй", "Третий"]):
            editor._add_item()
            editor._add_item()
            editor._edit_item()
        editor._remove_item()
        self.assertTrue(editor._save())
        editor.destroy()
        editor = checklist_gui.open_editor(self.root, "timesheet", "Табель")
        self.assertEqual(editor.items, ["Первый"])
        with patch.object(checklist_gui.simpledialog, "askstring", return_value="Второй пункт"):
            editor._add_item()

        messages = []

        def observe_draft():
            dialog, = editor.winfo_children()[-1:]
            messages.append((dialog._subject(), dialog._body(), dialog.text.cget("state")))
            dialog.destroy()

        self.root.after_idle(observe_draft)
        editor._send()
        subject, body, state = messages[0]
        self.assertEqual(subject, "Табель — Чек-лист — Табель")
        self.assertIn("Версия чек-листа: 2\n\n1. Первый\n2. Второй пункт", body)
        self.assertEqual(state, "disabled")
        self.assertEqual(editor.grab_current(), editor)
        self.assertEqual(checklists.load("timesheet").version, 2)

    def test_failed_checklist_send_keeps_message_and_offers_full_email_draft(self):
        long_item = "Подробный пункт " * 100
        snapshot = checklists.Checklist(3, (long_item.strip(), "Последний пункт"))
        dialog = feedback.open_feedback_dialog(self.root, "Планы", checklist_message=snapshot.message("Планы"))
        dialog.update()
        with patch.object(feedback, "_post_web3forms", return_value=False) as post, \
                patch.object(feedback.messagebox, "askyesno", return_value=True) as fallback, \
                patch.object(dialog, "_open_attached_draft") as draft, \
                patch.object(feedback.messagebox, "showinfo") as notice:
            dialog.send_button.invoke()
            deadline = time.monotonic() + 3
            while not draft.called and time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.01)
            post.assert_called_once()
            fallback.assert_called_once()
            draft.assert_called_once()
            notice.assert_not_called()
        self.assertEqual(post.call_args.args[0], "Табель — Чек-лист — Планы")
        self.assertIn("2. Последний пункт", post.call_args.args[1])
        self.assertIn(long_item.strip(), dialog._clipboard_text())
        self.assertEqual(dialog.text.cget("state"), "disabled")
        self.assertFalse(dialog.send_button.instate(["disabled"]))

    def test_button_is_visible_in_each_available_section(self):
        features = get_features()
        self.assertTrue(features)

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        for feature in features:
            with self.subTest(feature=feature.key):
                window = feature.open(self.root)
                try:
                    width, height = window.minsize()
                    window.geometry(f"{width}x{height}")
                    self.root.update()
                    button, = (child for child in descendants(window)
                               if isinstance(child, ttk.Button) and child.cget("text") == "Чек-лист")
                    self.assertTrue(button.winfo_ismapped())
                    self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())
                    button.invoke()
                    editor, = (child for child in window.winfo_children()
                               if isinstance(child, checklist_gui.ChecklistEditor))
                    self.assertEqual(editor.feature_key, feature.key)
                finally:
                    window.destroy()
