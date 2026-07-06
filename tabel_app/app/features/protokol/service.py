"""Контроллер «Протокола»: реквизиты + план методчаса -> .odt.

От протокола к протоколу меняются № протокола, отделение, присутствующие/отсутствующие;
дата ставится автоматически — **последняя рабочая среда месяца** (методический час);
повестка дня и «кого заслушали» берутся из **плана методического часа** для этого месяца
(`storage.load_plan()`), и при желании правятся в окне.
"""

import calendar as _cal
import datetime
import re

from . import storage
from .writer import generate as _generate

DEFAULTS = {
    "dept_no": "9",
    "zav": "Шершнева Т.И.",
}

MONTHS_NOM = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

_ORDINALS = ["первому", "второму", "третьему", "четвёртому", "пятому", "шестому"]


def last_working_wednesday(year, month):
    """Последняя СРЕДА месяца, являющаяся рабочим днём (методический час)."""
    cal = storage.load_calendar()
    nd = _cal.monthrange(year, month)[1]
    wednesdays = [datetime.date(year, month, d) for d in range(1, nd + 1)
                  if datetime.date(year, month, d).weekday() == 2]
    for d in reversed(wednesdays):          # с конца месяца
        if cal.is_workday(d):
            return d
    return wednesdays[-1] if wednesdays else datetime.date(year, month, nd)


def format_date(d):
    """datetime.date -> 'ДД.ММ.ГГГГ'."""
    return d.strftime("%d.%m.%Y")


def plan_topic(month):
    """Тема (повестка) методчаса для месяца из плана или ''."""
    return (storage.load_plan() or {}).get(str(int(month)), "")


def _plan_items(topic):
    """Разбить тему плана на пункты по нумерации «N.» (одна цифра, чтобы не ловить «10.»)."""
    items = re.split(r"(?:^|\s)\d\.\s*", topic or "")
    return [i.strip() for i in items if i.strip()]


def default_body(month=None, zav=None):
    """Тело протокола (повестка/решения/Разное) из плана методчаса для месяца.

    Структура как в образце: «Повестка дня:» с пунктами, по каждому содержательному
    вопросу «По N-му вопросу заслушали зав. отд. {zav}. Решение: …», затем «Разное:».
    Текст редактируется в окне."""
    zav = (zav or DEFAULTS["zav"]).strip()
    items = _plan_items(plan_topic(month)) if month else []
    if not items:
        items = ["Контроль за качеством выполнения социальных услуг.", "Разное."]

    lines = ["Повестка дня:", ""]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it}")
    lines.append("")

    n = 0
    for it in items:
        if it.lower().startswith("разное"):
            continue
        ordinal = _ORDINALS[n] if n < len(_ORDINALS) else f"{n + 1}-му"
        lines.append(f"По {ordinal} вопросу заслушали зав. отд. {zav.rstrip('.')}.")
        lines.append("Решение: принять информацию к сведению.")
        n += 1

    lines += ["", "Разное:", "", "- "]
    return "\n".join(lines)


def generate(out_path, number, date_str, attendees, body,
             dept_no=None, zav=None, absentees=None):
    """Сформировать протокол.

    attendees — присутствующие; absentees — отсутствующие (перечень в протоколе);
    body — текст повестки/решений/разное."""
    ctx = {
        "number": str(number).strip(),
        "date": str(date_str).strip(),
        "dept_no": (dept_no or DEFAULTS["dept_no"]).strip(),
        "zav": (zav or DEFAULTS["zav"]).strip(),
    }
    return _generate(out_path, ctx, list(attendees), body or "", list(absentees or []))
