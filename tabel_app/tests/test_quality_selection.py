"""Регрессия выборочного добавления клиентов в «Проверке качества»."""
from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.features.proverka_kachestva import gui


class QualitySelectionTest(unittest.TestCase):
    def select(self, count):
        clients = [(f"Получатель {i}", f"Адрес {i}", Mock())
                   for i in range(7)]
        for i, (_, _, var) in enumerate(clients):
            var.get.return_value = i < count
        window = SimpleNamespace(
            _client_vars=clients, _rows=[], _refresh_tree=Mock(),
            worker_var=Mock(**{"get.return_value": "Работник"}),
            thu_var=Mock(**{"get.return_value": "06.11.25"}),
        )
        with patch.object(gui, "messagebox") as messages, patch.object(
            gui.storage, "load_phone", return_value="123"
        ):
            gui.ProverkaKachestvaWindow._add_selected(window)
        return window, messages

    def test_one_to_five_selected_clients_keep_addresses_and_phones(self):
        for count in (1, 5):
            with self.subTest(count=count):
                window, messages = self.select(count)
                self.assertEqual(len(window._rows), count)
                self.assertEqual(window._rows[-1], {
                    "date": "06.11.25", "worker": "Работник",
                    "client": f"Получатель {count - 1}", "address": f"Адрес {count - 1}",
                    "phone": "123", "result": "нет",
                })
                window._refresh_tree.assert_called_once()
                self.assertEqual(messages.mock_calls, [])

    def test_more_than_five_selected_clients_leave_selection_and_rows_intact(self):
        window, messages = self.select(6)
        self.assertEqual(window._rows, [])
        for _, _, var in window._client_vars:
            var.set.assert_not_called()
        messages.showwarning.assert_called_once()

    def test_editable_year_refreshes_available_thursdays(self):
        interpreter = tk.Tcl()

        def fake_build(window):
            window.thu_combo = {}

        with patch.object(tk.Toplevel, "__init__", return_value=None), patch.object(
            gui.ProverkaKachestvaWindow, "_build", fake_build
        ), patch.multiple(gui.ProverkaKachestvaWindow, title=Mock(), geometry=Mock(), minsize=Mock()), patch.object(
            gui.ui_state, "get", side_effect=lambda key, default: default
        ), patch.object(tk, "_default_root", interpreter):
            window = gui.ProverkaKachestvaWindow()

        window.month_var.set("Октябрь")
        window.year_var.set(2026)
        self.assertEqual(window.thu_combo["values"], [
            "01.10.26", "08.10.26", "15.10.26", "22.10.26", "29.10.26",
        ])
        self.assertEqual(window.thu_var.get(), "01.10.26")
        window.year_var.set("")
        self.assertEqual(window.thu_combo["values"], [])
        self.assertEqual(window.thu_var.get(), "")
