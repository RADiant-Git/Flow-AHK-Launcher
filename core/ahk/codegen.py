# -*- coding: utf-8 -*-
"""Генерация текста runtime.ahk из набора правил.

Чистая функция: никаких файлов, процессов и AutoHotkey. Благодаря этому её
можно тестировать на любой машине, а решение «что корректно» остаётся в модели.
"""

import hashlib
from typing import List, Tuple

from core.catalog import KeyCatalog
from core.model import (GLOBAL_SCOPE, MODE_REMAP, Rule, RuleSet,
                        split_modifiers)

SCRIPT_VERSION = 3

_HEADER = (
    "#Requires AutoHotkey v2.0",
    "#SingleInstance Force",
    "#UseHook True",
)


def ahk_string(value: str) -> str:
    """Строковый литерал AutoHotkey v2 в одинарных кавычках.

    Экранирование — обратным апострофом: `` ` `` для апострофа и ``` `` ``` для
    самого апострофа. Переводы строк сворачиваются в пробел, иначе они
    разорвали бы строку скрипта.
    """
    text = str(value).replace("\r", "").replace("\n", " ")
    return "'" + text.replace("`", "``").replace("'", "`'") + "'"


def send_expression(action: str, catalog: KeyCatalog) -> str:
    """Аргумент для Send().

    Имена клавиш обязаны быть в фигурных скобках: `Send('Escape')` печатает
    слово «Escape», а `Send('{Escape}')` нажимает клавишу.

    Отдельный и более коварный случай — «модификатор + имя»: `Send('^AppsKey')`
    применяет `^` к первому символу строки, то есть к `A`, а остаток `ppsKey`
    печатает текстом. Поэтому скобки нужны и в `^AppsKey` → `^{AppsKey}`.
    Готовые Send-последовательности (`^ew`, `{LCtrl down}e`) передаются как есть.
    """
    token = " ".join(str(action).split())
    mods, rest = split_modifiers(token)
    if catalog.is_key_name(rest):
        return mods + "{" + rest + "}"
    return token


def hotkey_line(rule: Rule, catalog: KeyCatalog) -> str:
    # `*` — срабатывать и при зажатых модификаторах; `~` — не съедать нажатие,
    # а пропускать его и в активное окно тоже.
    prefix = "~*" if rule.transparent else "*"
    if rule.mode == MODE_REMAP:
        return "%s%s::%s" % (prefix, rule.trigger, rule.action)
    return "%s%s::Send(%s)" % (prefix, rule.trigger,
                               ahk_string(send_expression(rule.action, catalog)))


def render(ruleset: RuleSet, catalog: KeyCatalog, paused: bool = False
          ) -> Tuple[str, List[str]]:
    """RuleSet → (текст скрипта, заметки). Заметки — только про невозможное."""
    notes: List[str] = []
    active: List[Rule] = []
    for rule in ruleset.active:
        if not rule.trigger or not rule.action:
            notes.append("«%s» пропущено: не хватает триггера или действия" % rule.name)
            continue
        active.append(rule)

    lines = list(_HEADER)
    if active:
        # Без хоткеев хуки не нужны: скрипт завершится сразу и не оставит
        # резидентный процесс с глобальным клавиатурным хуком.
        lines += ["InstallKeybdHook()", "InstallMouseHook()"]
    lines.append("")

    if paused:
        lines += ["Suspend(True)", ""]

    grouped: List[Tuple[str, List[Rule]]] = []
    index = {}
    for rule in active:
        scope = rule.scope or GLOBAL_SCOPE
        if scope not in index:
            index[scope] = []
            grouped.append((scope, index[scope]))
        index[scope].append(rule)

    for scope, rules in grouped:
        if scope != GLOBAL_SCOPE:
            lines.append("#HotIf WinActive(%s)" % ahk_string("ahk_exe " + scope))
        else:
            lines.append("#HotIf")
        for rule in rules:
            lines.append(hotkey_line(rule, catalog))
        lines.append("")

    return "\n".join(lines), notes


def script_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
