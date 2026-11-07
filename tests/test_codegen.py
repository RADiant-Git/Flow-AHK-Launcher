# -*- coding: utf-8 -*-
"""Кодогенерация AHK. Модуль чистый: AutoHotkey не нужен для большинства тестов."""

import os
import unittest

from core.ahk import codegen
from core.ahk.runtime import AHKRuntime, locate_ahk
from core.model import MODE_REMAP, RuleSet, build
from tests.support import TempCase


class TestSendExpression(TempCase):
    def test_key_name_braced(self):
        self.assertEqual(codegen.send_expression("Escape", self.catalog), "{Escape}")
        self.assertEqual(codegen.send_expression("Media_Play_Pause", self.catalog),
                         "{Media_Play_Pause}")

    def test_raw_sequence_untouched(self):
        self.assertEqual(codegen.send_expression("^ew", self.catalog), "^ew")
        self.assertEqual(codegen.send_expression("{LCtrl down}e", self.catalog),
                         "{LCtrl down}e")

    def test_text_target_untouched(self):
        self.assertEqual(codegen.send_expression("hello world", self.catalog),
                         "hello world")

    def test_modifier_plus_key_name_is_braced_around_the_key(self):
        """Регрессия: Send('^AppsKey') жмёт Ctrl+Shift+A и печатает «ppsKey»."""
        self.assertEqual(codegen.send_expression("^AppsKey", self.catalog),
                         "^{AppsKey}")
        self.assertEqual(codegen.send_expression("!+PgUp", self.catalog), "!+{PgUp}")
        self.assertEqual(codegen.send_expression("#e", self.catalog), "#{e}")

    def test_modifier_prefixes_are_not_glued_to_brace(self):
        for action, expected in [("^Escape", "^{Escape}"), ("+MButton", "+{MButton}"),
                                 ("^!F5", "^!{F5}")]:
            self.assertEqual(codegen.send_expression(action, self.catalog), expected)


class TestAhkString(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(codegen.ahk_string("abc"), "'abc'")

    def test_single_quote(self):
        self.assertEqual(codegen.ahk_string("a'b"), "'a`'b'")

    def test_backtick(self):
        self.assertEqual(codegen.ahk_string("a`b"), "'a``b'")

    def test_both(self):
        self.assertEqual(codegen.ahk_string("a'b`c"), "'a`'b``c'")

    def test_newlines_flattened(self):
        self.assertNotIn("\n", codegen.ahk_string("a\nb"))
        self.assertNotIn("\r", codegen.ahk_string("a\rb"))


class TestRender(TempCase):
    def render(self, *rules, **kw):
        return codegen.render(RuleSet(rules), self.catalog, kw.get("paused", False))

    def test_header(self):
        text, _ = self.render(build(self.catalog, trigger="w", action="esc"))
        self.assertTrue(text.startswith("#Requires AutoHotkey v2.0"))
        self.assertIn("#UseHook True", text)

    def test_send_key_name(self):
        text, _ = self.render(build(self.catalog, trigger="w", action="Media_Play_Pause"))
        self.assertIn("*w::Send('{Media_Play_Pause}')", text)

    def test_send_raw(self):
        text, _ = self.render(build(self.catalog, trigger="w", action="^ew"))
        self.assertIn("*w::Send('^ew')", text)

    def test_remap_line(self):
        text, _ = self.render(build(self.catalog, trigger="CapsLock", action="Escape",
                                    mode=MODE_REMAP))
        self.assertIn("*CapsLock::Escape", text)
        self.assertNotIn("Send(", text)

    def test_scope_block(self):
        text, _ = self.render(build(self.catalog, trigger="c", action="esc",
                                    scope="Code.exe"))
        self.assertIn("#HotIf WinActive('ahk_exe Code.exe')", text)

    def test_global_scope_block(self):
        text, _ = self.render(build(self.catalog, trigger="c", action="esc"))
        self.assertIn("#HotIf\n*c::", text)

    def test_scopes_grouped_separately(self):
        text, _ = self.render(
            build(self.catalog, trigger="c", action="esc"),
            build(self.catalog, trigger="d", action="tab", scope="Code.exe"),
        )
        self.assertEqual(text.count("#HotIf WinActive("), 1)
        self.assertEqual(text.count("#HotIf\n"), 1)

    def test_quotes_in_action_escaped(self):
        text, _ = self.render(build(self.catalog, trigger="w", action="a'b"))
        self.assertIn("Send('a`'b')", text)

    def test_quotes_in_scope_escaped_and_rejected(self):
        from core.model import InvalidScope

        with self.assertRaises(InvalidScope):
            build(self.catalog, trigger="w", action="esc",
                  scope='x") or WinActive("y')

    def test_disabled_not_rendered(self):
        text, _ = self.render(build(self.catalog, trigger="w", action="esc",
                                    enabled=False))
        self.assertNotIn("*w::", text)
        self.assertNotIn("InstallKeybdHook", text)

    def test_empty_set_has_no_hooks(self):
        text, notes = self.render()
        self.assertNotIn("InstallKeybdHook", text)
        self.assertNotIn("InstallMouseHook", text)
        self.assertEqual(notes, [])

    def test_paused(self):
        text, _ = self.render(build(self.catalog, trigger="w", action="esc"), paused=True)
        self.assertIn("Suspend(True)", text)

    def test_captured_action_with_modifier_renders_correctly(self):
        """Регрессия из практики: кнопка «назад» мыши → Ctrl+Apps."""
        text, _ = self.render(build(self.catalog, trigger="XButton1",
                                    action="^AppsKey"))
        self.assertIn("*XButton1::Send('^{AppsKey}')", text)
        self.assertNotIn("Send('^AppsKey')", text)

    def test_transparent_prefix(self):
        text, _ = self.render(build(self.catalog, trigger="w", action="esc",
                                    transparent=True))
        self.assertIn("~*w::Send('{Escape}')", text)

    def test_no_transparent_prefix_by_default(self):
        text, _ = self.render(build(self.catalog, trigger="w", action="esc"))
        self.assertIn("*w::Send('{Escape}')", text)
        self.assertNotIn("~*", text)

    def test_win_shortcut_action_renders_correctly(self):
        text, _ = self.render(build(self.catalog, trigger="#w", action="#e"))
        self.assertIn("*#w::Send('#{e}')", text)

    def test_hash_is_stable_and_content_sensitive(self):
        rule = build(self.catalog, trigger="w", action="esc")
        a = codegen.script_hash(self.render(rule)[0])
        b = codegen.script_hash(self.render(rule)[0])
        c = codegen.script_hash(self.render(build(self.catalog, trigger="q", action="esc"))[0])
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    @unittest.skipUnless(os.path.exists(locate_ahk()), "AutoHotkey не установлен")
    def test_generated_script_passes_ahk_validate(self):
        text, _ = self.render(
            build(self.catalog, trigger="^!w", action="Media_Play_Pause"),
            build(self.catalog, trigger="CapsLock", action="Escape", mode=MODE_REMAP),
            build(self.catalog, trigger="c", action="esc", scope="Code.exe"),
            build(self.catalog, trigger="F8", action="it's a test"),
            build(self.catalog, trigger="F9", action="esc", transparent=True),
        )
        runtime = AHKRuntime()
        runtime.script_path = os.path.join(os.environ["TEMP"], "flowkey-render-test.ahk")
        self.assertEqual(runtime.validate(text), "")


if __name__ == "__main__":
    unittest.main()
