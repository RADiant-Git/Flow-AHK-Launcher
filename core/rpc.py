# -*- coding: utf-8 -*-
"""Граница JSON-RPC Flow Launcher.

Единственный модуль, который знает о форме argv. Три вещи, каждая из которых
раньше была отдельным классом багов:

1. Неизвестный метод не роняет процесс. Базовый `flowlauncher` делает
   `dict(methods)[name]` и бросает KeyError; для Flow Launcher упавший процесс
   неотличим от «ничего не найдено», и пользователь просто видит пустой список.
2. `context_menu` получает СПИСОК (параметры JsonRPCAction выбранной строки либо
   ContextData), а не строку. Сравнение с id как со строкой давляло меню целиком.
3. `query` может прийти словарём от новых хостов; брать нужно только `search`.

Обработчики описаны явной таблицей, поэтому опечатка в имени метода видна в
тестах, а не в рантайме.
"""

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core import config
from core.session import (INTENT_ACTION, INTENT_HELP, INTENT_NEW, INTENT_PROBLEM,
                          INTENT_SCOPE, Wizard, classify)
from core.services import Context


@dataclass
class Reply:
    """Чем ответить хосту: списком результатов и/или переходом к запросу."""

    results: Optional[List[Dict[str, Any]]] = None
    goto: str = ""

    def lines(self) -> List[str]:
        out = []
        if self.results is not None:
            out.append(json.dumps({"result": self.results}, ensure_ascii=True))
        if self.goto:
            out.append(json.dumps({
                "method": "Flow.Launcher.ChangeQuery",
                "parameters": [self.goto, True],
            }, ensure_ascii=True))
        return out


def normalize_query(param: Any) -> str:
    if isinstance(param, dict):
        for key in ("search", "query", "Query"):
            if key in param:
                return str(param[key] or "")
        return ""
    if isinstance(param, (list, tuple)):
        return normalize_query(param[0]) if param else ""
    if param is None:
        return ""
    return str(param)


def extract_rule_id(data: Any) -> str:
    """id правила из payload контекстного меню: список или одиночная строка."""
    if isinstance(data, (list, tuple)):
        return str(data[0]) if data else ""
    if isinstance(data, str):
        return data
    return ""


@dataclass
class Request:
    method: str = "query"
    params: List[Any] = field(default_factory=list)

    @classmethod
    def from_argv(cls, argv: Optional[List[str]] = None) -> "Request":
        argv = sys.argv[1:] if argv is None else argv
        if not argv:
            return cls("query", [""])
        try:
            payload = json.loads(argv[0])
        except (ValueError, TypeError):
            return cls("query", [str(argv[0])])
        if not isinstance(payload, dict):
            return cls("query", [payload])
        params = payload.get("parameters")
        if params is None:
            params = payload.get("params", [])
        if not isinstance(params, (list, tuple)):
            params = [params]
        return cls(str(payload.get("method") or "query"), list(params))


class Application:
    """Таблица методов + гарантия «никогда не упасть молча»."""

    def __init__(self, context: Optional[Context] = None):
        self.ctx = context or Context()
        self.handlers: Dict[str, Callable[..., Reply]] = self._build_handlers()

    # --- Разбор и рассылка -------------------------------------------

    def run(self, argv: Optional[List[str]] = None) -> int:
        request = Request.from_argv(argv)
        for line in self.respond(request).lines():
            print(line)
        return 0

    def respond(self, request: Request) -> Reply:
        handler = self.handlers.get(request.method)
        if handler is None:
            if request.method in ("query", "context_menu"):
                return Reply(results=[])
            return Reply()
        try:
            return handler(*request.params)
        except Exception as exc:  # последний рубеж: показываем, а не молчим
            return self._failure(request, exc)

    def _failure(self, request: Request, exc: Exception) -> Reply:
        message = "%s: %s" % (type(exc).__name__, exc)
        try:
            self.ctx.state.set_notices(["Сбой плагина: %s" % message])
        except Exception:
            pass
        if request.method in ("query", "context_menu"):
            return Reply(results=[_error_card(message)])
        return Reply(goto=_dash())

    # --- Навигация ----------------------------------------------------

    # --- query --------------------------------------------------------

    def query(self, param: Any = "") -> Reply:
        from core import views

        intent, rest = classify(normalize_query(param))
        if intent == INTENT_HELP:
            results = views.help_screen(self.ctx, rest)
        elif intent == INTENT_NEW:
            results = views.new_builder(self.ctx, rest)
        elif intent == INTENT_ACTION:
            results = views.action_step(self.ctx, rest)
        elif intent == INTENT_SCOPE:
            results = views.scope_step(self.ctx, rest)
        elif intent == INTENT_PROBLEM:
            results = views.problem_cards(rest)
        else:
            results = views.dashboard(self.ctx, rest)
        return Reply(results=results)

    def context_menu(self, data: Any = None) -> Reply:
        from core import views

        return Reply(results=views.rule_context_menu(self.ctx, extract_rule_id(data)))

    def change_query(self, query: str = "", requery: bool = True) -> Reply:
        return Reply(goto=str(query or ""))

    # --- Запись -------------------------------------------------------

    def listen_trigger(self, want_remap: bool = False) -> Reply:
        from core import services

        wizard = Wizard().begin_capture(want_remap)
        result, wizard = services.capture_trigger(self.ctx, wizard)
        return self._after_trigger_capture(result, wizard)

    def listen_trigger_remap(self) -> Reply:
        return self.listen_trigger(True)

    def _after_trigger_capture(self, result, wizard: Wizard) -> Reply:
        if result.ok:
            return Reply(goto=_step("target:"))
        if result.cancelled:
            self.ctx.state.set_notices(["Запись отменена (Escape)"])
            return Reply(goto=_dash())
        return Reply(goto=_problem(result.message or "нажатие не записано"))

    def continue_wizard(self) -> Reply:
        wizard = self.ctx.wizard()
        if not wizard.has_trigger:
            return Reply(goto=_step("new"))
        return Reply(goto=_step("target:"))

    def listen_target(self) -> Reply:
        from core import services

        wizard = self.ctx.wizard()
        if not wizard.has_trigger:
            self.ctx.state.set_wizard(Wizard().reset())
            return Reply(goto=_problem("триггер ещё не записан"))

        captured = services.capture_key(self.ctx)
        if captured.cancelled:
            self.ctx.state.set_notices(["Запись отменена (Escape), триггер сохранён"])
            return Reply(goto=_step("target:"))
        if not captured.ok:
            return Reply(goto=_problem(captured.message or "действие не записано"))

        return self._commit(services.draft_from_wizard(self.ctx, captured))

    def listen_target_for_dsl(self, source: str = "") -> Reply:
        from core import dsl, services
        from core.model import FlowKeyError

        captured = services.capture_key(self.ctx)
        if captured.cancelled:
            return Reply(goto=_step("new"))
        if not captured.ok:
            return Reply(goto=_problem(captured.message or "действие не записано"))

        formula = "%s -> %s" % (str(source).strip(), captured.trigger)
        try:
            draft = dsl.parse(formula, self.ctx.catalog)
        except (dsl.DslError, FlowKeyError) as exc:
            self.ctx.state.set_notices([str(exc)])
            return Reply(goto=_problem(str(exc)))
        return self._commit(draft)

    def commit_action(self, action: str = "") -> Reply:
        wizard = self.ctx.wizard()
        if not wizard.has_trigger:
            return Reply(goto=_problem("триггер не записан"))
        from core.model import RuleDraft

        return self._commit(RuleDraft(
            trigger=wizard.trigger,
            action=action,
            scope=wizard.scope,
            want_remap=wizard.want_remap,
            human=wizard.human,
        ))

    def apply_dsl(self, formula: str = "") -> Reply:
        from core import services

        outcome = services.create_from_dsl(self.ctx, formula)
        self.ctx.state.set_wizard(Wizard().reset())
        if not outcome.ok:
            return Reply(goto=_problem(outcome.error))
        return Reply(goto=_dash(), results=None)

    def start_new(self) -> Reply:
        return Reply(goto=_step("new"))

    def set_scope(self, scope: str = "") -> Reply:
        from core.model import InvalidScope, validate_scope

        try:
            resolved = validate_scope(scope)
        except InvalidScope as exc:
            self.ctx.state.set_notices([str(exc)])
            return Reply(goto=_problem(str(exc)))
        wizard = self.ctx.wizard().scoped(resolved)
        self.ctx.state.set_wizard(wizard)
        return Reply(goto=_step("target:"))

    # --- Управление ---------------------------------------------------

    def toggle_rule(self, rule_id: Any = "") -> Reply:
        from core import services

        services.toggle_rule(self.ctx, str(rule_id))
        return Reply(goto=_dash())

    def toggle_transparent(self, rule_id: Any = "") -> Reply:
        from core import services

        outcome = services.toggle_transparent(self.ctx, str(rule_id))
        if not outcome.ok:
            return Reply(goto=_problem(outcome.error))
        return Reply(goto=_dash())

    def delete_rule(self, rule_id: Any = "") -> Reply:
        from core import services

        services.delete_rule(self.ctx, str(rule_id))
        return Reply(goto=_dash())

    def clear_all(self) -> Reply:
        from core import services

        services.clear_all(self.ctx)
        return Reply(goto=_dash())

    def toggle_pause(self) -> Reply:
        from core import services

        services.set_paused(self.ctx, not self.ctx.state.is_paused())
        return Reply(goto=_dash())

    def action_reload(self) -> Reply:
        from core import services

        services.apply_hooks(self.ctx)
        return Reply(goto=_dash())

    def dismiss_notices(self) -> Reply:
        self.ctx.state.set_notices([])
        return Reply(goto=_dash())

    def toggle_autostart(self) -> Reply:
        from core.ahk import runtime as rt

        target = not rt.autostart_enabled(self.ctx.runtime)
        error = rt.set_autostart(self.ctx.runtime, target)
        if error:
            self.ctx.state.set_notices([error])
        return Reply(goto=_step("?"))

    def open_plugin_folder(self) -> Reply:
        import os

        os.startfile(config.BASE_DIR)
        return Reply()

    # --- Внутреннее ---------------------------------------------------

    def _commit(self, draft) -> Reply:
        from core import services

        outcome = services.commit_draft(self.ctx, draft)
        if not outcome.ok:
            return Reply(goto=_problem(outcome.error))
        return Reply(goto=_dash())

    def _build_handlers(self) -> Dict[str, Callable[..., Reply]]:
        names = [
            "query", "context_menu", "change_query",
            "listen_trigger", "listen_trigger_remap", "continue_wizard",
            "listen_target", "listen_target_for_dsl", "commit_action",
            "apply_dsl", "start_new", "set_scope",
            "toggle_rule", "delete_rule", "clear_all", "toggle_pause",
            "toggle_transparent",
            "action_reload", "dismiss_notices", "toggle_autostart",
            "open_plugin_folder",
        ]
        return {name: getattr(self, name) for name in names}


# --------------------------------------------------------------------------- #
# Построители строк перехода
# --------------------------------------------------------------------------- #

def _dash() -> str:
    return "%s " % config.ACTION_KEYWORD


def _step(name: str) -> str:
    return "%s %s " % (config.ACTION_KEYWORD, name)


def _problem(text: str) -> str:
    return "%s ошибка: %s" % (config.ACTION_KEYWORD, text)


def _error_card(message: str) -> Dict[str, Any]:
    from core import views

    return views.card("⚠️ Сбой плагина", message[:300], method="dismiss_notices")


def main(argv: Optional[List[str]] = None) -> int:
    return Application().run(argv)
