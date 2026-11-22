"""Проверка отправки и восстановления формы без обращения к почтовому сервису."""
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from app.core import feedback


class FeedbackTest(unittest.TestCase):
    def test_send_and_retry(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        dialog = feedback.open_feedback_dialog(root, "Дополнение файлов")
        dialog.text.insert("1.0", "Тест")
        dialog.cat_var.set("Доработка")
        for success in (False, True):
            with patch.object(feedback, "_post_web3forms", return_value=success) as post, \
                 patch.object(feedback.messagebox, "askyesno", return_value=False) as fallback, \
                 patch.object(feedback.messagebox, "showinfo") as notice:
                dialog.send_button.invoke()
                deadline = time.monotonic() + 4
                while not (fallback.called or notice.called) and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                post.assert_called_once()
                self.assertIn("Доработка — Дополнение файлов", post.call_args.args[0])
                if success:
                    notice.assert_called_once()
                    self.assertFalse(dialog.winfo_exists())
                else:
                    fallback.assert_called_once()
                    self.assertEqual(dialog.text.get("1.0", "end-1c"), "Тест")
                    self.assertFalse(dialog.send_button.instate(["disabled"]))
