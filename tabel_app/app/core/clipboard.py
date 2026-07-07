"""Глобальные горячие клавиши редактирования во всех окнах приложения.

Что обеспечивается на ОБЕИХ раскладках (латинской и русской ЙЦУКЕН):
  • Копировать / Вставить / Вырезать (Ctrl+C/V/X, Ctrl+С/М/Ч);
  • Выделить всё (Ctrl+A / Ctrl+Ф);
  • Отменить / Повторить (Ctrl+Z/Y, Ctrl+Я/Н).

Почему нужен отдельный модуль:
  - На русской раскладке Ctrl+C даёт keysym `Cyrillic_es`, а штатные привязки Tkinter
    ждут латинский `c` — поэтому буфер обмена «не работает». Лечится добавлением
    кириллических сочетаний к виртуальным событиям `<<Copy>>` и т.п. (`event_add`
    действует на весь интерпретатор Tk → покрывает все окна, включая Toplevel фич).
  - Отмены/повтора в Tkinter НЕТ: у `tk.Entry`/`ttk.Combobox` её нет вовсе, а `tk.Text`
    требует `undo=True`. Поэтому: для полей ввода ведём свой стек истории (снимок
    значения на каждое нажатие), а всем `Text` включаем родную отмену при фокусе.

Вызывается один раз при запуске — `enable_hotkeys(root)` в `shell.py`.
"""

import tkinter as tk

# Виртуальное событие -> Control-<keysym> для латинской И кириллической раскладок.
# Кириллические keysym соответствуют физическим клавишам C/V/X/A/Z/Y раскладки ЙЦУКЕН
# (с/м/ч/ф/я/н).
_MAP = {
    "<<Copy>>":      ("c", "C", "Cyrillic_es",  "Cyrillic_ES"),
    "<<Paste>>":     ("v", "V", "Cyrillic_em",  "Cyrillic_EM"),
    "<<Cut>>":       ("x", "X", "Cyrillic_che", "Cyrillic_CHE"),
    "<<SelectAll>>": ("a", "A", "Cyrillic_ef",  "Cyrillic_EF"),
    "<<Undo>>":      ("z", "Z", "Cyrillic_ya",  "Cyrillic_YA"),
    "<<Redo>>":      ("y", "Y", "Cyrillic_en",  "Cyrillic_EN"),
}

# Классы полей ввода (одна строка), где нужна ручная отмена/повтор и выделение всё.
_ENTRY_CLASSES = ("Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox")

_UNDO_LIMIT = 300


# ------------------------------------------------------------------ значения
def _entry_get(w):
    try:
        return w.get()
    except Exception:  # noqa: BLE001
        return None


def _entry_set(w, val):
    try:
        w.delete(0, "end")
        w.insert(0, val)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------- выделить всё
def _select_all(event):
    w = event.widget
    try:                                   # одно­строчные поля (Entry/Combobox/Spinbox)
        w.selection_range(0, "end")
        w.icursor("end")
        return "break"
    except tk.TclError:
        pass
    try:                                   # многострочный Text
        w.tag_add("sel", "1.0", "end-1c")
        w.mark_set("insert", "end-1c")
        return "break"
    except tk.TclError:
        pass


# ----------------------------------------------- отмена/повтор для полей ввода
def _snapshot(w):
    val = _entry_get(w)
    if val is None:
        return
    u = getattr(w, "_undo_stack", None)
    if u is None:
        u = w._undo_stack = []
        w._redo_stack = []
    if not u or u[-1] != val:
        u.append(val)
        del u[:-_UNDO_LIMIT]
        w._redo_stack.clear()


def _on_key(event):
    # снимок значения ДО изменения (KeyPress срабатывает раньше вставки символа)
    _snapshot(event.widget)


def _undo(event):
    w = event.widget
    u = getattr(w, "_undo_stack", None)
    cur = _entry_get(w)
    if u is None or cur is None:
        return "break"
    while u and u[-1] == cur:              # отбросить снимки, равные текущему
        u.pop()
    if u:
        w._redo_stack.append(cur)
        _entry_set(w, u[-1])
    return "break"


def _redo(event):
    w = event.widget
    r = getattr(w, "_redo_stack", None)
    if not r:
        return "break"
    val = r.pop()
    getattr(w, "_undo_stack", []).append(val)
    _entry_set(w, val)
    return "break"


def _enable_text_undo(event):
    # родная отмена tk.Text работает только при undo=True — включаем при фокусе
    try:
        if not int(event.widget.cget("undo")):
            event.widget.configure(undo=True, autoseparators=True, maxundo=-1)
    except tk.TclError:
        pass


# ------------------------------------------------------------------- монтаж
def enable_hotkeys(root):
    """Включить горячие клавиши редактирования во всём приложении (один вызов)."""
    # 1) Виртуальные события — обе раскладки.
    for virt, keysyms in _MAP.items():
        for ks in keysyms:
            try:
                root.event_add(virt, f"<Control-{ks}>")
            except tk.TclError:            # неизвестный keysym в этой сборке Tk
                pass

    # 2) Отмена/повтор для однострочных полей — свой стек истории.
    for cls in _ENTRY_CLASSES:
        root.bind_class(cls, "<Key>", _on_key, add="+")
        root.bind_class(cls, "<<Undo>>", _undo, add="+")
        root.bind_class(cls, "<<Redo>>", _redo, add="+")
        root.bind_class(cls, "<<SelectAll>>", _select_all, add="+")

    # 3) Многострочный Text — родная отмена (undo=True) + выделить всё.
    root.bind_class("Text", "<FocusIn>", _enable_text_undo, add="+")
    root.bind_class("Text", "<<SelectAll>>", _select_all, add="+")


# Обратная совместимость со старым именем.
enable_cyrillic_clipboard = enable_hotkeys
