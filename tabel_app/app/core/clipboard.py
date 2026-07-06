"""Горячие клавиши буфера обмена на НЕлатинских раскладках (русская и т.п.).

Проблема: на русской раскладке Ctrl+C/V/X/A дают keysym `Cyrillic_es/em/che/ef`, а
штатные привязки Tkinter ждут латинские (`c/v/x/a`) — поэтому копирование/вставка/
вырезание/выделение во всех полях ввода НЕ работают.

Решение: добавляем кириллические сочетания к виртуальным событиям
`<<Copy>>/<<Paste>>/<<Cut>>/<<SelectAll>>`. Тогда РОДНЫЕ обработчики Tkinter
срабатывают на обеих раскладках, без дублирования (одно нажатие = один keysym).

`event_add` действует на уровне всего приложения (интерпретатора Tk), поэтому достаточно
вызвать `enable_cyrillic_clipboard(root)` ОДИН раз при запуске — это покрывает все окна.
"""

import tkinter as tk

# Виртуальное событие -> кириллические keysym (нижний и верхний регистр) на физических
# клавишах C / V / X / A раскладки ЙЦУКЕН (с / м / ч / ф).
_MAP = {
    "<<Copy>>":      ("Cyrillic_es",  "Cyrillic_ES"),
    "<<Paste>>":     ("Cyrillic_em",  "Cyrillic_EM"),
    "<<Cut>>":       ("Cyrillic_che", "Cyrillic_CHE"),
    "<<SelectAll>>": ("Cyrillic_ef",  "Cyrillic_EF"),
}


def enable_cyrillic_clipboard(root):
    """Включить копирование/вставку/вырезание/выделение на кириллической раскладке."""
    for virt, keysyms in _MAP.items():
        for ks in keysyms:
            try:
                root.event_add(virt, f"<Control-{ks}>")
            except tk.TclError:  # неизвестный keysym в этой сборке Tk — пропускаем
                pass
