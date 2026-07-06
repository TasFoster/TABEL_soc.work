"""Хранилище функции «Проезд»: статичные реквизиты (settings.json) и
формы имени соцработников (worker_forms.json) — род. падеж и короткая форма
для заявления, с автоподстановкой и возможностью поправить вручную."""

import os

from ...core import db as _db
from ...core import storage as _core

FEATURE = "proezd"
_PKG = os.path.dirname(os.path.abspath(__file__))


def load_settings():
    """Настройки функции: пользовательский settings.json, дополненный НОВЫМИ ключами
    из пакетного дефолта (правки пользователя в приоритете).

    Это решает проблему «JSON — только сид»: на уже существующей установке live-файл
    мог быть создан раньше и не содержать новых ключей (напр. known_series). Слияние
    подтягивает новые ключи из дефолта, не затирая пользовательские значения."""
    import json
    user = _core.load_json(FEATURE, _PKG, "settings.json")
    base = {}
    try:
        dpath = os.path.join(_core.feature_resource_dir(FEATURE, _PKG), "data", "settings.json")
        with open(dpath, "r", encoding="utf-8") as f:
            base = json.load(f)
    except Exception:  # noqa: BLE001
        base = {}
    return {**base, **(user or {})}


def load_calendar():
    """Общий производственный календарь (БД) -> ProductionCalendar.

    Из него «Проезд» берёт праздники и перенесённые РАБОЧИЕ дни (work_days),
    например рабочую среду по переносу."""
    from ..timesheet.calendar_ru import ProductionCalendar
    return ProductionCalendar(_db.calendar_load(), 8, 7)


# --------------------------------------------------------------- лексикон подсказок
def load_lexicon():
    """Накопленный словарь подсказок (значения колонок из прошлых отчётов)."""
    import json
    path = os.path.join(_core.feature_data_dir(FEATURE), "lexicon.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_lexicon(obj):
    _core.save_json(FEATURE, "lexicon.json", obj)


def reestr_fio():
    """ФИО клиентов и соцработников из общей базы (Реестр) — для подсказок."""
    try:
        from ...core import db
        m = db.reestr_map_load()
        return list(m.get("client_worker", {}).keys()) + list(m.get("worker_order", []))
    except Exception:  # noqa: BLE001
        return []


def save_settings(obj):
    _core.save_json(FEATURE, "settings.json", obj)


def template_path():
    return _core.template_path(FEATURE, _PKG, "proezd_template.ods")


def load_worker_forms():
    path = os.path.join(_core.feature_data_dir(FEATURE), "worker_forms.json")
    if os.path.exists(path):
        import json
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_worker_forms(obj):
    _core.save_json(FEATURE, "worker_forms.json", obj)


def forms_for(full_name):
    """Вернуть {genitive, short} для ФИО: из сохранённого, иначе автоподстановка."""
    saved = load_worker_forms().get(full_name.strip())
    if saved:
        return {"genitive": saved.get("genitive") or derive_genitive(full_name),
                "short": saved.get("short") or derive_short(full_name)}
    return {"genitive": derive_genitive(full_name), "short": derive_short(full_name)}


def remember_forms(full_name, genitive, short):
    forms = load_worker_forms()
    forms[full_name.strip()] = {"genitive": genitive.strip(), "short": short.strip()}
    save_worker_forms(forms)


# --------------------------------------------------------------- авто-склонение
# Грубая эвристика склонения ФИО в род. падеж (пол определяется по отчеству) —
# только как СТАРТОВАЯ подстановка; пользователь правит и сохраняет.

def derive_short(full_name):
    parts = full_name.split()
    if not parts:
        return full_name
    surname = parts[0]
    initials = "".join(p[0] + "." for p in parts[1:3])
    return f"{surname} {initials}".strip()


_VOWELS = "аеёиоуыэюя"


def _gender(parts):
    patr = parts[2].lower() if len(parts) >= 3 else ""
    if patr.endswith(("ич", "ыч")):
        return "m"
    return "f"  # по умолчанию женский (большинство соцработников)


def _gen_word(w, kind, gender):
    low = w.lower()
    if kind == "surname":
        if low.endswith(("ко", "их", "ых", "енко")):
            return w  # несклоняемые
        if gender == "f":
            for suf, rep in (("ова", "овой"), ("ева", "евой"), ("ёва", "ёвой"),
                             ("ина", "иной"), ("ына", "ыной"), ("ая", "ой")):
                if low.endswith(suf):
                    return w[: -len(suf)] + rep
            return w[:-1] + "ой" if low.endswith("а") else w
        # мужской
        if low.endswith(("ов", "ев", "ёв", "ин", "ын")):
            return w + "а"
        if low.endswith("ий"):
            return w[:-2] + "ого"
        if low.endswith("ый"):
            return w[:-2] + "ого"
        if low.endswith("ой"):
            return w[:-2] + "ого"
        if low[-1] not in _VOWELS:
            return w + "а"
        return w
    if kind == "patronymic":
        if low.endswith(("вна", "чна")):
            return w[:-1] + "ы"
        if low.endswith(("ич", "ыч")):
            return w + "а"
        return w
    # имя
    if low.endswith("ия"):
        return w[:-2] + "ии"
    if low.endswith("я"):
        return w[:-1] + "и"
    if low.endswith("а"):
        # после г/к/х/ж/ч/ш/щ пишется «и», иначе «ы» (Ольга->Ольги, Анна->Анны)
        return w[:-1] + ("и" if len(low) >= 2 and low[-2] in "гкхжчшщ" else "ы")
    if low.endswith("й"):
        return w[:-1] + "я"
    if low[-1] not in _VOWELS:
        return w + "а"
    return w


def derive_genitive(full_name):
    parts = full_name.split()
    if not parts:
        return full_name
    g = _gender(parts)
    kinds = ["surname", "name", "patronymic"]
    return " ".join(_gen_word(p, kinds[i] if i < 3 else "name", g)
                    for i, p in enumerate(parts[:3]))
