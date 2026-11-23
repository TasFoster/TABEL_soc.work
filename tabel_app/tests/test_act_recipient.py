from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.features.file_completion.names import recipient


class RecipientTests(unittest.TestCase):
    def test_named_beneficiary_has_priority(self):
        text = ("Заказчик: Петров Пётр Петрович\n"
                "получателя социальных услуг Иванова Анна Сергеевна\n(ФИО)")
        self.assertEqual(recipient(text), "Иванова_Анна_Сергеевна")

    def test_ambiguous_beneficiaries(self):
        text = "Получатель услуг: Иванов Иван\nПолучатель услуг: Петров Пётр"
        self.assertIsNone(recipient(text))
