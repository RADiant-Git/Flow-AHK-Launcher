# -*- coding: utf-8 -*-
"""Презентация состояния в карточки результатов Flow Launcher.

Здесь нет бизнес-логики и нет записи: только «что показать» и «куда вести
Enter». Все строки собраны в одном месте, чтобы подпись и действие не могли
разъехаться — раньше подпись обещала «Alt+D: удалить», которого не существовало.
"""

from typing import Any, Dict, List, Optional

from core import config
from core.catalog import REMAP, SEND, TRIGGER
from core.model import GLOBAL_SCOPE, MODE_REMAP, Rule
from core.services import Context

KEYWORD = config.ACTION_KEYWORD

# Максимумы списков: Flow Launcher всё равно режет, но лишние строки — мусор.
CATALOG_LIMIT = 8
ACTION_LIMIT = 7
TARGET_LIMIT = 6


def card(title: str, subtitle: str = "", method: str = "", params: Optional[list] = None,
         keep_open: bool = True, context_data: Optional[list] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "Title": title,
        "SubTitle": subtitle,
        "IcoPath": config.ICON_PATH,
    }
    if method:
        action = {"method": method, "parameters": params or []}
        if keep_open:
            action["dontHideAfterAction"] = True
        result["JsonRPCAction"] = action
    if context_data is not None:
        result["ContextData"] = context_data
    return result


def _url(*parts: str) -> str:
    return " ".join([KEYWORD] + [p for p in parts if p]).strip() + " "


def problem_cards(text: str) -> List[Dict[str, Any]]:
    return [card(
        "⚠️ Ошибка записи",
        "%s — нажмите Enter, чтобы попробовать снова" % text,
        method="listen_trigger",
    )]


def _notices(ctx: Context) -> List[Dict[str, Any]]:
    notes = ctx.state.notices()
    if not notes:
        return []
    return [card(
        "⚠️ Не применено: %d" % len(notes),
        " | ".join(notes)[:300] + "   (Enter — скрыть)",
        method="dismiss_notices",
    )]


def _drift_card(ctx: Context) -> List[Dict[str, Any]]:
    from core import services

    if not services.is_drifted(ctx):
        return []
    return [card(
        "🔄 Хуки отстают от правил",
        "Скрипт пересобран, но не применён. Enter — применить",
        method="action_reload",
    )]


# --------------------------------------------------------------------------- #
# Главный экран
# --------------------------------------------------------------------------- #

def dashboard(ctx: Context, text: str) -> List[Dict[str, Any]]:
    wizard = ctx.wizard()
    results: List[Dict[str, Any]] = []
    if not text:
        results += _notices(ctx) + _drift_card(ctx)

        if wizard.has_trigger:
            results.append(card(
                "⏳ Незаконченная запись: [%s]" % wizard.human,
                "Действие не выбрано. Enter — продолжить, Esc-меню — отменить",
                method="continue_wizard",
            ))

    actions = [
        card("🎯 Записать переназначение",
             "Физически нажмите клавишу или кнопку мыши", method="listen_trigger"),
        card("🔒 Записать в режиме удержания",
             "Клавиша поведёт себя как целевая, включая автоповтор",
             method="listen_trigger_remap"),
        card("➕ Собрать правило из каталога или формулы",
             "Например: alt + shift + !c -> esc", method="start_new"),
    ]
    if text:
        needle = text.lower()
        actions = [a for a in actions
                   if needle in ("%s %s" % (a["Title"], a["SubTitle"])).lower()]
    results += actions

    needle = text.lower()
    for rule in ctx.ruleset():
        if needle and needle not in _haystack(rule):
            continue
        results.append(_rule_card(ctx, rule))

    if not text:
        results.append(card("❓ Справка и управление хуками",
                            "Пауза, перезапуск, автозапуск, очистка",
                            method="change_query", params=[_url("?")]))
    return results


def _haystack(rule: Rule) -> str:
    return " ".join([rule.name, rule.trigger, rule.action, rule.scope]).lower()


def _rule_card(ctx: Context, rule: Rule) -> Dict[str, Any]:
    paused = ctx.state.is_paused()
    enabled = rule.enabled and not paused
    if paused:
        status = "⏸️"
    else:
        status = "🟢" if rule.enabled else "⚪"
    mode = " ⇄" if rule.mode == MODE_REMAP else ""
    ghost = " 🔓" if rule.transparent else ""
    scope = "везде" if rule.scope == GLOBAL_SCOPE else rule.scope
    return card(
        "%s %s%s%s" % (status, rule.name, mode, ghost),
        "Окно: %s%s | Enter — %s | Ctrl+O (ПКМ) — меню" % (
            scope, " | нажатие проходит в окно" if rule.transparent else "",
            "выключить" if rule.enabled else "включить"),
        method="toggle_rule", params=[rule.id],
        context_data=[rule.id],
    )


# --------------------------------------------------------------------------- #
# Справка
# --------------------------------------------------------------------------- #

def help_screen(ctx: Context, text: str) -> List[Dict[str, Any]]:
    from core.ahk import runtime as rt

    paused = ctx.state.is_paused()
    autostart = rt.autostart_enabled(ctx.runtime)
    items = [
        card("▶️ Возобновить перехваты" if paused else "⏸️ Приостановить все перехваты",
             "Временно отключить или включить все хуки AHK",
             method="toggle_pause"),
        card("🔄 Перезапустить рантайм AHK",
             "Пересобрать и применить скрипт хуков", method="action_reload"),
        card("🚀 Автозапуск хуков при входе в Windows: %s" % ("ВКЛ" if autostart else "ВЫКЛ"),
             "Enter — переключить. Без этого бинды не работают после перезагрузки",
             method="toggle_autostart"),
        card("➕ Новое правило", "Открыть конструктор", method="start_new"),
        card("🎯 Записать клавишу", "Перехватить физическое нажатие",
             method="listen_trigger"),
        card("📂 Открыть папку плагина", "Файлы, скрипты, modules.json",
             method="open_plugin_folder", keep_open=False),
        card("🧹 Очистить все правила", "Удалить все переназначения",
             method="clear_all"),
    ]
    if not text:
        return items
    needle = text.lower()
    return [i for i in items if needle in "%s %s" % (i["Title"], i["SubTitle"]).lower()]


# --------------------------------------------------------------------------- #
# Конструктор: триггер
# --------------------------------------------------------------------------- #

def new_builder(ctx: Context, text: str) -> List[Dict[str, Any]]:
    catalog = ctx.catalog
    results: List[Dict[str, Any]] = []

    if "->" in text:
        source, target = text.split("->", 1)
        source = source.strip()
        target = " ".join(target.split())

        results.append(card("🔴 Записать действие нажатием для [%s]" % source,
                            "Enter, затем нажмите целевую клавишу",
                            method="listen_target_for_dsl", params=[source]))

        if target:
            probe = _try_dsl(ctx, text)
            if probe is not None:
                rule, note = probe
                results.append(card("✅ Применить: %s" % rule.name,
                                   note or "Окно: %s" % rule.scope,
                                   method="apply_dsl", params=[text]))

        for key in catalog.search(target, role=SEND)[:TARGET_LIMIT]:
            formula = "%s -> %s" % (source, key.ahk_name)
            results.append(card("Назначить: %s [%s]" % (key.display_name, key.ahk_name),
                                "Формула: %s" % formula,
                                method="change_query", params=[_url("new", formula)]))
        return results

    results.append(card("🔴 Записать триггер нажатием",
                        "Enter, затем клавиша, сочетание или кнопка мыши",
                        method="listen_trigger"))
    if text:
        results.append(card("👉 Перейти к выбору действия: [%s] ->" % text,
                            "Enter — назначить действие",
                            method="change_query", params=[_url("new", text, "->")]))

    base = text.rstrip()
    if base.endswith("+"):
        prefix, token = base + " ", ""
    elif "+" in base:
        head, token = base.rsplit("+", 1)
        head, token = head.rstrip(), token.strip()
        resolved = catalog.resolve(token)
        prefix = "%s + %s + " % (head, token) if resolved else "%s + " % head
    else:
        prefix, token = "", base

    for key in catalog.search(token, role=TRIGGER)[:CATALOG_LIMIT]:
        results.append(card("Выбрать: %s (%s)" % (key.display_name, key.ahk_name),
                            "Категория: %s | Enter — добавить в формулу" % key.category,
                            method="change_query",
                            params=[_url("new", "%s%s ->" % (prefix, key.ahk_name))]))
    return results


def _try_dsl(ctx: Context, formula: str):
    from core import dsl
    from core.model import FlowKeyError

    try:
        draft = dsl.parse(formula, ctx.catalog)
        rule, notes = draft.finalize(ctx.catalog)
    except (dsl.DslError, FlowKeyError):
        return None
    taken = ctx.ruleset().owner_of(rule)
    if taken is not None:
        return rule, "Занято правилом «%s» — сначала измените его" % taken.name
    return rule, " | ".join(notes) if notes else ""


# --------------------------------------------------------------------------- #
# Шаг действия (после записи триггера)
# --------------------------------------------------------------------------- #

def action_step(ctx: Context, text: str) -> List[Dict[str, Any]]:
    wizard = ctx.wizard()
    if not wizard.has_trigger:
        return [
            card("⚠️ Триггер ещё не записан",
                 "Нужно сначала нажать клавишу-источник. Enter — записать",
                 method="listen_trigger"),
            card("➕ Или соберите формулу вручную",
                 "Например: w -> esc", method="start_new"),
        ]

    label = wizard.human or wizard.trigger
    mode = " (удержание)" if wizard.want_remap else ""
    scope = "везде" if wizard.scope == GLOBAL_SCOPE else wizard.scope
    results = [
        card("🔴 Нажать целевую клавишу для [%s]" % label,
             "Enter, затем физическое нажатие", method="listen_target"),
        card("🌍 Окно: %s" % scope,
             "Ограничить правило одним приложением",
             method="change_query", params=[_url("app:")]),
    ]

    if text:
        results.append(card("✅ Создать: [%s]%s ➔ %s" % (label, mode, text),
                            "Enter — сохранить и применить",
                            method="commit_action", params=[text]))

    role = REMAP if wizard.want_remap else SEND
    for key in ctx.catalog.search(text, role=role)[:ACTION_LIMIT]:
        results.append(card("%s [%s]" % (key.display_name, key.ahk_name),
                            "Категория: %s | Enter — выбрать" % key.category,
                            method="commit_action", params=[key.ahk_name]))
    return results


# --------------------------------------------------------------------------- #
# Шаг выбора окна
# --------------------------------------------------------------------------- #

SCOPES = [
    (GLOBAL_SCOPE, "🌍 Глобально (везде)"),
    ("Code.exe", "VS Code"),
    ("chrome.exe", "Google Chrome"),
    ("firefox.exe", "Mozilla Firefox"),
    ("explorer.exe", "Проводник"),
    ("WindowsTerminal.exe", "Windows Terminal"),
]


def scope_step(ctx: Context, text: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if text:
        results.append(card("✅ Окно: %s" % text,
                            "Enter — продолжить выбор действия",
                            method="set_scope", params=[text]))
    for exe, label in SCOPES:
        results.append(card(label, "Процесс: %s" % exe,
                            method="set_scope", params=[exe]))
    return results


# --------------------------------------------------------------------------- #
# Контекстное меню правила
# --------------------------------------------------------------------------- #

def rule_context_menu(ctx: Context, rule_id: str) -> List[Dict[str, Any]]:
    rule = ctx.ruleset().find(rule_id)
    if rule is None:
        return []
    items = [
        card("▶️ Включить правило" if not rule.enabled else "⏸️ Выключить правило",
             rule.name, method="toggle_rule", params=[rule.id]),
    ]
    if rule.mode != MODE_REMAP:
        items.append(card(
            "🔓 Прозрачность: ВКЛ — выключить" if rule.transparent
            else "🔓 Прозрачность: ВЫКЛ — включить",
            "Включено: исходное нажатие уходит и в активное окно — сработает "
            "и переназначение, и штатная функция клавиши",
            method="toggle_transparent", params=[rule.id]))
    items.append(card("🗑️ Удалить правило", rule.name,
                      method="delete_rule", params=[rule.id]))
    return items
