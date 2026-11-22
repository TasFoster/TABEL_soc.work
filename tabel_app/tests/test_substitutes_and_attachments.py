from email import policy
from email.parser import BytesParser
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.feedback_mail import make_draft
from app.features.prilozhenie.calc import compute, unassigned_ranges
from app.features.prilozhenie.model import Absence, Redistribution, Worker


class SubstitutesAndAttachmentsTest(unittest.TestCase):
    def test_three_workers_split_dates_and_load(self):
        workers = [Worker(i, i, str(i), load_gor=6 if i == 1 else 0) for i in range(1, 5)]
        rows = [Redistribution("gor", 1, 2, 1, 5, 6), Redistribution("gor", 1, 3, 6, 10, 2)]
        self.assertEqual(unassigned_ranges(workers[0], "gor", 1, 10, [], rows), [(6, 10, 4)])
        rows.append(Redistribution("gor", 1, 4, 6, 10, 4))
        self.assertEqual(unassigned_ranges(workers[0], "gor", 1, 10, [], rows), [])
        result = compute(workers, list(range(1, 11)), 10, absences=[Absence(1, 1, 10)], redistributions=rows)
        self.assertEqual([row["totals"]["gor"] for row in result["workers"]], [0, 30, 10, 20])

    def test_mail_contains_original_files(self):
        with tempfile.TemporaryDirectory() as folder:
            files = [Path(folder) / name for name in ("Образец.xls", "Акт.docx")]
            for i, path in enumerate(files):
                path.write_bytes(bytes(range(256)) + bytes([i]))
            draft = make_draft("user@example.org", "Доработка", "Описание", files)
            parsed = BytesParser(policy=policy.default).parsebytes(draft)
            self.assertEqual(parsed["Subject"], "Доработка")
            self.assertEqual([(part.get_filename(), part.get_payload(decode=True))
                              for part in parsed.iter_attachments()], [(p.name, p.read_bytes()) for p in files])
