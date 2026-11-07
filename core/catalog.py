# -*- coding: utf-8 -*-
"""Каталог клавиш: имена AutoHotkey, алиасы, категории и роли.

Роль — главное отличие от прежней реализации. Одна и та же клавиша годится или
не годится в разные слоты правила, и это свойство данных, а не логики экранов:

  trigger — можно ли перехватить и использовать как источник хоткея;
  send    — осмысленно ли как цель Send('{...}');
  remap   — осмысленно ли как цель нативного ремапа `src::tgt`.

Например, одиночный `Send('{LCtrl}')` нажимает и тут же отпускает Ctrl — эффект
нулевой, поэтому у модификаторов send=False, а в режиме ремапа они полезны.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

TRIGGER = "trigger"
SEND = "send"
REMAP = "remap"

ROLE_ATTRIBUTES = {
    TRIGGER: "trigger",
    SEND: "send",
    REMAP: "remap",
}


@dataclass
class KeyInfo:
    ahk_name: str
    display_name: str
    category: str
    aliases: List[str] = field(default_factory=list)
    trigger: bool = True
    send: bool = True
    remap: bool = True


def _key(ahk_name, display_name, category, aliases=(), **roles):
    info = KeyInfo(ahk_name, display_name, category, list(aliases))
    for role, allowed in roles.items():
        setattr(info, ROLE_ATTRIBUTES[role], allowed)
    return info


RAW_KEYS: List[KeyInfo] = [
    # Модификаторы: бесполезны как одиночная цель Send, но годятся в триггеры и ремапы.
    _key("LCtrl", "Left Ctrl", "Modifiers", ["ctrl", "lctrl"], send=False),
    _key("RCtrl", "Right Ctrl", "Modifiers", ["rctrl"], send=False),
    _key("LAlt", "Left Alt", "Modifiers", ["alt", "lalt"], send=False),
    _key("RAlt", "Right Alt", "Modifiers", ["ralt", "altgr"], send=False),
    _key("LShift", "Left Shift", "Modifiers", ["shift", "lshift"], send=False),
    _key("RShift", "Right Shift", "Modifiers", ["rshift"], send=False),
    _key("LWin", "Windows Key", "Modifiers", ["win", "meta"], send=False),

    # Специальные
    _key("CapsLock", "Caps Lock", "Special", ["caps"]),
    _key("Escape", "Escape", "Special", ["esc"]),
    _key("Backspace", "Backspace", "Special", ["bs", "back"]),
    _key("Enter", "Enter / Return", "Special", ["ret"]),
    _key("Space", "Spacebar", "Special", ["space"]),
    _key("Tab", "Tab", "Special"),
    _key("PrintScreen", "Print Screen", "Special", ["prtsc"]),
    _key("Pause", "Pause / Break", "Special"),
    _key("NumLock", "Num Lock", "Special", ["num"]),
    _key("ScrollLock", "Scroll Lock", "Special", ["scroll"]),
    _key("AppsKey", "Меню (контекстное)", "Special", ["menu", "apps"]),

    # Навигация
    _key("Left", "Left Arrow", "Navigation", ["left"]),
    _key("Right", "Right Arrow", "Navigation", ["right"]),
    _key("Up", "Up Arrow", "Navigation", ["up"]),
    _key("Down", "Down Arrow", "Navigation", ["down"]),
    _key("Home", "Home", "Navigation"),
    _key("End", "End", "Navigation"),
    _key("PgUp", "Page Up", "Navigation", ["pageup"]),
    _key("PgDn", "Page Down", "Navigation", ["pagedown"]),
    _key("Delete", "Delete", "Navigation", ["del"]),
    _key("Insert", "Insert", "Navigation", ["ins"]),

    # Мышь. Захватчик перехватывает только среднюю и боковые кнопки, а AutoHotkey
    # не умеет ремапить мышь→мышь и клавишу→мышь.
    _key("MButton", "Middle Click (Колесо)", "Mouse", ["mmb", "middle"], remap=False),
    _key("XButton1", "Mouse 4 (Назад)", "Mouse", ["x1", "mouse4", "back"], remap=False),
    _key("XButton2", "Mouse 5 (Вперёд)", "Mouse", ["x2", "mouse5", "forward"], remap=False),
    _key("LButton", "Левая кнопка мыши", "Mouse", ["lmb"], trigger=False, remap=False),
    _key("RButton", "Правая кнопка мыши", "Mouse", ["rmb"], trigger=False, remap=False),
    _key("WheelUp", "Колесо вверх", "Mouse", ["wheelup"], trigger=False, remap=False),
    _key("WheelDown", "Колесо вниз", "Mouse", ["wheeldown"], trigger=False, remap=False),

    # Медиа
    _key("Volume_Up", "Громкость +", "Media", ["volup"]),
    _key("Volume_Down", "Громкость -", "Media", ["voldown"]),
    _key("Volume_Mute", "Отключить звук (Mute)", "Media", ["mute"]),
    _key("Media_Play_Pause", "Play / Pause", "Media", ["play", "pause"]),
    _key("Media_Next", "Следующий трек", "Media", ["next"]),
    _key("Media_Prev", "Предыдущий трек", "Media", ["prev"]),
    _key("Media_Stop", "Стоп", "Media", ["stop"]),

    # Браузерные / запуск приложений
    _key("Browser_Back", "Браузер: назад", "Browser", ["bback"]),
    _key("Browser_Forward", "Браузер: вперёд", "Browser", ["bforward"]),
    _key("Browser_Refresh", "Браузер: обновить", "Browser", ["brefresh"]),
    _key("Browser_Stop", "Браузер: стоп", "Browser", ["bstop"]),
    _key("Browser_Search", "Браузер: поиск", "Browser", ["bsearch"]),
    _key("Browser_Favorites", "Браузер: избранное", "Browser", ["bfavorites"]),
    _key("Browser_Home", "Браузер: домашняя", "Browser", ["bhome"]),
    _key("Launch_Mail", "Почтовый клиент", "Browser", ["mail"]),
    _key("Launch_Media", "Медиаплеер", "Browser", ["launchmedia"]),
    _key("Launch_App1", "Launch App1", "Browser"),
    _key("Launch_App2", "Launch App2", "Browser"),
]

# Цифровой блок
NUMPAD = [
    ("Numpad0", "Num 0"), ("Numpad1", "Num 1"), ("Numpad2", "Num 2"),
    ("Numpad3", "Num 3"), ("Numpad4", "Num 4"), ("Numpad5", "Num 5"),
    ("Numpad6", "Num 6"), ("Numpad7", "Num 7"), ("Numpad8", "Num 8"),
    ("Numpad9", "Num 9"), ("NumpadDot", "Num ."), ("NumpadEnter", "Num Enter"),
    ("NumpadAdd", "Num +"), ("NumpadSub", "Num -"), ("NumpadMult", "Num *"),
    ("NumpadDiv", "Num /"), ("NumpadDel", "Num Del"), ("NumpadIns", "Num Ins"),
    ("NumpadHome", "Num Home"), ("NumpadEnd", "Num End"), ("NumpadPgUp", "Num PgUp"),
    ("NumpadPgDn", "Num PgDn"), ("NumpadUp", "Num Up"), ("NumpadDown", "Num Down"),
    ("NumpadLeft", "Num Left"), ("NumpadRight", "Num Right"), ("NumpadClear", "Num Clear"),
]
for _name, _human in NUMPAD:
    RAW_KEYS.append(_key(_name, _human, "Numpad", [_name.lower()]))

for _i in range(1, 25):
    RAW_KEYS.append(_key("F%d" % _i, "F%d" % _i, "Function", ["f%d" % _i]))

for _char in "abcdefghijklmnopqrstuvwxyz0123456789":
    RAW_KEYS.append(_key(_char, _char.upper(), "Standard", [_char]))


class KeyCatalog:
    """Поиск и классификация клавиш."""

    def __init__(self, keys: Optional[List[KeyInfo]] = None):
        self.keys = keys if keys is not None else RAW_KEYS
        self._lookup: Dict[str, KeyInfo] = {}
        self._names = set()
        for item in self.keys:
            self._lookup[item.ahk_name.lower()] = item
            self._names.add(item.ahk_name)
            for alias in item.aliases:
                self._lookup.setdefault(alias.lower(), item)

    def resolve(self, token: str) -> Optional[KeyInfo]:
        return self._lookup.get(str(token).lower().strip())

    def is_key_name(self, token: str) -> bool:
        """Точное каноническое имя клавиши (а не алиас и не Send-строка).

        Нужно генератору: имена клавиш уходят в Send в фигурных скобках,
        иначе AutoHotkey печатает их текст.
        """
        return str(token).strip() in self._names

    def supports(self, key: KeyInfo, role: str) -> bool:
        return getattr(key, ROLE_ATTRIBUTES[role])

    def search(self, query: str = "", role: Optional[str] = None) -> List[KeyInfo]:
        needle = str(query).lower().strip()
        pool = [k for k in self.keys if role is None or self.supports(k, role)]
        if not needle:
            return pool
        return [
            k for k in pool
            if needle in k.ahk_name.lower()
            or needle in k.display_name.lower()
            or any(needle in a for a in k.aliases)
        ]
