# -*- coding: utf-8 -*-
"""Граница RPC: формы argv, отказоустойчивость и замкнутость сценариев.

Отдельные тесты закрепляют три подтверждённых дефекта прежней реализации,
чтобы они не вернулись: контекстное меню получало список, но сравнивало его со
строкой; неизвестный метод ронял процесс; экран выбора действия работал и без
записанного триггера.
"""

import contextlib
import io
import json
import unittest

import core.ahk.capture as capture
from core.model import build
from core.rpc import Application, Reply, Request, extract_rule_id, normalize_query
from core.session import AWAIT_ACTION, IDLE
from tests.support import TempCase, find_by_method, titles


class TestRequestParsing(unittest.TestCase):
    def test_typical_query(self):
        req = Request.from_argv([json.dumps({"method": "query", "parameters": ["new "]})])
        self.assertEqual(req.method, "query")
        self.assertEqual(req.params, ["new "])

    def test_no_argv_defaults_to_query(self):
        self.assertEqual(Request.from_argv([]).method, "query")
        self.assertEqual(Request.from_argv([]).params, [""])

    def test_garbage_argv_treated_as_query_text(self):
        req = Request.from_argv(["просто текст"])
        self.assertEqual(req.method, "query")
        self.assertEqual(req.params, ["просто текст"])

    def test_missing_parameters(self):
        self.assertEqual(Request.from_argv(['{"method":"clear_all"}']).params, [])

    def test_scalar_parameters_are_wrapped(self):
        self.assertEqual(Request.from_argv(['{"method":"x","parameters":5}']).params, [5])

    def test_v2_style_params_key(self):
        req = Request.from_argv(['{"method":"query","params":["w"]}'])
        self.assertEqual(req.params, ["w"])


class TestNormalizers(unittest.TestCase):
    def test_query_string(self):
        self.assertEqual(normalize_query("w -> esc"), "w -> esc")

    def test_query_dict_uses_search(self):
        self.assertEqual(normalize_query({"search": "abc", "rawQuery": "key abc"}), "abc")

    def test_query_dict_without_search(self):
        self.assertEqual(normalize_query({"nothing": 1}), "")

    def test_query_none(self):
        self.assertEqual(normalize_query(None), "")

    def test_query_wrapped_in_list(self):
        self.assertEqual(normalize_query(["w"]), "w")

    def test_rule_id_from_list(self):
        self.assertEqual(extract_rule_id(["abc123"]), "abc123")

    def test_rule_id_from_string(self):
        self.assertEqual(extract_rule_id("abc123"), "abc123")

    def test_rule_id_from_empty_list(self):
        self.assertEqual(extract_rule_id([]), "")

    def test_rule_id_from_junk(self):
        self.assertEqual(extract_rule_id(None), "")
        self.assertEqual(extract_rule_id({"id": "x"}), "")


class TestApplicationWiring(TempCase):
    def setUp(self):
        super().setUp()
        self.app = Application(self.ctx)

    # --- Регрессия бага №2: контекстное меню -------------------------

    def test_dashboard_rule_card_carries_context_data(self):
        from core.model import RuleSet

        self.ctx.rules.save(RuleSet([build(self.catalog, trigger="w", action="esc")]))
        reply = self.app.respond(Request("query", [""]))
        card = find_by_method(reply.results, "toggle_rule")[0]
        self.assertEqual(card["ContextData"], [card["JsonRPCAction"]["parameters"][0]])

    def test_context_menu_accepts_list_payload(self):
        """Главная регрессия: хост передаёт СПИСОК, а не строку."""
        from core.model import RuleSet

        rule = build(self.catalog, trigger="w", action="esc")
        self.ctx.rules.save(RuleSet([rule]))
        reply = self.app.respond(Request("context_menu", [[rule.id]]))
        self.assertEqual(len(reply.results), 3)
        self.assertIn("Удалить правило", " ".join(titles(reply.results)))
        self.assertIn("Прозрачность", " ".join(titles(reply.results)))

    def test_context_menu_accepts_bare_string_too(self):
        from core.model import RuleSet

        rule = build(self.catalog, trigger="w", action="esc")
        self.ctx.rules.save(RuleSet([rule]))
        reply = self.app.respond(Request("context_menu", [rule.id]))
        self.assertEqual(len(reply.results), 3)

    def test_context_menu_for_unknown_rule_is_empty(self):
        reply = self.app.respond(Request("context_menu", [["нет-такого"]]))
        self.assertEqual(reply.results, [])

    # --- Регрессия бага №3: неизвестный метод ------------------------

    def test_unknown_method_does_not_crash_query(self):
        """Упавший процесс для Flow Launcher неотличим от пустого ответа."""
        reply = self.app.respond(Request("query", [""]))
        self.assertTrue(reply.results)
        for item in reply.results:
            self.assertIn("Title", item)

    def test_filtered_dashboard_can_be_empty_without_error(self):
        reply = self.app.respond(Request("query", ["нет такого правила"]))
        self.assertEqual(reply.results, [])

    def test_unknown_action_method_is_ignored(self):
        reply = self.app.respond(Request("такой_метод", [1, 2]))
        self.assertEqual(reply.results, None)
        self.assertEqual(reply.goto, "")
        self.assertEqual(reply.lines(), [])

    def test_handler_exception_becomes_visible_card(self):
        def boom(*args):
            raise RuntimeError("намеренная ошибка")

        self.app.handlers["query"] = boom
        reply = self.app.respond(Request("query", [""]))
        self.assertIn("Сбой плагина", " ".join(titles(reply.results)))
        self.assertIn("Сбой плагина", " ".join(self.ctx.state.notices()))

    # --- Регрессия бага №6: экран без состояния ----------------------

    def test_action_step_without_trigger_refuses_cleanly(self):
        reply = self.app.respond(Request("query", ["target: esc"]))
        labels = " ".join(titles(reply.results))
        self.assertIn("Триггер ещё не записан", labels)
        self.assertEqual(len(self.ctx.ruleset()), 0)
        self.assertEqual(self.runtime.applied, [])

    def test_listen_target_without_trigger_refuses(self):
        reply = self.app.respond(Request("listen_target", []))
        self.assertIn("триггер", reply.goto)
        self.assertEqual(len(self.ctx.ruleset()), 0)

    # --- Инвариант: каждая карточка ведёт в существующий метод ------

    def test_every_referenced_method_exists(self):
        from core.model import RuleSet

        self.ctx.rules.save(RuleSet([build(self.catalog, trigger="w", action="esc")]))
        screens = ["", "?", "new", "new alt + ", "new w -> esc", "target: ",
                   "target: esc", "app: ", "app: chrome", "ошибка: таймаут", "chrome"]
        referenced = set()
        for screen in screens:
            for item in self.app.respond(Request("query", [screen])).results:
                method = (item.get("JsonRPCAction") or {}).get("method")
                if method:
                    referenced.add(method)
        self.assertGreaterEqual(len(referenced), 10)
        missing = sorted(m for m in referenced if m not in self.app.handlers)
        self.assertEqual(missing, [], "карточки ссылаются на несуществующие методы")

    def test_context_menu_methods_exist(self):
        from core.model import RuleSet

        rule = build(self.catalog, trigger="w", action="esc")
        self.ctx.rules.save(RuleSet([rule]))
        for item in self.app.respond(Request("context_menu", [[rule.id]])).results:
            self.assertIn(item["JsonRPCAction"]["method"], self.app.handlers)

    # --- Сценарии ----------------------------------------------------

    def test_dsl_creation_applies_hooks(self):
        reply = self.app.respond(Request("apply_dsl", ["alt + w -> esc"]))
        rules = self.ctx.ruleset()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules.rules[0].trigger, "!w")
        self.assertEqual(rules.rules[0].action, "Escape")
        self.assertIn("*!w::Send('{Escape}')", self.runtime.applied[-1])
        self.assertEqual(reply.goto, "key ")

    def test_duplicate_is_refused_with_human_text(self):
        self.app.respond(Request("apply_dsl", ["w -> esc"]))
        reply = self.app.respond(Request("apply_dsl", ["w -> tab"]))
        self.assertTrue(reply.goto.startswith("key ошибка:"))
        self.assertEqual(len(self.ctx.ruleset()), 1)
        notices = " ".join(self.ctx.state.notices())
        self.assertIn("уже занят", notices)

    def test_invalid_dsl_does_not_change_state(self):
        self.app.respond(Request("apply_dsl", ["вот так не умеет"]))
        self.assertEqual(len(self.ctx.ruleset()), 0)

    def test_toggle_and_delete_through_rpc(self):
        from core.model import RuleSet

        rule = build(self.catalog, trigger="w", action="esc")
        self.ctx.rules.save(RuleSet([rule]))

        self.app.respond(Request("toggle_rule", [rule.id]))
        self.assertFalse(self.ctx.ruleset().rules[0].enabled)
        self.assertNotIn("*w::", self.runtime.applied[-1])

        self.app.respond(Request("delete_rule", [rule.id]))
        self.assertEqual(len(self.ctx.ruleset()), 0)

    def test_scope_step_roundtrip(self):
        self.captured(trigger="w", human="W")
        self.app.respond(Request("set_scope", ["Code"]))
        wizard = self.ctx.wizard()
        self.assertEqual(wizard.scope, "Code.exe")
        self.assertEqual(wizard.stage, AWAIT_ACTION)
        self.app.respond(Request("commit_action", ["esc"]))
        self.assertEqual(self.ctx.ruleset().rules[0].scope, "Code.exe")

    def test_remap_flow_uses_native_remap(self):
        self.captured(trigger="w", human="W", want_remap=True)
        self.app.respond(Request("commit_action", ["esc"]))
        self.assertEqual(self.ctx.ruleset().rules[0].mode, "remap")
        self.assertIn("*w::Escape", self.runtime.applied[-1])

    def test_transparent_toggle_through_rpc(self):
        from core.model import RuleSet

        rule = build(self.catalog, trigger="XButton1", action="^AppsKey")
        self.ctx.rules.save(RuleSet([rule]))

        self.app.respond(Request("toggle_transparent", [rule.id]))
        self.assertTrue(self.ctx.ruleset().rules[0].transparent)
        self.assertIn("~*XButton1::Send('^{AppsKey}')", self.runtime.applied[-1])
        self.assertEqual(self.ctx.wizard().stage, IDLE)

        cards = self.app.respond(Request("query", [""])).results
        marked = [c for c in cards if "🔓" in c["Title"]]
        self.assertEqual(len(marked), 1, titles(cards))

        self.app.respond(Request("toggle_transparent", [rule.id]))
        self.assertFalse(self.ctx.ruleset().rules[0].transparent)
        self.assertNotIn("~*", self.runtime.applied[-1])

    def test_transparent_refused_for_remap_rule(self):
        from core.model import MODE_REMAP, RuleSet

        rule = build(self.catalog, trigger="CapsLock", action="Escape", mode=MODE_REMAP)
        self.ctx.rules.save(RuleSet([rule]))
        reply = self.app.respond(Request("toggle_transparent", [rule.id]))
        self.assertTrue(reply.goto.startswith("key ошибка:"))
        self.assertFalse(self.ctx.ruleset().rules[0].transparent)
        # в меню для ремап-правила пункта о прозрачности нет
        menu = self.app.respond(Request("context_menu", [[rule.id]])).results
        self.assertEqual(len(menu), 2, titles(menu))

    def test_clear_all_and_pause(self):
        from core.model import RuleSet

        self.ctx.rules.save(RuleSet([build(self.catalog, trigger="w", action="esc")]))
        self.app.respond(Request("toggle_pause", []))
        self.assertTrue(self.ctx.state.is_paused())
        self.assertIn("Suspend(True)", self.runtime.applied[-1])
        self.app.respond(Request("toggle_pause", []))
        self.assertFalse(self.ctx.state.is_paused())
        self.app.respond(Request("clear_all", []))
        self.assertEqual(len(self.ctx.ruleset()), 0)

    def test_change_query_handler_emits_navigation(self):
        reply = self.app.respond(Request("change_query", ["key new ", True]))
        self.assertEqual(reply.goto, "key new ")
        self.assertIn("Flow.Launcher.ChangeQuery", reply.lines()[0])


class TestCaptureFlow(TempCase):
    """Захват подменён: проверяем реакцию плагина, а не AutoHotkey."""

    def setUp(self):
        super().setUp()
        self.app = Application(self.ctx)
        self._real = capture.run
        capture.run = lambda *a, **kw: self.canned

    def tearDown(self):
        capture.run = self._real
        super().tearDown()

    def test_trigger_then_action(self):
        self.canned = capture.Capture(capture.KEY, trigger="^w", human="Ctrl + w")
        reply = self.app.respond(Request("listen_trigger", []))
        self.assertEqual(reply.goto, "key target: ")
        wizard = self.ctx.wizard()
        self.assertEqual(wizard.trigger, "^w")
        self.assertEqual(wizard.stage, AWAIT_ACTION)

        self.canned = capture.Capture(capture.KEY, trigger="Escape", human="Escape")
        self.app.respond(Request("listen_target", []))
        rule = self.ctx.ruleset().rules[0]
        self.assertEqual((rule.trigger, rule.action), ("^w", "Escape"))
        self.assertEqual(self.ctx.wizard().stage, IDLE)

    def test_cancel_does_not_create_anything(self):
        self.canned = capture.Capture(capture.CANCELLED)
        reply = self.app.respond(Request("listen_trigger", []))
        self.assertEqual(len(self.ctx.ruleset()), 0)
        self.assertEqual(self.ctx.wizard().stage, IDLE)
        self.assertEqual(self.runtime.applied, [])
        self.assertIn("отменена", " ".join(self.ctx.state.notices()))

    def test_timeout_offers_retry(self):
        self.canned = capture.Capture(capture.TIMEOUT, message="Timeout")
        reply = self.app.respond(Request("listen_trigger", []))
        self.assertTrue(reply.goto.startswith("key ошибка:"))

    def test_remap_variant_sets_wizard_flag(self):
        self.canned = capture.Capture(capture.KEY, trigger="w", human="W")
        self.app.respond(Request("listen_trigger_remap", []))
        self.assertTrue(self.ctx.wizard().want_remap)

    def test_action_cancel_keeps_trigger(self):
        self.captured(trigger="w", human="W")
        self.canned = capture.Capture(capture.CANCELLED)
        reply = self.app.respond(Request("listen_target", []))
        self.assertTrue(self.ctx.wizard().has_trigger)
        self.assertEqual(len(self.ctx.ruleset()), 0)


class TestReply(unittest.TestCase):
    def test_only_goto(self):
        self.assertEqual(Reply(goto="key ").lines(),
                         ['{"method": "Flow.Launcher.ChangeQuery", '
                          '"parameters": ["key ", true]}'])

    def test_only_results(self):
        lines = Reply(results=[{"Title": "x"}]).lines()
        self.assertEqual(len(lines), 1)
        self.assertIn('"result"', lines[0])

    def test_nothing(self):
        self.assertEqual(Reply().lines(), [])


class TestRunNeverCrashesTheHost(TempCase):
    """Ответ хосту всегда валиден, а выход всегда нулевой.

    Flow Launcher считает ненулевой код возврата плагина ошибкой: `JsonRPCPlugin`
    заворачивает трейсбек в `FlowPluginException`, а та всплывает в потоке
    интерфейса и роняет всё приложение. Логи пользователя это подтверждают —
    поэтому здесь проверяется не только «не бросил исключение», но и то, что в
    stdout ушёл ровно один разбираемый JSON.
    """

    def run_app(self, app, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = app.run(argv)
        return code, buffer.getvalue()

    def test_unknown_method_is_silent_and_successful(self):
        code, out = self.run_app(Application(self.ctx), ['{"method":"нет-такого"}'])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_broken_respond_still_yields_one_valid_json(self):
        app = Application(self.ctx)

        def boom(request):
            raise RuntimeError("внутренняя поломка")

        app.respond = boom
        code, out = self.run_app(app, ['{"method":"query","parameters":[""]}'])
        self.assertEqual(code, 0)
        payload = json.loads(out)          # частичный вывод хост не разберёт
        self.assertIn("Сбой", payload["result"][0]["Title"])

    def test_handler_exception_becomes_a_card(self):
        app = Application(self.ctx)
        app.handlers = {"query": lambda *args: 1 / 0}
        code, out = self.run_app(app, ['{"method":"query","parameters":[""]}'])
        self.assertEqual(code, 0)
        self.assertIn("ZeroDivisionError", json.loads(out)["result"][0]["SubTitle"])

    def test_output_is_pure_ascii(self):
        """Хост читает stdout в своей кодировке: не-ASCII ломает вывод."""
        code, out = self.run_app(Application(self.ctx),
                                 ['{"method":"query","parameters":[""]}'])
        self.assertEqual(code, 0)
        out.encode("ascii")


if __name__ == "__main__":
    unittest.main()
