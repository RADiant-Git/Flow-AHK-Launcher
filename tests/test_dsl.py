# -*- coding: utf-8 -*-
"""DSL: разбор формул в черновик правила."""

import unittest

from core import dsl
from core.dsl import DslError
from tests.support import TempCase


class TestParse(TempCase):
    def parse(self, formula):
        return dsl.parse(formula, self.catalog)

    def test_simple(self):
        draft = self.parse("w -> esc")
        self.assertEqual((draft.trigger, draft.action), ("w", "esc"))
        self.assertFalse(draft.want_remap)
        self.assertEqual(draft.scope, "*")

    def test_modifiers(self):
        draft = self.parse("alt + shift + c -> esc")
        self.assertEqual(draft.trigger, "!+c")
        self.assertEqual(draft.human, "Alt + Shift + C")
        self.assertFalse(draft.want_remap)

    def test_remap_marker(self):
        draft = self.parse("alt + !c -> esc")
        self.assertEqual(draft.trigger, "!c")
        self.assertTrue(draft.want_remap)

    def test_scope(self):
        draft = self.parse("@Code.exe alt + c -> esc")
        self.assertEqual(draft.scope, "Code.exe")
        self.assertEqual(draft.trigger, "!c")

    def test_raw_send_target(self):
        draft = self.parse("w -> ^ew")
        self.assertEqual(draft.action, "^ew")

    def test_target_with_spaces_normalized(self):
        draft = self.parse("w ->   a   b ")
        self.assertEqual(draft.action, "a b")

    def test_target_cannot_contain_newline(self):
        draft = self.parse("w -> a\nb")
        self.assertNotIn("\n", draft.action)
        self.assertEqual(draft.action, "a b")

    def test_human_label(self):
        draft = self.parse("ctrl + w -> esc")
        self.assertEqual(draft.human, "Ctrl + W")

    def test_extra_spaces_and_case(self):
        draft = self.parse("  ALT  +  W   ->   ESC ")
        self.assertEqual(draft.trigger, "!w")
        self.assertEqual(draft.action, "ESC")


class TestRejects(TempCase):
    def test_missing_arrow(self):
        with self.assertRaises(DslError):
            dsl.parse("w", self.catalog)

    def test_empty_action(self):
        with self.assertRaises(DslError):
            dsl.parse("w ->", self.catalog)

    def test_empty_trigger(self):
        with self.assertRaises(DslError):
            dsl.parse("-> esc", self.catalog)

    def test_empty_formula(self):
        with self.assertRaises(DslError):
            dsl.parse("", self.catalog)

    def test_unknown_modifier(self):
        with self.assertRaises(DslError):
            dsl.parse("hyper + c -> esc", self.catalog)

    def test_bare_at(self):
        with self.assertRaises(DslError):
            dsl.parse("@ w -> esc", self.catalog)

    def test_bang_without_key(self):
        with self.assertRaises(DslError):
            dsl.parse("! -> esc", self.catalog)


class TestDraftToRule(TempCase):
    def test_formula_to_valid_rule(self):
        draft = dsl.parse("alt + shift + !c -> esc", self.catalog)
        rule, notes = draft.finalize(self.catalog)
        self.assertEqual(rule.trigger, "!+c")
        self.assertEqual(rule.action, "Escape")
        self.assertEqual(rule.mode, "remap")
        self.assertEqual(notes, [])

    def test_scope_survives(self):
        rule, _ = dsl.parse("@firefox.exe w -> esc", self.catalog).finalize(self.catalog)
        self.assertEqual(rule.scope, "firefox.exe")

    def test_bogus_trigger_rejected_before_storage(self):
        """Связка DSL → модель: мусор не должен доходить до генератора AHK."""
        draft = dsl.parse("NotAKey -> esc", self.catalog)
        with self.assertRaises(Exception):
            draft.finalize(self.catalog)


if __name__ == "__main__":
    unittest.main()
