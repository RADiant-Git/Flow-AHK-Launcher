# -*- coding: utf-8 -*-
"""Экраны: что именно видит пользователь.

Проверки появились после жалобы «не даёт переназначить мышь на LWin»: правило
собиралось, но модификатора не было в списке действий, а подпись правила не
говорила, в каком режиме оно работает.
"""

import unittest

from core import views
from core.model import MODE_REMAP, RuleDraft, RuleSet
from tests.support import TempCase, titles


class TestActionCandidates(TempCase):
    def setUp(self):
        super().setUp()
        self.captured("XButton1", "Mouse 4 (Back)")

    def offered(self, text):
        return titles(views.action_step(self.ctx, text))

    def test_modifier_is_found_by_query(self):
        self.assertTrue(any("LWin" in title for title in self.offered("win")),
                        self.offered("win"))

    def test_modifier_is_found_by_exact_name(self):
        self.assertTrue(any("LWin" in title for title in self.offered("lwin")))

    def test_ordinary_key_is_still_offered(self):
        self.assertTrue(any("Escape" in title for title in self.offered("esc")))

    def test_empty_query_is_not_flooded_by_modifiers(self):
        """В каталоге модификаторы идут первыми — без фильтра они заняли бы
        весь список из семи строк."""
        found = self.offered("")
        self.assertFalse(any("LCtrl" in t or "LWin" in t or "LShift" in t
                             for t in found), found)
        self.assertTrue(found)

    def test_hold_mode_lists_modifiers_without_a_query(self):
        self.captured("XButton1", "Mouse 4 (Back)", want_remap=True)
        self.assertTrue(any("LWin" in t for t in self.offered("")))

    def test_empty_query_does_not_offer_mouse_buttons_as_remap(self):
        """Мышь ремапить нельзя, поэтому в режиме удержания её быть не должно."""
        self.captured("XButton1", "Mouse 4 (Back)", want_remap=True)
        self.assertFalse(any("XButton1" in t for t in self.offered("")))


class TestRuleCard(TempCase):
    def make(self, trigger, action, **kw):
        rule, _ = RuleDraft(trigger=trigger, action=action, **kw).finalize(self.catalog)
        self.ctx.rules.save(RuleSet([rule]))
        return rule

    def card_for(self, needle):
        found = [c for c in views.dashboard(self.ctx, "") if needle in c["Title"]]
        self.assertEqual(len(found), 1, [c["Title"] for c in found])
        return found[0]

    def test_remap_mode_is_spelled_out(self):
        self.make("XButton1", "LWin", human="Mouse 4 (Back)")
        card = self.card_for("Mouse 4")
        self.assertIn("⇄", card["Title"])
        self.assertIn("удержание", card["SubTitle"])

    def test_send_mode_is_spelled_out(self):
        self.make("w", "esc")
        card = self.card_for("Escape")
        self.assertIn("одно нажатие", card["SubTitle"])
        self.assertNotIn("⇄", card["Title"])

    def test_transparency_is_still_reported(self):
        self.make("w", "esc", transparent=True)
        card = self.card_for("Escape")
        self.assertIn("🔓", card["Title"])
        self.assertIn("нажатие проходит в окно", card["SubTitle"])


class TestDashboard(TempCase):
    def test_empty_dashboard_offers_three_ways_to_create(self):
        found = titles(views.dashboard(self.ctx, ""))
        for needle in ("🎯", "🔒", "➕"):
            self.assertTrue(any(needle in t for t in found), found)

    def test_incomplete_wizard_is_visible(self):
        self.captured("XButton1", "Mouse 4 (Back)")
        found = titles(views.dashboard(self.ctx, ""))
        self.assertTrue(any("Незаконченная запись" in t for t in found), found)

    def test_action_step_without_trigger_explains_itself(self):
        """Вместо пустого экрана — что именно не так и как это исправить."""
        found = titles(views.action_step(self.ctx, ""))
        self.assertTrue(any("Триггер ещё не записан" in t for t in found), found)


if __name__ == "__main__":
    unittest.main()
