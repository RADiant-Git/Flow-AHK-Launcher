# -*- coding: utf-8 -*-
"""Разбор намерений из строки поиска."""

import unittest

from core.session import (INTENT_ACTION, INTENT_HELP,
                          INTENT_IDLE, INTENT_NEW, INTENT_PROBLEM, INTENT_SCOPE,
                          classify)


class TestClassify(unittest.TestCase):
    def check(self, text, intent, rest=None):
        got, payload = classify(text)
        self.assertEqual(got, intent, text)
        if rest is not None:
            self.assertEqual(payload, rest, text)

    def test_empty_is_dashboard(self):
        self.check("", INTENT_IDLE, "")

    def test_plain_filter_is_dashboard(self):
        self.check("chrome", INTENT_IDLE, "chrome")

    def test_help(self):
        self.check("?", INTENT_HELP, "")
        self.check("? пауза", INTENT_HELP, "пауза")

    def test_new_exact_and_prefixed(self):
        self.check("new", INTENT_NEW, "")
        self.check("new alt + ", INTENT_NEW, "alt +")

    def test_new_does_not_swallow_words(self):
        # «news» — это фильтр по правилу, а не вход в конструктор
        self.check("news", INTENT_IDLE, "news")

    def test_action_step(self):
        self.check("target: esc", INTENT_ACTION, "esc")
        self.check("target:", INTENT_ACTION, "")
        self.check("действие: esc", INTENT_ACTION, "esc")

    def test_scope_step(self):
        self.check("app: chrome", INTENT_SCOPE, "chrome")
        self.check("окно: chrome", INTENT_SCOPE, "chrome")

    def test_problem(self):
        self.check("timeout: нет нажатия", INTENT_PROBLEM, "timeout: нет нажатия")
        self.check("ошибка: х", INTENT_PROBLEM, "ошибка: х")


if __name__ == "__main__":
    unittest.main()
