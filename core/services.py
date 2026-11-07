# -*- coding: utf-8 -*-
"""Сценарии (use cases): единственный путь, который меняет состояние системы.

Каждый сценарий — транзакция: прочитать → проверить в модели → атомарно
сохранить → применить хуки → собрать замечания для интерфейса. Экраны ничего
не записывают сами, они только вызывают эти функции и показывают результат.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.ahk import capture, codegen, runtime as rt
from core.catalog import KeyCatalog
from core.model import (DuplicateTrigger, FlowKeyError, InvalidAction, MODE_REMAP,
                        Rule, RuleDraft, RuleSet, RuleNotFound)
from core.session import Wizard
from core.storage import RuleStore, StateStore


@dataclass
class Context:
    """Внешний мир плагина, собранный в одном месте."""

    catalog: KeyCatalog = None
    rules: RuleStore = None
    state: StateStore = None
    runtime: rt.AHKRuntime = None

    def __post_init__(self):
        self.catalog = self.catalog or KeyCatalog()
        self.rules = self.rules or RuleStore(catalog=self.catalog)
        self.state = self.state or StateStore()
        self.runtime = self.runtime or rt.AHKRuntime()
        # Внедрённый RuleStore мог прийти без каталога: без него транзакция
        # mutate() молча прочитала бы пустой набор и затерела существующие правила.
        if self.rules.catalog is None:
            self.rules.catalog = self.catalog

    def ruleset(self) -> RuleSet:
        return self.rules.load(self.catalog)

    def wizard(self) -> Wizard:
        return self.state.wizard()


@dataclass
class Outcome:
    """Результат сценария для уровня presentations: чем закончить и что сказать."""

    ok: bool = True
    error: str = ""
    notes: List[str] = field(default_factory=list)
    rule: Optional[Rule] = None

    @property
    def message(self) -> str:
        return self.error or (self.notes[-1] if self.notes else "")


def apply_hooks(ctx: Context, ruleset: Optional[RuleSet] = None,
                paused: Optional[bool] = None) -> Tuple[rt.ApplyResult, List[str]]:
    """Пересобрать скрипт, проверить и применить. Хуки не применяются «вслепую»."""
    current = ctx.ruleset() if ruleset is None else ruleset
    is_paused = ctx.state.is_paused() if paused is None else paused

    safe, notes = current.without_conflicts()
    text, render_notes = codegen.render(safe, ctx.catalog, is_paused)
    notes = list(notes) + list(render_notes)

    result = ctx.runtime.apply(text)
    if result.ok:
        ctx.state.update(applied_hash=result.digest)
    else:
        notes.append(result.error)
    _publish(ctx, notes)
    return result, notes


def _publish(ctx: Context, notes: List[str]) -> None:
    ctx.state.set_notices(notes)


def commit_draft(ctx: Context, draft: RuleDraft, clear_wizard: bool = True) -> Outcome:
    """Единственная точка создания правила — для DSL, захвата и каталога."""
    try:
        rule, notes = draft.finalize(ctx.catalog)
    except FlowKeyError as exc:
        _publish(ctx, [str(exc)])
        return Outcome(ok=False, error=str(exc), notes=[str(exc)])

    try:
        _, updated = ctx.rules.mutate(lambda rs: (rule, rs.add(rule)))
    except DuplicateTrigger as exc:
        _publish(ctx, [str(exc)])
        return Outcome(ok=False, error=str(exc), notes=[str(exc)])
    except FlowKeyError as exc:
        _publish(ctx, [str(exc)])
        return Outcome(ok=False, error=str(exc), notes=[str(exc)])

    if clear_wizard:
        ctx.state.set_wizard(Wizard().reset())

    result, apply_notes = apply_hooks(ctx, updated)
    return Outcome(ok=result.ok, error=result.error,
                   notes=notes + apply_notes, rule=rule)


def create_from_dsl(ctx: Context, formula: str) -> Outcome:
    from core import dsl

    try:
        draft = dsl.parse(formula, ctx.catalog)
    except dsl.DslError as exc:
        _publish(ctx, ["Формула не разобрана: %s" % exc])
        return Outcome(ok=False, error="Формула не разбрана: %s" % exc)
    return commit_draft(ctx, draft, clear_wizard=False)


def capture_key(ctx: Context) -> capture.Capture:
    """Один физический перехват без побочных состояний."""
    return capture.run(ctx.runtime.executable)


def capture_trigger(ctx: Context, wizard: Wizard) -> Tuple[capture.Capture, Wizard]:
    """Записать триггер и перевести мастера в соответствующую стадию."""
    result = capture_key(ctx)
    if result.ok:
        wizard = wizard.captured(result.trigger, result.human)
    else:
        wizard = wizard.reset()
    ctx.state.set_wizard(wizard)
    return result, wizard


def draft_from_wizard(ctx: Context, captured: capture.Capture) -> RuleDraft:
    """Собрать черновик из состояния мастера и записанного действия."""
    wizard = ctx.wizard()
    return RuleDraft(
        trigger=wizard.trigger,
        action=captured.trigger,
        scope=wizard.scope,
        want_remap=wizard.want_remap,
        human=wizard.human or wizard.trigger,
    )


def toggle_rule(ctx: Context, rule_id: str) -> Outcome:
    try:
        _, updated = ctx.rules.mutate(lambda rs: (None, rs.toggled(rule_id)))
    except RuleNotFound as exc:
        _publish(ctx, [str(exc)])
        return Outcome(ok=False, error=str(exc))
    result, notes = apply_hooks(ctx, updated)
    rule = updated.find(rule_id)
    return Outcome(ok=result.ok, error=result.error, notes=notes, rule=rule)


def toggle_transparent(ctx: Context, rule_id: str) -> Outcome:
    """Переключить прозрачность правила (исходное нажатие проходит в окно)."""
    from dataclasses import replace as _replace

    from core.model import InvalidAction

    def transform(rs):
        rule = rs.find(rule_id)
        if rule is None:
            raise RuleNotFound("Правило %s не найдено" % rule_id)
        want = not rule.transparent
        if want and rule.mode == MODE_REMAP:
            raise InvalidAction(
                "Прозрачность не совмещается с удержанием: ремап сам превращает "
                "исходную клавишу в целевую")
        updated = rs.replace(_replace(rule, transparent=want))
        return want, updated

    try:
        want, updated = ctx.rules.mutate(transform)
    except (RuleNotFound, InvalidAction) as exc:
        _publish(ctx, [str(exc)])
        return Outcome(ok=False, error=str(exc), notes=[str(exc)])
    result, notes = apply_hooks(ctx, updated)
    return Outcome(ok=result.ok, error=result.error, notes=notes,
                   rule=updated.find(rule_id))


def delete_rule(ctx: Context, rule_id: str) -> Outcome:
    try:
        _, updated = ctx.rules.mutate(lambda rs: (None, rs.remove(rule_id)))
    except RuleNotFound as exc:
        _publish(ctx, [str(exc)])
        return Outcome(ok=False, error=str(exc))
    result, notes = apply_hooks(ctx, updated)
    return Outcome(ok=result.ok, error=result.error, notes=notes)


def clear_all(ctx: Context) -> Outcome:
    ctx.rules.save(RuleSet())
    result, notes = apply_hooks(ctx, RuleSet())
    return Outcome(ok=result.ok, error=result.error, notes=notes)


def set_paused(ctx: Context, paused: bool) -> Outcome:
    ctx.state.update(global_paused=bool(paused))
    result, notes = apply_hooks(ctx)
    return Outcome(ok=result.ok, error=result.error, notes=notes)


def is_drifted(ctx: Context) -> bool:
    """Записанные правила разошлись с тем, что реально применено."""
    current = ctx.ruleset()
    safe, _ = current.without_conflicts()
    text, _ = codegen.render(safe, ctx.catalog, ctx.state.is_paused())
    applied = ctx.state.applied_hash()
    if not applied:
        return bool(safe.active)
    return applied != codegen.script_hash(text)
