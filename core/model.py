# -*- coding: utf-8 -*-
"""Доменная модель: правило, черновик, набор правил, конфликты.

Здесь живут все правила «что вообще может быть правилом». Генератор AHK и
экраны не принимают решений о корректности — они получают уже валидные данные.
Именно перенос проверки из кодогенерации в модель превращает «молча не
работающее правило» в явный отказ в момент создания.
"""

import re
import uuid
from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Optional, Tuple

from core.catalog import REMAP, SEND, KeyCatalog

MODE_SEND = "send"
MODE_REMAP = "remap"
MODES = (MODE_SEND, MODE_REMAP)

GLOBAL_SCOPE = "*"

# Триггер: необязательные модификаторы AHK + базовое имя клавиши.
# Префиксы *, ~ и $ не допускаем — звёздочку добавляет генератор, а ~ и $
# меняют смысл правила вопреки воле пользователя.
_TRIGGER_RE = re.compile(r"\A([!^+#]{0,4})([A-Za-z0-9_]+)\Z")
_VKSC_RE = re.compile(r"\Avk[0-9A-Fa-f]{2}(?:sc[0-9A-Fa-f]{3})?\Z")
_MODIFIER_ORDER = "^{+#"
_MODS_SPLIT_RE = re.compile(r"\A([!^+#]*)(.+)\Z", re.S)


def split_modifiers(token: str) -> Tuple[str, str]:
    """Разделить `^!AppsKey` на (`^!`, `AppsKey`).

    И триггер, и действие могут прийти в форме «префикс модификаторов + имя
    клавиши», и обоим нужно уметь выделять имя: первому — ради валидации,
    второму — ради фигурных скобок в Send.
    """
    match = _MODS_SPLIT_RE.match(token)
    if not match:
        return "", token
    return match.group(1), match.group(2)


class FlowKeyError(Exception):
    """Базовая доменная ошибка. Текст — для пользователя, не для лога."""


class InvalidTrigger(FlowKeyError):
    pass


class InvalidAction(FlowKeyError):
    pass


class InvalidScope(FlowKeyError):
    pass


class DuplicateTrigger(FlowKeyError):
    def __init__(self, rule, taken_by: str):
        super().__init__(
            "Триггер %s уже занят правилом «%s»" % (rule.trigger, taken_by)
        )
        self.rule = rule
        self.taken_by = taken_by


class RuleNotFound(FlowKeyError):
    pass


def validate_trigger(trigger: str, catalog: KeyCatalog) -> str:
    """Проверить AHK-спецификатор триггера, вернуть канонический вид."""
    token = " ".join(str(trigger).split())
    if not token:
        raise InvalidTrigger("Триггер не задан — сначала запишите клавишу")
    match = _TRIGGER_RE.match(token)
    if not match:
        raise InvalidTrigger(
            "Некорректный триггер «%s»: допускаются модификаторы ! ^ + # и имя клавиши" % token
        )
    modifiers, base = match.group(1), match.group(2)
    if _VKSC_RE.match(base):
        return modifiers + base
    if not catalog.is_key_name(base) and catalog.resolve(base) is None:
        raise InvalidTrigger("AutoHotkey не знает клавишу «%s»" % base)
    return modifiers + base


def validate_action(action: str) -> str:
    token = " ".join(str(action).split())
    if not token:
        raise InvalidAction("Действие не может быть пустым")
    return token


def canonical_action(action: str, catalog: KeyCatalog) -> str:
    """Свернуть алиас к каноническому имени клавиши.

    `esc` → `Escape`, `^apps` → `^AppsKey`, а `^ew` остаётся как есть: у
    Send-последовательностей имени клавиши нет. Без этого шага генератор не
    узнал бы, что значение нужно обернуть в фигурные скобки.
    """
    token = validate_action(action)
    mods, rest = split_modifiers(token)
    if mods:
        info = catalog.resolve(rest)
        if info:
            return mods + info.ahk_name
    info = catalog.resolve(token)
    return info.ahk_name if info else token


def validate_scope(scope: str) -> str:
    token = str(scope or GLOBAL_SCOPE).strip()
    if not token or token == GLOBAL_SCOPE:
        return GLOBAL_SCOPE
    if not re.match(r"\A[A-Za-z0-9_.\- ]{1,64}\Z", token):
        raise InvalidScope("Некорректное имя процесса: «%s»" % token)
    return token if token.lower().endswith(".exe") else token + ".exe"


def humanize_trigger(trigger: str, catalog: KeyCatalog) -> str:
    """`^!e` → `Ctrl + Alt + e` для подписей в интерфейсе."""
    match = _TRIGGER_RE.match(trigger)
    if not match:
        return trigger
    modifiers, base = match.group(1), match.group(2)
    info = catalog.resolve(base)
    label = info.display_name if info else base
    names = {"^": "Ctrl", "!": "Alt", "+": "Shift", "#": "Win"}
    return " + ".join([names[c] for c in modifiers if c in names] + [label])


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    trigger: str          # AHK-спецификатор без "*": ^!e, w, MButton
    action: str           # имя клавиши либо готовая Send-последовательность
    scope: str            # "*" или имя процесса
    mode: str             # send | remap
    enabled: bool = True
    transparent: bool = False   # ~ : исходное нажатие уходит и в активное окно

    @property
    def conflict_key(self) -> Tuple[str, str]:
        return (self.scope.lower(), self.trigger.lower())

    def to_json(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "trigger": self.trigger,
            "action": self.action,
            "scope": self.scope,
            "mode": self.mode,
            "enabled": self.enabled,
            "transparent": self.transparent,
        }

    @classmethod
    def from_json(cls, raw: Dict[str, object], catalog: KeyCatalog) -> "Rule":
        """Собрать правило из JSON, допуская запись формата v1."""
        trigger = str(raw.get("trigger") or raw.get("trigger_ahk") or "")
        action = str(raw.get("action") or raw.get("target") or "")
        scope = raw.get("scope")
        if scope is None:
            scope = raw.get("app")
        mode = str(raw.get("mode") or (MODE_REMAP if raw.get("hold") else MODE_SEND))
        if mode not in MODES:
            mode = MODE_SEND
        return build(
            catalog,
            trigger=trigger,
            action=action,
            scope=str(scope or GLOBAL_SCOPE),
            mode=mode,
            enabled=bool(raw.get("enabled", True)),
            transparent=bool(raw.get("transparent", False)),
            rule_id=str(raw.get("id") or new_id()),
            name=str(raw.get("name") or ""),
            human=str(raw.get("trigger_human") or ""),
        )


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def build(catalog: KeyCatalog, *, trigger: str, action: str,
          scope: str = GLOBAL_SCOPE, mode: str = MODE_SEND,
          enabled: bool = True, transparent: bool = False,
          rule_id: Optional[str] = None,
          name: str = "", human: str = "") -> Rule:
    """Создать валидное правило. Единственный легальный способ его получить."""
    trigger = validate_trigger(trigger, catalog)
    action = canonical_action(action, catalog)
    scope = validate_scope(scope)

    info = catalog.resolve(action)
    if mode == MODE_REMAP:
        if not (info and catalog.supports(info, REMAP)):
            raise InvalidAction(
                "В режиме ремапа доступно только имя клавиши, а не «%s»" % action
            )
        if transparent:
            raise InvalidAction(
                "Прозрачность не совмещается с удержанием: ремап сам превращает "
                "исходную клавишу в целевую, пропускать ему нечего"
            )
    elif mode == MODE_SEND:
        if info and not catalog.supports(info, SEND):
            raise InvalidAction(
                "«%s» как одиночное действие ничего не делает — это модификатор. "
                "Выберите режим удержания" % action
            )
    else:
        raise InvalidAction("Неизвестный режим действия: %s" % mode)

    label = human or humanize_trigger(trigger, catalog)
    return Rule(
        id=rule_id or new_id(),
        name=name or "%s ➔ %s" % (label, action),
        trigger=trigger,
        action=action,
        scope=scope,
        mode=mode,
        enabled=enabled,
        transparent=transparent,
    )


@dataclass(frozen=True)
class RuleDraft:
    """Черновик из любого источника: DSL, физический захват, выбор из каталога.

    Всё, что отличает способы создания, — поля этого объекта; путь
    draft → Rule → сохранение → применение при этом один.
    """

    trigger: str
    action: str
    scope: str = GLOBAL_SCOPE
    want_remap: bool = False
    human: str = ""
    transparent: bool = False
    notes: Tuple[str, ...] = ()

    def finalize(self, catalog: KeyCatalog,
                 rule_id: Optional[str] = None) -> Tuple[Rule, List[str]]:
        """Превратить в правило, вернув сопроводительные заметки для интерфейса."""
        notes = list(self.notes)
        action = canonical_action(self.action, catalog)
        info = catalog.resolve(action)

        mode = MODE_SEND
        if self.want_remap:
            if info and catalog.supports(info, REMAP):
                mode = MODE_REMAP
            else:
                notes.append(
                    "Удержание применено только для одиночных клавишей — "
                    "«%s» отправляется как последовательность" % action
                )
            if mode == MODE_REMAP and self.transparent:
                notes.append("Прозрачность не применена: она несовместима с удержанием")

        rule = build(
            catalog,
            trigger=self.trigger,
            action=action,
            scope=self.scope,
            mode=mode,
            human=self.human,
            transparent=self.transparent if mode != MODE_REMAP else False,
            rule_id=rule_id,
        )
        return rule, notes


class RuleSet:
    """Иммутационная коллекция правил с контролем конфликтов триггеров."""

    def __init__(self, rules: Iterable[Rule] = ()):
        self.rules: Tuple[Rule, ...] = tuple(rules)

    def __iter__(self):
        return iter(self.rules)

    def __len__(self):
        return len(self.rules)

    def __eq__(self, other):
        return isinstance(other, RuleSet) and self.rules == other.rules

    @property
    def active(self) -> List[Rule]:
        return [r for r in self.rules if r.enabled]

    def find(self, rule_id: str) -> Optional[Rule]:
        return next((r for r in self.rules if r.id == rule_id), None)

    def owner_of(self, rule: Rule) -> Optional[Rule]:
        """Какое существующее правило заняло триггер нового."""
        for existing in self.rules:
            if existing.conflict_key == rule.conflict_key:
                return existing
        return None

    def add(self, rule: Rule) -> "RuleSet":
        taken = self.owner_of(rule)
        if taken is not None:
            raise DuplicateTrigger(rule, taken.name)
        return RuleSet(list(self.rules) + [rule])

    def replace(self, rule: Rule) -> "RuleSet":
        found = self.find(rule.id)
        if found is None:
            raise RuleNotFound("Правило %s не найдено" % rule.id)
        clash = self.owner_of(rule)
        if clash is not None and clash.id != rule.id:
            raise DuplicateTrigger(rule, clash.name)
        return RuleSet([rule if r.id == rule.id else r for r in self.rules])

    def remove(self, rule_id: str) -> "RuleSet":
        if self.find(rule_id) is None:
            raise RuleNotFound("Правило %s не найдено" % rule_id)
        return RuleSet([r for r in self.rules if r.id != rule_id])

    def toggled(self, rule_id: str) -> "RuleSet":
        rule = self.find(rule_id)
        if rule is None:
            raise RuleNotFound("Правило %s не найдено" % rule_id)
        return self.replace(replace(rule, enabled=not rule.enabled))

    def without_conflicts(self) -> Tuple["RuleSet", List[str]]:
        """Страховка: набор на вход уже валиден, но данные могли прийти извне."""
        kept: List[Rule] = []
        notes: List[str] = []
        seen: Dict[Tuple[str, str], str] = {}
        for rule in self.rules:
            holder = seen.get(rule.conflict_key)
            if holder is not None:
                notes.append("«%s» пропущено: триггер %s занят правилом «%s»"
                             % (rule.name, rule.trigger, holder))
                continue
            seen[rule.conflict_key] = rule.name
            kept.append(rule)
        return RuleSet(kept), notes
