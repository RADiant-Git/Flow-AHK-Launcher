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

from core import config  # noqa: E402  (импорт возможен только после sys.path)

# Перенос данных из папки плагина в постоянный каталог: Flow Launcher удаляет
# папку плагина при обновлении, поэтому данные должны лежать вне неё.
config.ensure_migrated()

from core.rpc import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
