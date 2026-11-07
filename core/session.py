# -*- coding: utf-8 -*-
"""Машина состояний мастера и разбор намерений из строки поиска.

Ключевая идея (см. ARCHITECTURE.md, раздел 7): текст в строке поиска — это
НАМЕРЕНИЕ пользователя, а не состояние. Состояние мастера живёт в сторе. Экран
проверяет, что состояние соответствует намерению, и если нет — не выводит
битый экран, а объясняет, чего не хватает.

Раньше это давало дыру: `key target: esc` без записанного триггера приводило к
правилу с триггером «Key» и сырой ошибке AutoHotkey.
"""

from dataclasses import dataclass, replace
from typing import Optional, Tuple

# Стадии мастера
IDLE = "idle"
AWAIT_ACTION = "await_action"
AWAIT_SCOPE = "await_scope"

STAGES = (IDLE, AWAIT_ACTION, AWAIT_SCOPE)

# Намерения, которые распознаёт строка поиска
INTENT_IDLE = "idle"
INTENT_HELP = "help"
INTENT_NEW = "new"
INTENT_ACTION = "action"
INTENT_SCOPE = "scope"
INTENT_PROBLEM = "problem"


@dataclass(frozen=True)
class Wizard:
    """Состояние одного создаваемого правила."""

    stage: str = IDLE
    trigger: str = ""
    human: str = ""
    scope: str = "*"
    want_remap: bool = False

    @property
    def has_trigger(self) -> bool:
        return bool(self.trigger)

    def begin_capture(self, want_remap: bool = False) -> "Wizard":
        return replace(self, stage=IDLE, want_remap=bool(want_remap))

    def captured(self, trigger: str, human: str) -> "Wizard":
        return replace(self, stage=AWAIT_ACTION, trigger=trigger, human=human)

    def choosing_scope(self) -> "Wizard":
        return replace(self, stage=AWAIT_SCOPE)

    def scoped(self, scope: str) -> "Wizard":
        return replace(self, stage=AWAIT_ACTION, scope=scope)

    def reset(self) -> "Wizard":
        return Wizard()

    def to_json(self) -> dict:
        return {
            "stage": self.stage,
            "trigger": self.trigger,
            "human": self.human,
            "scope": self.scope,
            "want_remap": self.want_remap,
        }

    @classmethod
    def from_json(cls, raw: Optional[dict]) -> "Wizard":
        raw = raw or {}
        stage = raw.get("stage", IDLE)
        if stage not in STAGES:
            stage = IDLE
        # Стадии AWAIT_* без триггера невозможны: набор данных важнее стадии.
        trigger = str(raw.get("trigger") or "")
        if stage != IDLE and not trigger:
            stage = IDLE
        return cls(
            stage=stage,
            trigger=trigger,
            human=str(raw.get("human") or ""),
            scope=str(raw.get("scope") or "*"),
            want_remap=bool(raw.get("want_remap")),
        )


def classify(query: str, action_keyword: str = "key") -> Tuple[str, str]:
    """Строка поиска (без ключевого слова) → (намерение, остаток)."""
    text = str(query or "").strip()

    if not text:
        return INTENT_IDLE, ""
    if text.startswith("?"):
        return INTENT_HELP, text[1:].strip()
    if text == "new" or text.startswith("new "):
        return INTENT_NEW, text[3:].strip()
    if text.startswith(("target:", "действие:")):
        return INTENT_ACTION, _strip_prefix(text, ("target:", "действие:"))
    if text.startswith(("app:", "окно:")):
        return INTENT_SCOPE, _strip_prefix(text, ("app:", "окно:"))
    if text.startswith(("error:", "timeout:", "ошибка:")):
        return INTENT_PROBLEM, text
    return INTENT_IDLE, text


def _strip_prefix(text: str, prefixes: Tuple[str, ...]) -> str:
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text
