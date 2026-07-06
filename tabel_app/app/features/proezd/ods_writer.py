"""Формирование пакета «Проезд» (.ods) БЕЗ Excel — через odfpy.

На каждого соцработника — два листа по образцу:
  * «отчет_по_проезду» (маршрутный лист): шапка, строки поездок
    (№ · дата · откуда · куда · цель · номер+серия билета), подвал с
    количеством поездок ПРОПИСЬЮ и подписями (сотрудник / зав. отделением);
  * «Заявление»: директору, сумма цифрами и прописью, дата, подпись.

Номера и серии билетов берутся со скана (1-й билет → 1-я поездка). Сумма
считается по таблице цен серий (Σ цена_серии). Microsoft Excel НЕ требуется.
"""

import os

from odf.opendocument import load
from odf.table import Table

from ..reestr import ods_build as ob
from ..reestr.num2words_ru import int_in_words, rubles_kopecks_in_words

REPORT_SHEET = "отчет_по_проезду"
APPL_SHEET = "Заявление"

# Столбцы листа «отчёт» (0-based)
C_NUM, C_DATE, C_FROM, C_TO, C_PURPOSE, C_TICKET = 0, 1, 2, 3, 4, 5

DEFAULT_PRICES = {"4МН": 35, "ВА": 43}   # серия -> цена; иначе DEFAULT_PRICE
DEFAULT_PRICE = 35


class ProezdWriterError(Exception):
    pass


def price_for(prices, series):
    series = (series or "").strip().upper()
    for prefix, val in prices.items():
        if series.startswith(prefix.upper()):
            return val
    return prices.get("*", DEFAULT_PRICE)


def fmt_money(v):
    rub = int(v)
    kop = int(round((float(v) - rub) * 100))
    return f"{rub},{kop:02d}"


def _find_row(table, predicate):
    for start, row, rep in ob.logical_rows(table):
        cells = ob.logical_cells(row, 0)
        if 0 in cells and predicate(ob.cell_text(cells[0]).strip()):
            return start, row
    return None, None


def generate(template_path, out_path, ctx, rows, keep_open=False):
    """rows — список строк-поездок (dict с ключами num/date/frm/to/purpose/number/
    series/price), уже отредактированных пользователем. Сумма = Σ price."""
    template_path = os.path.abspath(template_path)
    out_path = os.path.abspath(out_path)
    if not os.path.exists(template_path):
        raise ProezdWriterError(f"Не найден шаблон: {template_path}")
    if not rows:
        raise ProezdWriterError("Нет поездок для формирования отчёта.")

    doc = load(template_path)
    sheets = {t.getAttribute("name"): t for t in doc.spreadsheet.getElementsByType(Table)}
    ot = sheets[REPORT_SHEET]
    za = sheets[APPL_SHEET]

    total = sum(float(r.get("price") or 0) for r in rows)

    _write_report(ot, ctx, rows)
    _write_application(za, ctx, total)

    if os.path.exists(out_path):
        os.remove(out_path)
    doc.save(out_path)
    return out_path


def _ticket_str(number, series):
    number = (number or "").strip()
    series = (series or "").strip()
    return f"{number} {series}".strip()


def _write_report(ot, ctx, rows):
    n = len(rows)
    # шапка
    ob.put_row(ob.row_at(ot, 1), {0: f"Ф.И.О. сотрудника {ctx['worker_full']}"})
    if ctx.get("position_line"):
        ob.put_row(ob.row_at(ot, 2), {0: ctx["position_line"]})
    ob.put_row(ob.row_at(ot, 5), {0: f"За {ctx['month_upper']} {ctx['year']}г."})

    # найти прототип строки поездки (первая строка с числовым № в столбце 0
    # после строки-заголовка) и «якорь» подвала («Количество поездок …»)
    cnt_start, cnt_row = _find_row(ot, lambda t: t.startswith("Количество поездок"))
    proto = None
    trip_rows = []
    for start, row, rep in ob.logical_rows(ot):
        if start < 7 or (cnt_start is not None and start >= cnt_start):
            continue
        cells = ob.logical_cells(row, 0)
        txt = ob.cell_text(cells[0]).strip() if 0 in cells else ""
        if txt.isdigit():
            if proto is None:
                proto = ob.clone_row(row)
            trip_rows.append(row)
    if proto is None:
        raise ProezdWriterError("В шаблоне не найдена строка-прототип поездки.")

    for row in trip_rows:
        ob.remove_row(ot, row)

    new_rows = []
    for i, row in enumerate(rows, 1):
        r = ob.clone_row(proto)
        ob.put_row(r, {
            C_NUM: i,
            C_DATE: row.get("date", ""),
            C_FROM: row.get("frm", ""),
            C_TO: row.get("to", ""),
            C_PURPOSE: row.get("purpose", ""),
            C_TICKET: _ticket_str(row.get("number", ""), row.get("series", "")),
        })
        new_rows.append(r)
    ob.insert_rows_before(ot, new_rows, cnt_row)

    # подвал
    ob.put_row(cnt_row, {0: f"Количество поездок всего {int_in_words(n)} ."})
    _, sotr = _find_row(ot, lambda t: t.startswith("Сотрудник"))
    if sotr is not None:
        ob.put_row(sotr, {0: f"Сотрудник_______________/ {ctx['worker_short']}/"})
    _, confirm = _find_row(ot, lambda t: t.startswith("Поездки, указанные"))
    if confirm is not None:
        ob.put_row(confirm, {0: "Поездки, указанные в маршрутном листе подтверждаю:"
                                "___________________   /                    "
                                f"{ctx['zav']}  /"})


def _write_application(za, ctx, total):
    ob.put_row(ob.row_at(za, 1), {0: ctx["director_dative"]})
    ob.put_row(ob.row_at(za, 5), {1: f"отделение СОД №{ctx['dept_no']}"})
    ob.put_row(ob.row_at(za, 6), {1: ctx["worker_genitive"]})
    ob.put_row(ob.row_at(za, 8), {0:
        f"Прошу возместить мне расходы на проезд в служебных целях в сумме "
        f"{fmt_money(total)} ({rubles_kopecks_in_words(total)}) , "
        f"произведенные в {ctx['month_prep']} {ctx['year']} г."})
    ob.put_row(ob.row_at(za, 13), {0: ctx["appl_date"]})
