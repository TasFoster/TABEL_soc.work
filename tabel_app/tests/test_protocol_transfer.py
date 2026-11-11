"""Перенос и восстановление полного комплекта на изолированной базе."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import db


class ProtocolTransferTest(unittest.TestCase):
    def test_export_restore_backup_and_legacy(self):
        with tempfile.TemporaryDirectory() as directory, patch('app.core.storage.app_base_dir', return_value=directory), patch.object(db, 'ensure_seeded'):
            data = Path(directory) / 'data'
            data.mkdir()
            with sqlite3.connect(db.db_path()) as conn:
                conn.execute('CREATE TABLE departments (id INTEGER)')
                conn.execute('INSERT INTO departments VALUES (7)')
            folder = data / 'protokol'
            folder.mkdir()
            draft = folder / 'draft_db_7_2026_11.json'
            history = folder / 'history_ab12.json'
            draft.write_text(json.dumps({'agenda': 'Первая'}))
            history.write_text(json.dumps({'draft': {'agenda': 'История'}}))
            target = Path(directory) / 'export.db'
            db.export_db(str(target))
            backup = db.backup_db()
            self.assertTrue(Path(backup).exists())
            draft.write_text('{}')
            history.unlink()
            db.import_db(str(target))
            self.assertEqual(json.loads(draft.read_text())['agenda'], 'Первая')
            self.assertEqual(json.loads(history.read_text())['draft']['agenda'], 'История')
            legacy = Path(directory) / 'legacy.db'
            with sqlite3.connect(legacy) as conn:
                conn.execute('CREATE TABLE departments (id INTEGER)')
            db.import_db(str(legacy))
            self.assertTrue(history.exists())
            db.import_db(backup)
            self.assertEqual(json.loads(draft.read_text())['agenda'], 'Первая')

    def test_bad_bundle_does_not_change_data(self):
        with tempfile.TemporaryDirectory() as directory, patch('app.core.storage.app_base_dir', return_value=directory):
            data = Path(directory) / 'data'
            data.mkdir()
            source = Path(directory) / 'bad.db'
            with sqlite3.connect(source) as conn:
                conn.execute('CREATE TABLE departments (id INTEGER)')
                conn.execute('CREATE TABLE transfer_files (name TEXT, content BLOB)')
                conn.execute('INSERT INTO transfer_files VALUES (?, ?)', ('../escape.json', b'{}'))
            with self.assertRaises(ValueError):
                db.import_db(str(source))
            self.assertFalse(Path(db.db_path()).exists())
