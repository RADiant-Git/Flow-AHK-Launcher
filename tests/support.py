# -*- coding: utf-8 -*-
"""Общая обвязка тестов: изолированные хранилища и подставной AutoHotkey.

Тесты не должны зависеть ни от установленного AutoHotkey, ни от реальных файлов
плагина: все пути во временные каталоги, а вместо настоящего рантайма — запись
вызовов.
"""

import os
import shutil
import sys
import tempfile
import unittest

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

from core.ahk import codegen  # noqa: E402
from core.ahk.runtime import ApplyResult  # noqa: E402
from core.catalog import KeyCatalog  # noqa: E402
from core.services import Context  # noqa: E402
from core.storage import RuleStore, StateStore  # noqa: E402


class FakeRuntime(object):
    """Заменяет управление процессом: проверяем текст и факт применения."""

    def __init__(self):
        self.applied = []
        self.script_path = os.path.join(tempfile.gettempdir(), "flowkey-test-runtime.ahk")
        self.executable = self.script_path  # несуществующий файл
        self.available = True

    def validate(self, text):
        return ""

    def apply(self, text):
        self.applied.append(text)
        return ApplyResult(ok=True, digest=codegen.script_hash(text), launched=True)


class TempCase(unittest.TestCase):
    """Базовый кейс с изолированными modules.json / session.json."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="flowkey-tests-")
        self.catalog = KeyCatalog()
        self.rules_path = os.path.join(self.tmp, "modules.json")
        self.state_path = os.path.join(self.tmp, "session.json")
        self.runtime = FakeRuntime()
        self.ctx = Context(
            catalog=self.catalog,
            rules=RuleStore(self.rules_path, self.catalog),
            state=StateStore(self.state_path),
            runtime=self.runtime,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- Хелперы ------------------------------------------------------

    def write_rules_v1(self, entries):
        """Положить файл старого формата (плоский список v1)."""
        import json

        with open(self.rules_path, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, ensure_ascii=False)

    def captured(self, trigger="w", human="w", scope="*", want_remap=False):
        """Провести мастера через стадию «триггер записан» без реального захвата."""
        from core.session import Wizard

        wizard = Wizard().begin_capture(want_remap).captured(trigger, human)
        if scope != "*":
            wizard = wizard.scoped(scope)
        self.ctx.state.set_wizard(wizard)
        return wizard

    def assertContains(self, haystack, needle, message=""):
        self.assertIn(needle, haystack, message or "%r not found in %r" % (needle, haystack))


def titles(results):
    return [item.get("Title", "") for item in results]


def find_by_method(results, method):
    return [r for r in results
            if (r.get("JsonRPCAction") or {}).get("method") == method]
