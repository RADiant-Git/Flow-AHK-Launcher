# -*- coding: utf-8 -*-
"""Генерация скрипта захвата и разбор его вывода.

Отдельный файл потому, что этот код раньше ломался именно здесь: шаблон со
сквозными фигурными скобками AHK несовместим со str.format, и проверка этого
нужна постоянная, а не «запустили один раз руками».
"""

import os
import shutil
import tempfile
import unittest

from core.ahk import capture
from core.ahk.runtime import AHKRuntime, locate_ahk


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestRender(unittest.TestCase):
    def test_timeout_substituted(self):
        self.assertIn('InputHook("L1 T10")', capture.render(10))
        self.assertIn('InputHook("L1 T3")', capture.render(3))

    def test_no_leftover_token(self):
        self.assertNotIn(capture.TIMEOUT_TOKEN, capture.render(10))

    def test_marker_present(self):
        self.assertIn(capture.MARKER, capture.render(10))

    def test_ahk_braces_survive(self):
        text = capture.render(10)
        self.assertIn('ih.KeyOpt("{All}", "E")', text)
        self.assertIn('"{LCtrl}{RCtrl}', text)

    def test_escape_cancels(self):
        text = capture.render(10)
        self.assertIn('Emit("Cancelled")', text)
        self.assertIn('key = "Escape" && mods = ""', text)

    def test_input_is_blocked(self):
        text = capture.render(10)
        self.assertIn("VisibleNonText := false", text)
        self.assertNotIn('InputHook("V', text)

    def test_modifiers_not_end_keys(self):
        self.assertIn('"-E"', capture.render(10))

    def test_uses_endmods(self):
        text = capture.render(10)
        self.assertIn("ih.EndMods", text)
        self.assertNotIn("GetKeyState", text)

    def test_output_shape(self):
        self.assertIn('Emit(human . key . "|" . prefix . key)', capture.render(10))

    @unittest.skipUnless(os.path.exists(locate_ahk()), "AutoHotkey не установлен")
    def test_rendered_script_is_valid_for_ahk(self):
        runtime = AHKRuntime()
        runtime.script_path = os.path.join(os.environ["TEMP"], "flowkey-cap-probe.ahk")
        for seconds in (1, 10):
            self.assertEqual(runtime.validate(capture.render(seconds)), "")


class TestParseOutput(unittest.TestCase):
    def test_combo(self):
        got = capture.parse_output("Ctrl + e|^e")
        self.assertTrue(got.ok)
        self.assertEqual((got.human, got.trigger), ("Ctrl + e", "^e"))

    def test_mouse(self):
        got = capture.parse_output("Middle Click|MButton")
        self.assertEqual(got.trigger, "MButton")
        self.assertEqual(got.human, "Middle Click")

    def test_cancelled(self):
        got = capture.parse_output("Cancelled")
        self.assertTrue(got.cancelled)
        self.assertFalse(got.ok)

    def test_timeout(self):
        self.assertTrue(capture.parse_output("Timeout").timed_out)

    def test_empty_is_timeout(self):
        got = capture.parse_output("")
        self.assertTrue(got.timed_out)

    def test_bare_key_without_pipe(self):
        got = capture.parse_output("Escape")
        self.assertTrue(got.ok)
        self.assertEqual(got.trigger, "Escape")


class TestEnsureScript(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="flowkey-cap-")
        self.path = os.path.join(self.dir, "nested", "capture.ahk")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_creates_missing_folder(self):
        capture.ensure_script(self.path, 10)
        self.assertTrue(os.path.exists(self.path))

    def test_idempotent(self):
        capture.ensure_script(self.path, 10)
        first = read(self.path)
        capture.ensure_script(self.path, 10)
        self.assertEqual(first, read(self.path))

    def test_rewrites_stale_version(self):
        capture.ensure_script(self.path, 10)   # создаёт вложенную папку
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("; FlowKey Manager capture v2\n")
        capture.ensure_script(self.path, 10)
        self.assertIn(capture.MARKER, read(self.path))

    def test_timeout_change_propagates(self):
        capture.ensure_script(self.path, 10)
        capture.ensure_script(self.path, 4)
        self.assertIn('InputHook("L1 T4")', read(self.path))


if __name__ == "__main__":
    unittest.main()
