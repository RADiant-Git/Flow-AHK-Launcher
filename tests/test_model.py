# -*- coding: utf-8 -*-
"""Домен: валидация, конфликты, миграция формата."""

import unittest

from core.model import (DuplicateTrigger, GLOBAL_SCOPE, InvalidAction,
                        InvalidScope, InvalidTrigger, MODE_REMAP, MODE_SEND,
                        RuleSet, RuleNotFound, build, humanize_trigger)
from core.session import Wizard
from tests.support import TempCase
from core.model import RuleDraft


class TestCanonicalAction(TempCase):
    def test_alias_replaced(self):
        from core.model import canonical_action

        self.assertEqual(canonical_action("esc", self.catalog), "Escape")

    def test_alias_after_modifier_replaced(self):
        from core.model import canonical_action

        self.assertEqual(canonical_action("^apps", self.catalog), "^AppsKey")
        self.assertEqual(canonical_action("!prtsc", self.catalog), "!PrintScreen")

    def test_rule_keeps_canonical_form(self):
        rule = build(self.catalog, trigger="XButton1", action="^apps")
        self.assertEqual(rule.action, "^AppsKey")

    def test_send_sequence_is_not_rewritten(self):
        from core.model import canonical_action

        self.assertEqual(canonical_action("^ew", self.catalog), "^ew")
        self.assertEqual(canonical_action("hello", self.catalog), "hello")

    def test_split_modifiers(self):
        from core.model import split_modifiers

        self.assertEqual(split_modifiers("^!AppsKey"), ("^!", "AppsKey"))
        self.assertEqual(split_modifiers("AppsKey"), ("", "AppsKey"))
        self.assertEqual(split_modifiers("{LCtrl down}e"), ("", "{LCtrl down}e"))


class TestValidation(TempCase):
    def test_valid_rule(self):
        rule = build(self.catalog, trigger="^!e", action="esc")
        self.assertEqual(rule.trigger, "^!e")
        self.assertEqual(rule.action, "Escape")
        self.assertEqual(rule.scope, GLOBAL_SCOPE)
        self.assertEqual(rule.mode, MODE_SEND)

    def test_trigger_key_from_hole_is_rejected(self):
        """Раньше «Key» проходил в генератор и умирал уже в AutoHotkey."""
        with self.assertRaises(InvalidTrigger):
            build(self.catalog, trigger="Key", action="esc")

    def test_empty_trigger(self):
        with self.assertRaises(InvalidTrigger):
            build(self.catalog, trigger="", action="esc")

    def test_tilde_and_dollar_prefixes_rejected(self):
        for bad in ["~w", "$w", "*w"]:
            with self.assertRaises(InvalidTrigger, msg=bad):
                build(self.catalog, trigger=bad, action="esc")

    def test_unknown_base_key(self):
        with self.assertRaises(InvalidTrigger):
            build(self.catalog, trigger="notakey", action="esc")

    def test_vksc_allowed(self):
        rule = build(self.catalog, trigger="vk41sc01e", action="esc")
        self.assertEqual(rule.trigger, "vk41sc01e")

    def test_empty_action(self):
        with self.assertRaises(InvalidAction):
            build(self.catalog, trigger="w", action="   ")

    def test_scope_normalized_to_exe(self):
        self.assertEqual(build(self.catalog, trigger="w", action="esc",
                               scope="Code").scope, "Code.exe")
        self.assertEqual(build(self.catalog, trigger="w", action="esc",
                               scope="chrome.exe").scope, "chrome.exe")

    def test_scope_rejects_injection(self):
        for bad in ['a") or WinActive("b', "a b\tc", ""]:
            if bad == "":
                self.assertEqual(build(self.catalog, trigger="w", action="esc",
                                       scope=bad).scope, GLOBAL_SCOPE)
                continue
            with self.assertRaises(InvalidScope, msg=bad):
                build(self.catalog, trigger="w", action="esc", scope=bad)

    def test_remap_requires_single_key(self):
        with self.assertRaises(InvalidAction):
            build(self.catalog, trigger="w", action="^ew", mode=MODE_REMAP)

    def test_modifier_is_not_a_send_target_but_is_remap_target(self):
        from core.catalog import SEND

        info = self.catalog.resolve("ctrl")
        self.assertFalse(self.catalog.supports(info, SEND))
        with self.assertRaises(InvalidAction):
            build(self.catalog, trigger="w", action="ctrl", mode=MODE_SEND)
        self.assertEqual(build(self.catalog, trigger="w", action="LCtrl",
                               mode=MODE_REMAP).mode, MODE_REMAP)

    def test_transparent_allowed_for_send(self):
        rule = build(self.catalog, trigger="w", action="esc", transparent=True)
        self.assertTrue(rule.transparent)

    def test_transparent_refused_for_remap(self):
        """Ремап сам превращает клавишу — «пропускать» ему нечего."""
        with self.assertRaises(InvalidAction):
            build(self.catalog, trigger="w", action="esc", mode=MODE_REMAP,
                  transparent=True)


class TestDraftTransparency(TempCase):
    def test_draft_downgrades_transparent_with_remap_note(self):
        draft = RuleDraft(trigger="w", action="esc", want_remap=True, transparent=True)
        rule, notes = draft.finalize(self.catalog)
        self.assertEqual(rule.mode, MODE_REMAP)
        self.assertFalse(rule.transparent)
        self.assertTrue(any("Прозрачность" in n for n in notes), notes)

    def test_draft_keeps_transparent_for_send(self):
        draft = RuleDraft(trigger="w", action="esc", transparent=True)
        rule, notes = draft.finalize(self.catalog)
        self.assertTrue(rule.transparent)
        self.assertEqual(notes, [])


class TestHumanize(unittest.TestCase):
    def setUp(self):
        from core.catalog import KeyCatalog

        self.catalog = KeyCatalog()

    def test_modifiers(self):
        self.assertEqual(humanize_trigger("^!+e", self.catalog),
                         "Ctrl + Alt + Shift + E")

    def test_named_key(self):
        self.assertEqual(humanize_trigger("CapsLock", self.catalog), "Caps Lock")


class TestRuleSet(TempCase):
    def make(self, trigger, action="esc", scope=GLOBAL_SCOPE, **kw):
        return build(self.catalog, trigger=trigger, action=action, scope=scope, **kw)

    def test_add_and_conflict(self):
        rules = RuleSet().add(self.make("w"))
        with self.assertRaises(DuplicateTrigger):
            rules.add(self.make("w", action="tab"))

    def test_conflict_is_per_scope(self):
        rules = RuleSet([self.make("w")]).add(self.make("w", scope="Code.exe"))
        self.assertEqual(len(rules), 2)

    def test_case_insensitive_conflict(self):
        rules = RuleSet([self.make("CapsLock")])
        with self.assertRaises(DuplicateTrigger):
            rules.add(self.make("capslock"))

    def test_toggle_and_remove(self):
        rule = self.make("w")
        toggled = RuleSet([rule]).toggled(rule.id)
        self.assertFalse(toggled.rules[0].enabled)
        self.assertEqual(len(RuleSet([rule]).remove(rule.id)), 0)
        with self.assertRaises(RuleNotFound):
            RuleSet().remove("нет-такого")

    def test_without_conflicts_keeps_first(self):
        first = self.make("w")
        second = build(self.catalog, trigger="w", action="tab", name="Второе")
        safe, notes = RuleSet([first, second]).without_conflicts()
        self.assertEqual(len(safe), 1)
        self.assertEqual(len(notes), 1)


class TestMigration(TempCase):
    def test_v1_fields_are_migrated(self):
        self.write_rules_v1([{
            "id": "abc",
            "name": "W -> Esc",
            "trigger_human": "Ctrl + w",
            "trigger_ahk": "^w",
            "target": "Escape",
            "app": "Code.exe",
            "enabled": True,
            "hold": True,
        }])
        rules = self.ctx.rules.load(self.catalog)
        self.assertEqual(len(rules), 1)
        rule = rules.rules[0]
        self.assertEqual(rule.trigger, "^w")
        self.assertEqual(rule.action, "Escape")
        self.assertEqual(rule.scope, "Code.exe")
        self.assertEqual(rule.mode, MODE_REMAP)
        self.assertEqual(rule.name, "W -> Esc")

    def test_v1_disabled_and_junk(self):
        self.write_rules_v1([
            {"id": "ok", "trigger_ahk": "w", "target": "esc", "app": "*", "enabled": False},
            {"id": "broken", "trigger_ahk": "Key", "target": "esc"},
        ])
        rules = self.ctx.rules.load(self.catalog)
        self.assertEqual([r.id for r in rules], ["ok"])
        self.assertFalse(rules.rules[0].enabled)

    def test_roundtrip_v2(self):
        rule = build(self.catalog, trigger="^w", action="esc")
        self.ctx.rules.save(RuleSet([rule]))
        loaded = self.ctx.rules.load(self.catalog)
        self.assertEqual(loaded.rules[0].id, rule.id)
        self.assertEqual(loaded.rules[0].trigger, "^w")

    def test_transparent_survives_storage(self):
        rule = build(self.catalog, trigger="^w", action="esc", transparent=True)
        self.ctx.rules.save(RuleSet([rule]))
        loaded = self.ctx.rules.load(self.catalog)
        self.assertTrue(loaded.rules[0].transparent)

    def test_v1_has_no_transparent_field(self):
        self.write_rules_v1([{"id": "a", "trigger_ahk": "w", "target": "esc",
                              "app": "*", "enabled": True}])
        self.assertFalse(self.ctx.rules.load(self.catalog).rules[0].transparent)

    def test_broken_entry_does_not_lose_others(self):
        self.ctx.rules.save(RuleSet([
            build(self.catalog, trigger="w", action="esc"),
            build(self.catalog, trigger="q", action="tab"),
        ]))
        import json

        with open(self.rules_path, encoding="utf-8") as handle:
            raw = json.load(handle)
        raw["rules"].append({"id": "x"})            # заведомо битая запись
        with open(self.rules_path, "w", encoding="utf-8") as handle:
            json.dump(raw, handle)
        self.assertEqual(len(self.ctx.rules.load(self.catalog)), 2)


class TestDraft(TempCase):
    def test_draft_downgrades_remap_with_note(self):
        draft = RuleDraft(trigger="w", action="^ew", want_remap=True)
        rule, notes = draft.finalize(self.catalog)
        self.assertEqual(rule.mode, MODE_SEND)
        self.assertTrue(notes)

    def test_draft_remap_ok(self):
        draft = RuleDraft(trigger="w", action="esc", want_remap=True, human="W")
        rule, notes = draft.finalize(self.catalog)
        self.assertEqual(rule.mode, MODE_REMAP)
        self.assertEqual(notes, [])
        self.assertIn("W", rule.name)


class TestWizardMachine(TempCase):
    def test_stage_without_trigger_falls_back_to_idle(self):
        from core.session import AWAIT_ACTION, IDLE

        wizard = Wizard(stage=AWAIT_ACTION, trigger="", human="")
        self.assertEqual(Wizard.from_json(wizard.to_json()).stage, IDLE)

    def test_transitions(self):
        from core.session import AWAIT_ACTION, IDLE

        wizard = Wizard().begin_capture(True).captured("^w", "Ctrl + w")
        self.assertEqual(wizard.stage, AWAIT_ACTION)
        self.assertTrue(wizard.want_remap)
        wizard = wizard.choosing_scope().scoped("Code.exe")
        self.assertEqual(wizard.stage, AWAIT_ACTION)
        self.assertEqual(wizard.scope, "Code.exe")
        self.assertEqual(wizard.reset().stage, IDLE)

    def test_roundtrip(self):
        wizard = Wizard().captured("w", "W").scoped("chrome.exe")
        self.assertEqual(Wizard.from_json(wizard.to_json()), wizard)


if __name__ == "__main__":
    unittest.main()
