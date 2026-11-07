# -*- coding: utf-8 -*-
"""DSL формул: `[@процесс] триггер [ + ... ] -> действие` → RuleDraft.

Чистая функция без доступа к диску и процессам. От прежней реализации
отличается тем, что не знает про поля записи и про AutoHotkey-генерацию:
она отдаёт черновик, а правила из него собирает доменный слой.
"""

import re
from typing import List, Tuple

from core.catalog import KeyCatalog
from core.model import GLOBAL_SCOPE, RuleDraft

_ACTION_SPLIT = re.compile(r"->")
_MODIFIER_NAMES = {
    "ctrl": ("^", "Ctrl"),
    "lctrl": ("^", "Ctrl"),
    "rctrl": ("^", "Ctrl"),
    "alt": ("!", "Alt"),
    "lalt": ("!", "Alt"),
    "ralt": ("!", "Alt"),
    "shift": ("+", "Shift"),
    "lshift": ("+", "Shift"),
    "rshift": ("+", "Shift"),
    "win": ("#", "Win"),
    "lwin": ("#", "Win"),
    "rwin": ("#", "Win"),
    "meta": ("#", "Win"),
    "cmd": ("#", "Win"),
}


class DslError(ValueError):
    """Формула неразборима. Текст читает пользователь."""


def _normalize(text: str) -> str:
    return " ".join(str(text).split())


def _modifier_of(token: str, catalog: KeyCatalog):
    """Модификатор → (символ AHK, человекочитаемое имя) либо None."""
    info = catalog.resolve(token)
    name = (info.ahk_name if info else token).lower()
    for key, value in _MODIFIER_NAMES.items():
        if key in name:
            return value
    return None


def _trigger_token(token: str, catalog: KeyCatalog) -> Tuple[str, str, bool]:
    """Один токен → (ахк-имя, подпись, это удержание)."""
    raw = _normalize(token)
    want_remap = raw.startswith("!")
    body = raw[1:].strip() if want_remap else raw
    if not body:
        raise DslError("Пустой токен перед '->'")
    info = catalog.resolve(body)
    ahk = info.ahk_name if info else body
    human = info.display_name if info else body
    return ahk, human, want_remap


def parse(formula: str, catalog: KeyCatalog) -> RuleDraft:
    text = _normalize(formula)
    if not text:
        raise DslError("Формула пуста. Пример: w -> esc")

    scope = GLOBAL_SCOPE
    if text.startswith("@"):
        head, _, rest = text.partition(" ")
        scope = head[1:].strip()
        if not scope:
            raise DslError("После @ нужно имя процесса, например @Code.exe")
        text = _normalize(rest)

    if "->" not in text:
        raise DslError("Ожидается оператор '->'. Пример: w -> esc")

    source_part, target_part = _ACTION_SPLIT.split(text, 1)
    target = _normalize(target_part)
    if not target:
        raise DslError("Действие не может быть пустым")

    tokens = [t.strip() for t in source_part.split("+") if t.strip()]
    if not tokens:
        raise DslError("Триггер не может быть пустым")

    *modifier_tokens, main_token = tokens
    ahk_main, human_main, want_remap = _trigger_token(main_token, catalog)

    prefix = ""
    humans: List[str] = []
    for token in modifier_tokens:
        found = _modifier_of(token, catalog)
        if found is None:
            raise DslError("Неизвестный модификатор: «%s»" % token)
        symbol, label = found
        prefix += symbol
        humans.append(label)

    trigger = prefix + ahk_main
    human = " + ".join(humans + [human_main])
    return RuleDraft(
        trigger=trigger,
        action=target,
        scope=scope,
        want_remap=want_remap,
        human=human,
    )
