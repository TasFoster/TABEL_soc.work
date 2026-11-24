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
from app.core import storage, updater

spec = importlib.util.spec_from_file_location("make_manifest", ROOT / "tools/make_manifest.py")
manifest_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest_tool)


class UpdatesTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(updater.sys, "platform", "win32"))
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

    def test_platform_entries_do_not_cross_update(self):
        root = Path(self.temp.name)
        linux_full = root / "tabel_9.8.7_amd64.deb"
        linux_lite = root / "tabel-lite_9.8.7_amd64.deb"
        for installer in (linux_full, linux_lite):
            installer.write_bytes(b"!<arch>\n" + installer.name.encode("ascii"))
        manifest = manifest_tool.build_manifest(
            "9.8.7", "TasFoster/TABEL_soc.work", self.full, self.lite,
            linux_full=linux_full, linux_lite=linux_lite,
        )
        self.assertEqual(manifest["latest"]["full"], self.manifest["latest"]["full"])
        self.assertEqual(manifest["latest"]["lite"], self.manifest["latest"]["lite"])
        with patch.object(updater.sys, "platform", "linux"), patch.object(updater.platform, "machine", return_value="x86_64"):
            self.assertTrue(updater.temp_installer_path("9.8.7").endswith(".deb"))
            with patch.object(updater, "_http_get_json", return_value=self.manifest):
                self.assertIsNone(updater.check_for_update())
            with patch.object(updater, "_http_get_json", return_value=manifest):
                for variant, installer in (("full", linux_full), ("lite", linux_lite)):
                    with patch.object(updater, "variant_key", return_value=variant):
                        info = updater.check_for_update()
                        self.assertTrue(info["url"].endswith(installer.name))
                        self.assertTrue(updater.verify_sha256(installer, info["sha256"]))
                with patch.object(updater.platform, "machine", return_value="aarch64"):
                    self.assertIsNone(updater.check_for_update())

    def test_frozen_linux_paths_follow_xdg(self):
        root = Path(self.temp.name)
        with patch.object(storage.sys, "platform", "linux"), patch.object(storage.sys, "frozen", True, create=True):
            for package in ("tabel", "tabel-lite"):
                with patch.object(storage.sys, "executable", f"/usr/lib/{package}/{package}"):
                    with patch.dict(os.environ, {"XDG_DATA_HOME": str(root), "HOME": str(root)}):
                        self.assertEqual(storage.app_base_dir(), str(root / package))
                    with patch.dict(os.environ, {"XDG_DATA_HOME": "relative", "HOME": str(root)}):
                        self.assertEqual(storage.app_base_dir(), str(root / ".local" / "share" / package))


if __name__ == "__main__":
    unittest.main()
