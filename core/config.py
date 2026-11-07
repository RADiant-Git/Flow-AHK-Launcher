# -*- coding: utf-8 -*-
"""Пути, константы и значения из plugin.json.

Здесь принимаются два независимых решения о том, «где лежит файл».

1. `plugin.json` — единственный источник `IcoPath`, `ActionKeyword` и имени
   плагина: их повторение в коде уже приводило к сломанной иконке.

2. Пользовательские данные (`modules.json`, `session.json`) и сгенерированный
   `runtime.ahk` лежат **вне папки плагина**. Flow Launcher обновляет плагин
   так: распаковывает новую версию в соседнюю папку, помечает старую файлом
   `NeedDelete.txt` и удаляет её при следующем запуске. Всё, что лежит внутри
   папки плагина, обновление уничтожает. Каталог настроек плагина
   (`Settings/Plugins/<Name>`) переживает и обновление, и удаление плагина с
   сохранением настроек, поэтому данные живут там.
"""

import json
import os
import shutil

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CORE_DIR)

SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

CAPTURE_SCRIPT = os.path.join(SCRIPTS_DIR, "capture.ahk")

# Сколько секунд ждать нажатие при захвате и сколько дать AHK на /validate.
CAPTURE_TIMEOUT = 10
VALIDATE_TIMEOUT = 20

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "FlowKeyManagerRuntime"

# Как Flow Launcher раскладывает свои данные (DataLocation.cs).
PORTABLE_FOLDER = "UserData"
DEAD_MARKER = ".dead"           # признак «портативные данные отключены»
SETTINGS_SUBDIR = ("Settings", "Plugins")


def _read_manifest():
    path = os.path.join(BASE_DIR, "plugin.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


MANIFEST = _read_manifest()

# IcoPath в результатах Flow Launcher разрешается относительно папки плагина.
ICON_PATH = MANIFEST.get("IcoPath") or "Images/app.png"
ACTION_KEYWORD = MANIFEST.get("ActionKeyword") or "key"
PLUGIN_NAME = MANIFEST.get("Name") or "FlowKey Manager"


def flow_data_dir(program_dir: str = "", roaming: str = "") -> str:
    """Каталог данных Flow Launcher — та же формула, что в DataLocation.cs.

    Портативный режим (`<папка программы>\\UserData`) главнее, но только если
    каталог существует и не помечен файлом `.dead`.
    """
    if program_dir:
        portable = os.path.join(program_dir, PORTABLE_FOLDER)
        if os.path.isdir(portable) and not os.path.exists(
                os.path.join(portable, DEAD_MARKER)):
            return portable
    return os.path.join(roaming, "FlowLauncher") if roaming else ""


def plugin_data_dir(plugin_name: str, program_dir: str = "", roaming: str = "") -> str:
    """Постоянный каталог плагина; пустая строка — если его не из чего собрать.

    Каталог здесь только вычисляется: создаёт его первая запись
    (`storage._atomic_write`), поэтому импорт модуля не трогает диск.
    """
    root = flow_data_dir(program_dir, roaming)
    if not root or not plugin_name:
        return ""
    return os.path.join(root, *SETTINGS_SUBDIR, plugin_name)


def migrate_legacy(legacy: str, target: str) -> bool:
    """Перенести файл из папки плагина в постоянный каталог.

    Копия, а не перемещение: пока старая папка на месте, исходник остаётся
    нетронутым, а обновление плагина всё равно удалит её целиком. Существующий
    target не перезаписывается никогда — иначе повторный запуск затирал бы
    актуальные правила копией из архива.
    """
    if not target or target == legacy:
        return False
    if os.path.exists(target) or not os.path.exists(legacy):
        return False
    folder = os.path.dirname(target)
    try:
        if folder:
            os.makedirs(folder, exist_ok=True)
        shutil.copy2(legacy, target)
    except OSError:
        return False
    return True


DATA_DIR = plugin_data_dir(
    PLUGIN_NAME,
    os.environ.get("FLOW_PROGRAM_DIRECTORY") or "",
    os.environ.get("APPDATA") or "",
)

# Данные рядом с кодом — запасной вариант для запуска без Flow Launcher и для
# машин без APPDATA. В этом режиме обновление плагина их потеряет.
RULES_FILE = os.path.join(DATA_DIR or BASE_DIR, "modules.json")
STATE_FILE = os.path.join(DATA_DIR or BASE_DIR, "session.json")
RUNTIME_SCRIPT = os.path.join(DATA_DIR or BASE_DIR, "runtime.ahk")

_LEGACY_FILES = (
    (os.path.join(BASE_DIR, "modules.json"), RULES_FILE),
    (os.path.join(BASE_DIR, "session.json"), STATE_FILE),
)


def ensure_migrated() -> int:
    """Разово перенести данные установок, сделанных до переезда.

    Вызывается из точки входа (`main.py`), а не при импорте: импорт модуля не
    должен писать на диск, иначе тесты и любой сторонний импорт создавали бы
    каталоги в чужом профиле.
    """
    return sum(1 for legacy, target in _LEGACY_FILES
               if migrate_legacy(legacy, target))

