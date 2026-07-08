"""Глобальные горячие клавиши редактирования во всех окнах приложения.

Работают на ЛЮБОЙ раскладке (латиница, русская ЙЦУКЕН и др.):
  • Копировать / Вставить / Вырезать — Ctrl+C / Ctrl+V / Ctrl+X;
  • Выделить всё — Ctrl+A;
  • Отменить / Повторить — Ctrl+Z / Ctrl+Y.

Почему клавиша определяется по КОДУ (keycode), а не по СИМВОЛУ (keysym):
  На латинице всё уже работает штатно: Tk по умолчанию привязывает Ctrl+C/V/X/A/Z/Y к
  виртуальным событиям <<Copy>>/<<Paste>>/<<Cut>>/<<SelectAll>>/<<Undo>>/<<Redo>>.
  Но на русской раскладке Ctrl+C даёт keysym не `c`, а кириллический символ (и, в
  зависимости от сборки Tk/Windows, РАЗНЫЙ) — эти виртуальные события не срабатывают,
  и «горячие клавиши не работают». `keycode` же одинаков независимо от раскладки (это
  физическая клавиша), поэтому мы ловим Ctrl+<любая раскладка> одним обработчиком
  `<Control-KeyPress>` и диспетчеризуем по keycode — но ТОЛЬКО когда keysym НЕ латинский
  (иначе штатный механизм уже отработал, и было бы двойное действие).

Отмена/повтор: у tk.Entry/ttk-полей своей истории нет — ведём стек снимков значения
(и на латинице привязываем его к штатным <<Undo>>/<<Redo>>, а на прочих раскладках —
через keycode); у tk.Text включаем родную отмену (undo=True) при фокусе.

Вызывается один раз при запуске — enable_hotkeys(root) в shell.py.
"""

import tkinter as tk

# Логическое действие -> (латинские keysym'ы клавиши, её keycode на Windows).
# keysym нужен, чтобы на латинице НЕ дублировать штатные copy/paste/cut;
# keycode — универсальный распознаватель клавиши для ЛЮБОЙ раскладки.
_ACTIONS = {
    "copy":  (("c",), 67),   # C
    "paste": (("v",), 86),   # V
    "cut":   (("x",), 88),   # X
    "all":   (("a",), 65),   # A
    "undo":  (("z",), 90),   # Z
    "redo":  (("y",), 89),   # Y
}
_BY_KEYSYM = {ks: act for act, (kss, _) in _ACTIONS.items() for ks in kss}
_BY_KEYCODE = {kc: act for act, (_, kc) in _ACTIONS.items()}
_VIRTUAL = {"copy": "<<Copy>>", "paste": "<<Paste>>", "cut": "<<Cut>>"}

# Классы однострочных полей ввода (там ведём свою отмену/повтор и выделение).
_ENTRY_CLASSES = ("Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox")
_ALT_MASK = 0x20000            # бит Alt/AltGr на Windows — такие сочетания не трогаем
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


def _is_text(w):
    try:
        return w.winfo_class() == "Text"
    except tk.TclError:
        return False


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


def _text_native(w, virt):
    try:
        w.event_generate(virt)
    except tk.TclError:
        pass
    return "break"


def _enable_text_undo(event):
    # родная отмена tk.Text работает только при undo=True — включаем при фокусе
    try:
        if not int(event.widget.cget("undo")):
            event.widget.configure(undo=True, autoseparators=True, maxundo=-1)
    except tk.TclError:
        pass


# --------------------------------------------- единый обработчик Ctrl+<клавиша>
def _control_key(event):
    """Ctrl+<клавиша> по keycode — ТОЛЬКО для не-латинских раскладок. На латинице
    возвращает None: там всё делает штатный механизм Tk (виртуальные события) плюс наши
    привязки <<Undo>>/<<Redo>>/<<SelectAll>> (см. enable_hotkeys)."""
    if event.state & _ALT_MASK:            # Ctrl+Alt / AltGr — не наше
        return None
    if event.keysym.lower() in _BY_KEYSYM:  # латиница — обработает штатный Tk
        return None
    act = _BY_KEYCODE.get(event.keycode)    # прочие раскладки — по коду клавиши
    if act is None:
        return None
    w = event.widget
    if act == "all":
        return _select_all(event)
    if act == "undo":
        return _text_native(w, "<<Undo>>") if _is_text(w) else _undo(event)
    if act == "redo":
        return _text_native(w, "<<Redo>>") if _is_text(w) else _redo(event)
    return _text_native(w, _VIRTUAL[act])  # copy/paste/cut


# ------------------------------------------------------------------- монтаж
def enable_hotkeys(root):
    """Включить горячие клавиши редактирования во всём приложении (один вызов).

    Привязки классовые (bind_class) — действуют на все окна интерпретатора Tk,
    включая Toplevel каждой функции."""
    # 1) Единый обработчик Ctrl+<клавиша> для НЕ-латинских раскладок — по keycode.
    for cls in _ENTRY_CLASSES + ("Text",):
        root.bind_class(cls, "<Control-KeyPress>", _control_key, add="+")
    # 2) Латиница: у полей ввода нет своей отмены/повтора и «выделить всё» — привязываем
    #    к штатным виртуальным событиям (Ctrl+Z/Y/A на латинице их триггерят по умолчанию).
    for cls in _ENTRY_CLASSES:
        root.bind_class(cls, "<Key>", _on_key, add="+")          # снимки для отмены
        root.bind_class(cls, "<<Undo>>", _undo, add="+")
        root.bind_class(cls, "<<Redo>>", _redo, add="+")
        root.bind_class(cls, "<<SelectAll>>", _select_all, add="+")
    # 3) Многострочный Text — включить родную отмену при получении фокуса.
    root.bind_class("Text", "<FocusIn>", _enable_text_undo, add="+")


# Обратная совместимость со старым именем.
enable_cyrillic_clipboard = enable_hotkeys
