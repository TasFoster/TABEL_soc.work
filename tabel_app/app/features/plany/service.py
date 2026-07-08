"""Контроллер функции «Планы».

Берёт фиксированный шаблон месяца, сдвигает год во всех датах на нужный (единый
offset от базового года шаблонов) и подставляет соцработника «Заслушивания», затем
пишет .odt. Список задач не меняется — из года в год меняются только год и соцработник.
"""

import copy
import re

from . import storage
from .writer import generate as _write

MONTHS_NOM = ["", "январь", "февраль", "март", "апрель", "май", "июнь",
              "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def month_num(name):
    n = (name or "").strip().lower()
    for i, m in enumerate(MONTHS_NOM):
        if i and m == n:
            return i
    return 0


def shift_years(text, offset):
    """Сдвинуть все годы в тексте на offset: 4-значные 20XX и 2-значные в датах ДД.ММ.ГГ."""
    if not offset or not text:
        return text
    # 4-значный год 20XX (границы — «не цифра», т.к. \b не срабатывает после «_»,
    # напр. в строке подписи «________2025 г.»)
    text = re.sub(r"(?<!\d)(20\d\d)(?!\d)",
                  lambda m: str(int(m.group(1)) + offset), text)

    def yy(m):
        ny = (2000 + int(m.group("yy")) + offset) % 100
        return "%s%02d" % (m.group("pre"), ny)

    # 2-значный год в дате ДД.ММ.ГГ
    return re.sub(r"(?<!\d)(?P<pre>\d{1,2}\.\d{1,2}\.)(?P<yy>\d{2})(?!\d)", yy, text)


def effective_worker(dept, year, month):
    """Соцработник для (отд, год, месяц): запомненный, иначе из шаблона."""
    return storage.worker_load(dept, year, month) or storage.default_worker(dept, month)


def build_plan(dept, month, year):
    """Собрать данные плана: копия шаблона со сдвинутым годом и подставленным соцработником."""
    tpl = storage.month_template(dept, month)
    offset = int(year) - storage.baseline_year()
    plan = copy.deepcopy(tpl)

    # подстановка соцработника «Заслушивания» (prefix + ФИО + suffix)
    pos = tpl.get("sign_pos")
    if pos:
        worker = effective_worker(dept, year, month)
        si, ri = pos
        prefix, suffix = tpl.get("sign_prefix", ""), tpl.get("sign_suffix", "")
        # в источнике между ФИО и «о проделанной…» часто нет пробела — добавим
        sep = " " if worker and suffix[:1] not in (" ", "") else ""
        plan["sections"][si]["rows"][ri][1] = "%s%s%s%s" % (prefix, worker, sep, suffix)

    # сдвиг года по всему документу
    plan["header"] = [shift_years(x, offset) for x in plan.get("header", [])]
    plan["footer"] = [shift_years(x, offset) for x in plan.get("footer", [])]
    for sec in plan.get("sections", []):
        sec["rows"] = [[shift_years(c, offset) for c in row] for row in sec["rows"]]
    return plan


def has_sign(dept, month):
    """Есть ли в этом месяце пункт «Заслушивание» (редактируемый соцработник)."""
    return bool(storage.month_template(dept, month).get("sign_pos"))


def generate(out_path, dept, month, year):
    """Сформировать план месяца в .odt. Соцработник берётся из БД/шаблона."""
    plan = build_plan(dept, month, year)
    _write(out_path, plan)
    return out_path
