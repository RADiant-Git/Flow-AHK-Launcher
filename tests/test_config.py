# -*- coding: utf-8 -*-
"""Куда плагин кладёт пользовательские данные.

Проверка нужна потому, что ошибка здесь стоит дорого и незаметно: Flow Launcher
удаляет папку плагина при каждом обновлении, поэтому «данные рядом с кодом»
означают «правила пропали после апдейта». Формулы путей обязаны совпадать с
DataLocation.cs самого Flow Launcher.
"""

import os
import shutil
import tempfile
import unittest

from core import config


class TestFlowDataDir(unittest.TestCase):
    def test_portable_wins_when_userdata_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "UserData"))
            got = config.flow_data_dir(tmp, os.path.join("C:", "roaming"))
            self.assertEqual(got, os.path.join(tmp, "UserData"))

    def test_dead_marker_disables_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            portable = os.path.join(tmp, "UserData")
            os.makedirs(portable)
            open(os.path.join(portable, config.DEAD_MARKER), "w").close()
            got = config.flow_data_dir(tmp, os.path.join("C:", "roaming"))
            self.assertEqual(got, os.path.join("C:", "roaming", "FlowLauncher"))

    def test_absent_userdata_falls_back_to_roaming(self):
        with tempfile.TemporaryDirectory() as tmp:
            got = config.flow_data_dir(tmp, os.path.join("C:", "roaming"))
            self.assertEqual(got, os.path.join("C:", "roaming", "FlowLauncher"))

    def test_roaming_without_program_dir(self):
        got = config.flow_data_dir("", os.path.join("C:", "roaming"))
        self.assertEqual(got, os.path.join("C:", "roaming", "FlowLauncher"))

    def test_nothing_without_environment(self):
        self.assertEqual(config.flow_data_dir("", ""), "")


class TestPluginDataDir(unittest.TestCase):
    def test_builds_settings_path(self):
        got = config.plugin_data_dir("FlowKey Manager", "", os.path.join("C:", "roaming"))
        self.assertEqual(
            got,
            os.path.join("C:", "roaming", "FlowLauncher", "Settings", "Plugins",
                         "FlowKey Manager"))

    def test_portable_settings_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "UserData"))
            got = config.plugin_data_dir("FlowKey Manager", tmp, "")
            self.assertEqual(
                got,
                os.path.join(tmp, "UserData", "Settings", "Plugins", "FlowKey Manager"))

    def test_no_name_or_no_root_means_fallback(self):
        self.assertEqual(config.plugin_data_dir("", "x", "y"), "")
        self.assertEqual(config.plugin_data_dir("Name", "", ""), "")

    def test_does_not_touch_disk(self):
        """Каталог только вычисляется: создаёт его первая запись."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "UserData"))
            got = config.plugin_data_dir("FlowKey Manager", tmp, "")
            self.assertTrue(got)
            self.assertFalse(os.path.exists(got))

    def test_shipped_paths_are_consistent(self):
        for path in (config.RULES_FILE, config.STATE_FILE, config.RUNTIME_SCRIPT):
            self.assertTrue(os.path.isabs(path), path)
            self.assertEqual(os.path.dirname(path),
                             config.DATA_DIR or config.BASE_DIR)


class TestMigrateLegacy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="flowkey-cfg-")
        self.legacy = os.path.join(self.tmp, "plugin", "modules.json")
        self.target = os.path.join(self.tmp, "data", "modules.json")
        os.makedirs(os.path.dirname(self.legacy))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, path, text):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_copies_and_creates_target_folder(self):
        self.write(self.legacy, "v1")
        self.assertTrue(config.migrate_legacy(self.legacy, self.target))
        self.assertEqual(self.read(self.target), "v1")
        # исходник остаётся на месте: старая папка ещё живёт
        self.assertEqual(self.read(self.legacy), "v1")

    def test_does_not_overwrite_existing(self):
        self.write(self.legacy, "старое")
        os.makedirs(os.path.dirname(self.target))
        self.write(self.target, "актуальное")
        self.assertFalse(config.migrate_legacy(self.legacy, self.target))
        self.assertEqual(self.read(self.target), "актуальное")

    def test_second_run_is_noop(self):
        self.write(self.legacy, "v1")
        self.assertTrue(config.migrate_legacy(self.legacy, self.target))
        self.assertFalse(config.migrate_legacy(self.legacy, self.target))

    def test_missing_legacy_is_not_an_error(self):
        self.assertFalse(config.migrate_legacy(self.legacy, self.target))
        self.assertFalse(os.path.exists(self.target))

    def test_no_target_means_fallback_mode(self):
        self.write(self.legacy, "v1")
        self.assertFalse(config.migrate_legacy(self.legacy, ""))
        self.assertFalse(config.migrate_legacy(self.legacy, self.legacy))


if __name__ == "__main__":
    unittest.main()
