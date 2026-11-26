from datetime import date
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from docx import Document
from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.file_completion import act_editor, rtf
from app.features.timesheet.calendar_ru import ProductionCalendar


TITLE = "Акт сдачи-приемки оказанных социальных услуг"
HEADER = "№ 7 за декабрь 2026 г. к договору № 9 от 01.12.2025"
CLIENT = "Получатель социальных услуг Клиентова Анна Петровна"
REFERENCE = "Договор действует 01.12.2026 - 31.12.2026"
SERVICE_DATES = "01.12.2026 - 31.12.2026"
DIRECTOR = "Директор филиала ________  (Тестова И.И.)"
WORKER = "Социальный работник ______ (Примерова О.О.)"
SIGNED = "«30» декабря 2026 г."


class ActEditorTests(unittest.TestCase):
    def test_docx_rolls_over_year_and_edits_only_act_fields(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "original.docx"
            doc = Document()
            for text in (TITLE, CLIENT, REFERENCE):
                doc.add_paragraph(text)
            header = doc.add_paragraph()
            header.add_run("№ 7 за ")
            header.add_run("декабрь").bold = True
            header.add_run(" 2026")
            header.add_run(" г. к договору № 9 от 01.12.2025")
            table = doc.add_table(rows=1, cols=3)
            for cell, text in zip(table.rows[0].cells, ("Услуга", "285,00", SERVICE_DATES)):
                cell.text = text
            for text in (DIRECTOR, WORKER, SIGNED):
                doc.add_paragraph(text)
            doc.save(source)
            before = source.read_bytes()
            pdf = folder / "test.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            writer.write(pdf)
            production = ProductionCalendar({"2027": {"holidays": ["01-29"]}})
            with patch.object(act_editor, "convert", return_value=pdf):
                result = act_editor.prepare(
                    source, folder, None, None, "", "Новая А.А.", production=production
                )

            edited = Document(result)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(result.name, "Клиентова_Анна_Петровна_акт.docx")
            self.assertEqual(
                [p.text for p in edited.paragraphs],
                [TITLE, CLIENT, REFERENCE, HEADER.replace("декабрь 2026", "январь 2027"),
                 "Директор филиала ________  (Новая А.А.)", WORKER, "«28» января 2027 г."],
            )
            self.assertTrue(edited.paragraphs[3].runs[1].bold)
            self.assertEqual(
                [cell.text for cell in edited.tables[0].rows[0].cells],
                ["Услуга", "285,00", "01.01.2027 - 31.01.2027"],
            )

    def test_rtf_fallback_preserves_table_and_allows_explicit_dates(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "original.rtf"
            intro = rtf.escape("\n".join((TITLE, HEADER, CLIENT, REFERENCE, "")))
            row = r"\trowd " + rtf.escape("Услуга") + r"\cell 23\cell " + SERVICE_DATES + r"\cell\row "
            ending = rtf.escape("\n".join((DIRECTOR.replace(" филиала", ""), WORKER, SIGNED)))
            raw = (r"{\rtf1\ansi\ansicpg1251\uc1 " + intro + row + ending + "}").encode("ascii")
            source.write_bytes(raw)
            with patch.object(act_editor, "convert", side_effect=act_editor.ConversionError):
                result = act_editor.prepare(
                    source, folder, date(2028, 2, 1), date(2028, 3, 1), "Новая О.О.", "Тестова И.И."
                )

            self.assertEqual(source.read_bytes(), raw)
            self.assertEqual(result.suffix, ".rtf")
            updated = result.read_bytes()
            self.assertIn(rb"\trowd ", updated)
            self.assertIn(rb"\cell\row ", updated)
            self.assertEqual(
                rtf.parse(updated)[0],
                "\n".join((TITLE, HEADER.replace("декабрь 2026", "февраль 2028"), CLIENT, REFERENCE,
                           "Услуга\t23\t01.02.2028 - 29.02.2028\t", DIRECTOR,
                           "Социальный работник ______ (Новая О.О.)", "«1» марта 2028 г.")),
            )
