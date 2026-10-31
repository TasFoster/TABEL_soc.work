"""Проверки манифеста и обновления без сети и запуска установщиков."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core import updater

spec = importlib.util.spec_from_file_location("make_manifest", ROOT / "tools/make_manifest.py")
manifest_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest_tool)


class UpdatesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.full, self.lite = root / "Tabel-full-setup.exe", root / "Tabel-lite-setup.exe"
        self.full.write_bytes(b"MZfull installer")
        self.lite.write_bytes(b"MZlite installer")
        self.manifest = manifest_tool.build_manifest("9.8.7", "TasFoster/TABEL_soc.work", self.full, self.lite)

    def test_manifest_hashes_sizes_and_pinned_urls(self):
        for variant, path in (("full", self.full), ("lite", self.lite)):
            entry = self.manifest["latest"][variant]
            self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(entry["size"], path.stat().st_size)
            self.assertTrue(entry["url"].endswith("/v9.8.7/" + path.name))

    def test_variant_selection_and_real_hash_check(self):
        with patch.object(updater, "_http_get_json", return_value=self.manifest):
            for variant, path in (("full", self.full), ("lite", self.lite)):
                with patch.object(updater, "variant_key", return_value=variant):
                    info = updater.check_for_update()
                    self.assertTrue(updater.verify_sha256(path, info["sha256"]))
                    self.assertTrue(info["url"].endswith(path.name))
        self.full.write_bytes(b"changed")
        self.assertFalse(updater.verify_sha256(self.full, self.manifest["latest"]["full"]["sha256"]))
        self.assertFalse(updater.verify_sha256(self.full, ""))

    def test_current_version_no_update(self):
        with patch.object(updater, "APP_VERSION", "9.8.7"), patch.object(updater, "_http_get_json", return_value=self.manifest):
            self.assertIsNone(updater.check_for_update())

    def test_missing_hash_rejected(self):
        self.manifest["latest"]["full"]["sha256"] = ""
        with patch.object(updater, "variant_key", return_value="full"), patch.object(updater, "_http_get_json", return_value=self.manifest):
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update()

    def test_http_installer_rejected(self):
        self.manifest["latest"]["full"]["url"] = "http://example.invalid/setup.exe"
        with patch.dict(os.environ, {"TABEL_UPDATE_INSECURE": "0"}), patch.object(updater, "variant_key", return_value="full"), patch.object(updater, "_http_get_json", return_value=self.manifest):
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update()

    def test_channel_and_test_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIn("/releases/latest/download/version.json", updater._manifest_url())
            with patch.object(updater, "UPDATE_CHANNEL", "yandex"), patch.object(updater, "_yadisk_href", return_value="legacy"):
                self.assertEqual(updater._manifest_url(), "legacy")
        with patch.dict(os.environ, {"TABEL_UPDATE_MANIFEST": "http://localhost/version.json"}):
            self.assertEqual(updater._manifest_url(), "http://localhost/version.json")

    def test_invalid_inputs_do_not_make_manifest(self):
        self.full.unlink()
        with self.assertRaises(ValueError):
            manifest_tool.build_manifest("9.8.7", "TasFoster/TABEL_soc.work", self.full, self.lite)
        with self.assertRaises(ValueError):
            manifest_tool.build_manifest("../../bad", "TasFoster/TABEL_soc.work", self.lite, self.lite)


if __name__ == "__main__":
    unittest.main()
