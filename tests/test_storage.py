# -*- coding: utf-8 -*-
"""Хранилище: атомарность, блокировка, миграция и устойчивость к BOM."""

import json
import os

from core.model import DuplicateTrigger, RuleNotFound, RuleSet, build
from core.session import AWAIT_ACTION, Wizard
from core.storage import RuleStore, StateStore
from tests.support import TempCase


class TestRuleStore(TempCase):
    def test_missing_file_is_empty(self):
        self.assertEqual(len(self.ctx.ruleset()), 0)

    def test_save_uses_format_version(self):
        self.ctx.rules.save(RuleSet([build(self.catalog, trigger="w", action="esc")]))
        with open(self.rules_path, encoding="utf-8") as handle:
            doc = json.load(handle)
        self.assertEqual(doc["format_version"], 2)
        self.assertEqual(list(doc), ["format_version", "rules"])

    def test_file_has_no_bom(self):
        self.ctx.rules.save(RuleSet([build(self.catalog, trigger="w", action="esc")]))
        with open(self.rules_path, "rb") as handle:
            self.assertFalse(handle.read(3) == b"\xef\xbb\xbf")

    def test_read_tolerates_bom(self):
        """Правила не должны «исчезать» из-за BOM от стороннего редактора."""
        self.ctx.rules.save(RuleSet([build(self.catalog, trigger="w", action="esc")]))
        with open(self.rules_path, "rb") as handle:
            payload = handle.read()
        with open(self.rules_path, "wb") as handle:
            handle.write(b"\xef\xbb\xbf" + payload)
        self.assertEqual(len(self.ctx.rules.load(self.catalog)), 1)

    def test_corrupt_file_does_not_raise(self):
        with open(self.rules_path, "w", encoding="utf-8") as handle:
            handle.write("{ это не json")
        self.assertEqual(len(self.ctx.rules.load(self.catalog)), 0)

    def test_mutate_rolls_back_on_error(self):
        rule = build(self.catalog, trigger="w", action="esc")
        self.ctx.rules.save(RuleSet([rule]))
        with self.assertRaises(RuleNotFound):
            self.ctx.rules.mutate(lambda rs: (None, rs.remove("нет")))
        with open(self.rules_path, encoding="utf-8") as handle:
            self.assertEqual(len(json.load(handle)["rules"]), 1)

    def test_mutate_keeps_conflict_unwritten(self):
        rule = build(self.catalog, trigger="w", action="esc")
        self.ctx.rules.save(RuleSet([rule]))
        twin = build(self.catalog, trigger="w", action="tab")
        with self.assertRaises(DuplicateTrigger):
            self.ctx.rules.mutate(lambda rs: (None, rs.add(twin)))
        self.assertEqual(len(self.ctx.rules.load(self.catalog)), 1)

    def test_write_is_atomic_via_temp(self):
        self.ctx.rules.save(RuleSet([build(self.catalog, trigger="w", action="esc")]))
        self.assertFalse(os.path.exists(self.rules_path + ".tmp"))


class TestStateStore(TempCase):
    def test_defaults(self):
        state = self.ctx.state.load()
        self.assertEqual(state["wizard"], {})
        self.assertFalse(state["global_paused"])
        self.assertEqual(state["notices"], [])

    def test_wizard_roundtrip(self):
        wizard = Wizard().begin_capture(True).captured("^w", "Ctrl + w")
        self.ctx.state.set_wizard(wizard)
        loaded = self.ctx.wizard()
        self.assertEqual(loaded.stage, AWAIT_ACTION)
        self.assertEqual(loaded.trigger, "^w")
        self.assertTrue(loaded.want_remap)

    def test_notices_are_strings(self):
        self.ctx.state.set_notices(["а", 5, None])
        self.assertEqual(self.ctx.state.notices(), ["а", "5", "None"])

    def test_applied_hash_roundtrip(self):
        self.assertEqual(self.ctx.state.applied_hash(), "")
        self.ctx.state.update(applied_hash="abc")
        self.assertEqual(self.ctx.state.applied_hash(), "abc")

    def test_corrupt_state_recovers(self):
        with open(self.state_path, "w", encoding="utf-8") as handle:
            handle.write("мусор")
        state = self.ctx.state.load()
        self.assertEqual(state["notices"], [])
        self.assertEqual(state["wizard"], {})


if __name__ == "__main__":
    import unittest  # noqa: F401

    unittest.main()
