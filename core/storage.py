# -*- coding: utf-8 -*-
"""Атомарное хранилище двух документов: правил и состояния.

Flow Launcher запускает плагин новым процессом на каждое взаимодействие, поэтому
два процесса вполне могут прочитать и перезаписать один файл. Отсюда два
требования, которых не было в прежней реализации:

* запись только через временный файл и os.replace — обрыв посреди записи больше
  не уничтожает все правила;
* блокировка msvcrt на время «прочитал → изменил → записал».

Формат правил версионируется: v1 (плоский список с trigger_ahk/target/app/hold)
мигрируется в v2 при чтении и больше не записывается.
"""

import contextlib
import json
import msvcrt
import os
import time
from typing import Callable, Optional, Tuple

from core.catalog import KeyCatalog
from core.config import RULES_FILE, STATE_FILE
from core.model import Rule, RuleSet
from core.session import Wizard

FORMAT_VERSION = 2
LOCK_TIMEOUT = 2.0
LOCK_RETRY = 0.02

EMPTY_STATE = {
    "format_version": FORMAT_VERSION,
    "wizard": {},
    "global_paused": False,
    "notices": [],
    "applied_hash": "",
}


class StorageError(Exception):
    pass


@contextlib.contextmanager
def _locked(path: str):
    """Неблокирующая попытка взять файловую блокировку с дедлайном.

    При превышении дедлайна работа продолжается без блокировки: зависший
    интерфейс хуже, чем редкая гонка, а повреждение файла исключает атомарная
    запись.
    """
    handle = None
    acquired = False
    try:
        handle = os.open(path + ".lock", os.O_RDWR | os.O_CREAT)
        deadline = time.time() + LOCK_TIMEOUT
        while True:
            try:
                msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
                acquired = True
                break
            except OSError:
                if time.time() >= deadline:
                    break
                time.sleep(LOCK_RETRY)
        yield acquired
    except OSError:
        # Каталог недоступен для записи — не блокируем, пусть выше станет видно.
        yield False
    finally:
        if handle is not None:
            if acquired:
                try:
                    msvcrt.locking(handle, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            try:
                os.close(handle)
            except OSError:
                pass


def _atomic_write(path: str, text: str) -> None:
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read_json(path: str):
    """Прочитать JSON. utf-8-sig терпит BOM: файлы правят сторонними редакторами.

    Без этого файл с BOM молча считался бы пустым и правила «исчезли».
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


class RuleStore:
    """modules.json: набор правил. Единственный источник правды о биндах."""

    def __init__(self, path: str = RULES_FILE, catalog: Optional[KeyCatalog] = None):
        self.path = path
        self.catalog = catalog

    def load(self, catalog: Optional[KeyCatalog] = None) -> RuleSet:
        return self._load(catalog or self.catalog)

    def _load(self, catalog: Optional[KeyCatalog]) -> RuleSet:
        catalog = catalog or self.catalog
        raw = _read_json(self.path)
        if catalog is None:
            return RuleSet()
        rules = []
        for entry in self._entries(raw):
            try:
                rules.append(Rule.from_json(entry, catalog))
            except Exception:
                # Битая запись не должна обесценивать остальные правила.
                continue
        return RuleSet(rules)

    @staticmethod
    def _entries(raw) -> list:
        if raw is None:
            return []
        if isinstance(raw, list):           # формат v1
            return [e for e in raw if isinstance(e, dict)]
        if isinstance(raw, dict):
            entries = raw.get("rules") or []
            return [e for e in entries if isinstance(e, dict)]
        return []

    def save(self, ruleset: RuleSet) -> None:
        document = {
            "format_version": FORMAT_VERSION,
            "rules": [rule.to_json() for rule in ruleset],
        }
        _atomic_write(self.path, json.dumps(document, ensure_ascii=False, indent=2))

    def mutate(self, transform: Callable[[RuleSet], Tuple[object, RuleSet]]
               ) -> Tuple[object, RuleSet]:
        """Атомарная транзакция: transform(current) → (результат, новый набор).

        Если transform бросает исключение, файл не переписывается.
        """
        with _locked(self.path):
            current = self._load(self.catalog)
            result, updated = transform(current)
            self.save(updated)
        return result, updated


class StateStore:
    """session.json: стадия мастера, пауза, замечания, хэш применённых хуков."""

    def __init__(self, path: str = STATE_FILE):
        self.path = path

    def load(self) -> dict:
        raw = _read_json(self.path) or {}
        state = dict(EMPTY_STATE)
        state.update({k: v for k, v in raw.items() if k in state})
        return state

    def save(self, state: dict) -> None:
        merged = dict(EMPTY_STATE)
        merged.update(state)
        merged["format_version"] = FORMAT_VERSION
        _atomic_write(self.path, json.dumps(merged, ensure_ascii=False))

    def update(self, **changes) -> dict:
        with _locked(self.path):
            state = self.load()
            state.update(changes)
            self.save(state)
        return state

    # --- Удобства ---

    def wizard(self) -> Wizard:
        return Wizard.from_json(self.load().get("wizard"))

    def set_wizard(self, wizard: Wizard) -> None:
        self.update(wizard=wizard.to_json())

    def is_paused(self) -> bool:
        return bool(self.load().get("global_paused"))

    def notices(self) -> list:
        value = self.load().get("notices") or []
        return [str(v) for v in value] if isinstance(value, list) else []

    def set_notices(self, notices) -> None:
        self.update(notices=[str(n) for n in notices])

    def applied_hash(self) -> str:
        return str(self.load().get("applied_hash") or "")
