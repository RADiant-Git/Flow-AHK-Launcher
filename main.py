import json
import os
import sys

# Flow Launcher запускает плагин из произвольного рабочего каталога и добавляет
# свои пути к sys.path только в собственной обёртке (PythonPlugin.cs). При
# прямом запуске `python main.py` обёртки нет, поэтому пути к модулям плагина
# добавляем явно. Пакет flowlauncher плагину не нужен: протокол JSON-RPC
# описан в core/rpc.py, а внешних зависимостей у проекта нет.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for _path in (BASE_DIR, os.path.join(BASE_DIR, "lib")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Иконка для аварийной карточки: config может не импортироваться, поэтому путь
# продублирован здесь и в plugin.json.
FALLBACK_ICON = "Images/app.png"


def _bootstrap():
    """Подготовить данные и вернуть точку входа диспетчера."""
    from core import config

    # Данные лежат вне папки плагина: Flow Launcher удаляет её при обновлении,
    # поэтому установки прошлых версий переносятся при первом запуске.
    config.ensure_migrated()

    from core.rpc import main

    return main


def _fail(reason):
    """Ответить карточкой вместо падения.

    Flow Launcher считает ненулевой код возврата и трейсбек в stderr ошибкой
    плагина, заворачивает их в `FlowPluginException` и бросает в поток
    интерфейса — падает всё приложение, а не плагин. Поэтому даже не сумев
    запуститься, плагин обязан выдать валидный JSON и выйти с нулём.
    """
    print(json.dumps({"result": [{
        "Title": "⚠️ Плагин не запустился",
        "SubTitle": str(reason)[:300],
        "IcoPath": FALLBACK_ICON,
    }]}, ensure_ascii=True))


if __name__ == "__main__":
    try:
        _main = _bootstrap()
    except Exception as exc:  # noqa: BLE001 — иначе хост упадёт вместе с нами
        _fail("%s: %s" % (type(exc).__name__, exc))
        sys.exit(0)
    sys.exit(_main())
