# -*- coding: utf-8 -*-
"""Управление процессом AutoHotkey: поиск, проверка, применение, автозапуск.

Порядок применения важен: скрипт сначала проверяется через `AHK /validate`
(разбор без выполнения — хуки не ставятся, побочные эффектов нет), и только
если он корректен, записывается runtime.ahk и запускается. Прежний порядок
«записать, потом запустить и надеяться» оставлял пользователя с сырым
сообщением интерпретатора и без работающих хуков.
"""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

from core import config
from core.ahk.codegen import script_hash

STANDARD_PATHS = (
    r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe",
    r"C:\Program Files\AutoHotkey\v2\AutoHotkey32.exe",
    r"C:\Program Files\AutoHotkey\AutoHotkey64.exe",
    r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
)

_ERROR_RE = re.compile(r"\((?P<line>\d+)\)\s*:\s*==>\s*(?P<what>.+?)"
                       r"(?:\s+Specifically:\s*(?P<detail>.+?))?\s*\Z", re.S)


def locate_ahk() -> str:
    for name in ("AutoHotkey64.exe", "AutoHotkey.exe"):
        found = shutil.which(name)
        if found:
            return found
    for path in STANDARD_PATHS:
        if os.path.exists(path):
            return path
    return STANDARD_PATHS[0]


@dataclass
class ApplyResult:
    ok: bool
    error: str = ""
    digest: str = ""
    launched: bool = False

    @property
    def failure(self) -> str:
        return self.error


def _format_error(message: str) -> str:
    """Сырой вывод интерпретатора — в человеческую форму."""
    cleaned = " ".join(str(message).split())
    if not cleaned:
        return "AutoHotkey не смог разобрать скрипт хуков"
    match = _ERROR_RE.search(cleaned)
    if match:
        detail = match.group("detail")
        body = match.group("what").strip().rstrip(".")
        if detail:
            return "Строка %s: %s (%s)" % (match.group("line"), body, detail.strip())
        return "Строка %s: %s" % (match.group("line"), body)
    return cleaned[:300]


class AHKRuntime:
    def __init__(self, executable: Optional[str] = None,
                 script_path: str = config.RUNTIME_SCRIPT):
        self.script_path = script_path
        self.executable = executable or locate_ahk()

    @property
    def available(self) -> bool:
        return os.path.exists(self.executable)

    # --- Проверка -----------------------------------------------------

    def validate(self, text: str) -> str:
        """Вернуть "" для корректного скрипта, иначе — готовое к показу сообщение."""
        if not self.available:
            return ("AutoHotkey v2 не найден — установите его или укажите путь "
                    "в настройках Flow Launcher")
        folder = os.path.dirname(os.path.abspath(self.script_path))
        try:
            # runtime.ahk живёт в постоянном каталоге плагина, который до первой
            # записи может не существовать: mkstemp не создаёт папок.
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            return ("Не удалось подготовить каталог для runtime.ahk: %s"
                    % (exc.strerror or exc))
        handle, path = tempfile.mkstemp(suffix=".ahk", prefix="flowkey-check-", dir=folder)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as probe:
                probe.write(text)
            try:
                proc = subprocess.run(
                    [self.executable, "/ErrorStdOut", "/validate", path],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=config.VALIDATE_TIMEOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except subprocess.TimeoutExpired:
                return "AutoHotkey не ответил за %s секунд" % config.VALIDATE_TIMEOUT
            except OSError as exc:
                return "Не удалось запустить AutoHotkey: %s" % exc.strerror or str(exc)
            if proc.returncode == 0:
                return ""
            return _format_error((proc.stderr or proc.stdout or "").strip())
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    # --- Применение ---------------------------------------------------

    def apply(self, text: str) -> ApplyResult:
        digest = script_hash(text)
        error = self.validate(text)
        if error:
            return ApplyResult(ok=False, error=error, digest="")
        try:
            self._write(text)
        except OSError as exc:
            return ApplyResult(ok=False, error="Не удалось записать runtime.ahk: %s" % exc,
                               digest="")
        try:
            subprocess.Popen([self.executable, self.script_path],
                             creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as exc:
            return ApplyResult(ok=False,
                               error="Не удалось запустить AutoHotkey: %s" % exc,
                               digest="")
        return ApplyResult(ok=True, digest=digest, launched=True)

    def _write(self, text: str) -> None:
        folder = os.path.dirname(os.path.abspath(self.script_path))
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp = self.script_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.script_path)


# --- Автозапуск -------------------------------------------------------


def autostart_command(runtime: AHKRuntime) -> str:
    return '"%s" "%s"' % (runtime.executable, runtime.script_path)


def autostart_enabled(runtime: AHKRuntime) -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, config.RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, config.RUN_VALUE)
            return str(value) == autostart_command(runtime)
    except OSError:
        return False
    except Exception:
        return False


def set_autostart(runtime: AHKRuntime, enabled: bool) -> str:
    """Вернуть пустую строку при успехе или причину отказа."""
    try:
        import winreg
    except ImportError:
        return "Автозапуск доступен только в Windows"
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, config.RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, config.RUN_VALUE, 0, winreg.REG_SZ,
                                  autostart_command(runtime))
            else:
                try:
                    winreg.DeleteValue(key, config.RUN_VALUE)
                except FileNotFoundError:
                    pass
        return ""
    except OSError as exc:
        return "Не удалось изменить автозапуск: %s" % (exc.strerror or exc)
