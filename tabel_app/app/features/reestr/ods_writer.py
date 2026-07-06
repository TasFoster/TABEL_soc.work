"""Запись итогового реестра в .ods по шаблону БЕЗ Excel (через odfpy).

Стратегия: в шаблоне для каждого листа оставлены строки-прототипы (метка
работника, имя, строка клиента, «Д.», «Итого», «Всего»). Писатель клонирует
эти прототипы нужное число раз, заполняет значения и вставляет перед «хвостом»
листа (подпись зав. отделением + статичные строки), сохраняя всё оформление.

Microsoft Excel НЕ требуется.
"""

import os

from odf.opendocument import load

from . import ods_build as ob

MONTHS_PREP = ["", "январе", "феврале", "марте", "апреле", "мае", "июне",
               "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]

# Имена листов в шаблоне
SHEET_GOS = "Гос_"
SHEET_DOP = "Доп"
SHEET_DENGI = "деньги"
SHEET_PERESMOTR = "пересмотр"


def fmt_amount(v):
    v = round(float(v) + 1e-9, 2)
    return str(int(v)) if v == int(v) else f"{v:.2f}".replace(".", ",")


def _month_year_from_period(period_start):
    try:
        _, mm, yy = period_start.split(".")
        return MONTHS_PREP[int(mm)], yy
    except Exception:
        return "", ""


class OdsWriterError(Exception):
    pass


def _sheets(doc):
    from odf.table import Table
    return {t.getAttribute("name"): t for t in doc.spreadsheet.getElementsByType(Table)}


def _stamper(table, proto_first, proto_count):
    """Клонировать строки-прототипы, вырезать их, вернуть штамповщик.

    stamp(idx, values=None) — вставить копию прототипа idx (с заполнением
    values={столбец: значение}) перед «хвостом» листа; вернуть строку.
    anchor — первая строка хвоста (обычно строка подписи зав. отделением).
    """
    protos = [ob.row_at(table, proto_first + i) for i in range(proto_count)]
    templates = [ob.clone_row(e) for e in protos]
    anchor = ob.row_at(table, proto_first + proto_count)
    for e in protos:
        ob.remove_row(table, e)

    def stamp(idx, values=None):
        row = ob.clone_row(templates[idx])
        if values:
            ob.put_row(row, values)
        table.insertBefore(row, anchor)
        return row

    return stamp, anchor


def _set_header(table, row, col, text):
    ob.put_row(ob.row_at(table, row), {col: text})


def generate(template_path, out_path, data, dept_number, signatures, sheets=("gos",),
             keep_open=False):
    template_path = os.path.abspath(template_path)
    out_path = os.path.abspath(out_path)
    if not os.path.exists(template_path):
        raise OdsWriterError(f"Не найден шаблон: {template_path}")

    doc = load(template_path)
    sh = _sheets(doc)

    if "gos" in sheets:
        _write_gos(sh[SHEET_GOS], data, dept_number, signatures)
    if "dop" in sheets:
        _write_dop(sh[SHEET_DOP], data, dept_number, signatures)
    if "dengi" in sheets:
        _write_dengi(sh[SHEET_DENGI], data)
    if "peresmotr" in sheets:
        _write_peresmotr(sh[SHEET_PERESMOTR], data)

    if os.path.exists(out_path):
        os.remove(out_path)
    doc.save(out_path)
    return out_path


def _zav_line(dept_number, sig):
    return (f"Зав. отделением ОСОД № {dept_number}   _______________________"
            f"{sig.get('zav_fio', '')}")


# --------------------------------------------------------------- Гос_
# Прототипы L20-26: 0=метка,1=имя,2=клиент,3=Д.,4=Итого,5=Всего,6=сумма письма.
# Данные клиента — в логических столбцах 1..8 (B..I).

def _write_gos(table, data, dept_number, sig):
    month, year = _month_year_from_period(data["period_start"])
    total = data["gos_total"]
    _set_header(table, 16, 1,
                f"    Предоставляем денежные средства в объеме {fmt_amount(total)} "
                f"({data['gos_total_words']}) для оплаты в кассу учреждения "
                f"государственных услуг, оказанных филиалом в {month} {year} г. "
                f"в соответствии  с заключенными  договорами.")
    _set_header(table, 17, 3, f"Отделение СОД №{dept_number}")

    stamp, anchor = _stamper(table, 20, 7)
    for w in data["worker_order"]:
        block = data["gos_by_worker"].get(w)
        if not block or (not block["gos"] and not block["dop_only"]):
            continue
        stamp(0)                       # метка
        stamp(1, {1: w})               # имя

        clients = block["gos"]
        for i, c in enumerate(clients, 1):
            e = "бесплатно" if c["free"] else round(c["po_dogovoru"], 2)
            f = "бесплатно" if c["free"] else round(c["k_oplate"], 2)
            stamp(2, {1: i, 2: c["fio"], 3: c["contract"], 4: e, 5: f,
                      6: "пересмотр" if c.get("peresmotr") else None,
                      7: round(c["dop_sum"], 2) if c.get("dop_sum") else None})

        for c in block["dop_only"]:
            stamp(3, {1: "Д.", 2: c["fio"], 3: None, 7: round(c["dop_sum"], 2)})

        t = data["worker_totals"][w]
        po = round(sum(c["po_dogovoru"] for c in clients if not c["free"]), 2)
        stamp(4, {1: "Итого:", 4: po, 5: t["k_oplate"], 7: t["dop"], 8: t["itogo"]})

    sum_po = round(sum(t["po_dogovoru"] for t in data["worker_totals"].values()), 2)
    sum_dop = round(sum(t["dop"] for t in data["worker_totals"].values()), 2)
    stamp(5, {1: "Всего:", 4: sum_po, 5: total, 7: sum_dop, 8: round(total + sum_dop, 2)})
    stamp(6, {5: total})

    ob.put_row(anchor, {1: _zav_line(dept_number, sig)})


# --------------------------------------------------------------- Доп
# Прототипы L23-24: 0=клиент, 1=ИТОГО. Данные клиента — столбцы 1..10 (B..K).

def _write_dop(table, data, dept_number, sig):
    month, year = _month_year_from_period(data["period_start"])
    total = data["dop_total"]
    _set_header(table, 19, 1,
                f"Предоставляем денежные средства в объеме {fmt_amount(total)} "
                f"({data['dop_total_words']}) для оплаты в кассу учреждения "
                f"дополнительных услуг, оказанных филиалом в {month} {year} г. "
                f"в соответствии с заключенными  договорами.")
    _set_header(table, 20, 1, f" ОСОД №  {dept_number}")

    stamp, anchor = _stamper(table, 23, 2)
    for i, c in enumerate(data["dop_rows"], 1):
        s = round(c["summa"], 2)
        mark = "новый" if c.get("new") else ("пересмотр" if c.get("peresmotr") else None)
        stamp(0, {1: i, 2: c["fio_full"], 3: c["contract_raw"], 4: c["date"],
                  5: s, 6: s, 7: "Без НДС", 8: 0, 9: s, 10: mark})
    stamp(1, {1: "ИТОГО:", 5: round(total, 2), 6: round(total, 2), 9: round(total, 2)})

    ob.put_row(anchor, {1: _zav_line(dept_number, sig)})


# --------------------------------------------------------------- деньги
# Прототипы L0-4: 0=метка,1=имя,2=клиент,3=Д.,4=Итого. Данные — столбцы 0..2 (A..C).

def _write_dengi(table, data):
    stamp, anchor = _stamper(table, 0, 5)
    for w in data["worker_order"]:
        block = data["gos_by_worker"].get(w)
        if not block or (not block["gos"] and not block["dop_only"]):
            continue
        stamp(0)
        stamp(1, {0: w})
        for i, c in enumerate(block["gos"], 1):
            stamp(2, {0: i, 1: c["fio"], 2: None})
        for c in block["dop_only"]:
            stamp(3, {0: "Д.", 1: c["fio"], 2: None})
        t = data["worker_totals"][w]
        stamp(4, {0: "Итого:", 2: t["itogo"]})


# --------------------------------------------------------------- пересмотр
# Прототипы L0-2: 0=метка,1=имя,2=клиент. Данные клиента — столбцы 0..6 (A..G).

def _write_peresmotr(table, data):
    stamp, anchor = _stamper(table, 0, 3)
    for w in data["worker_order"]:
        rows = data["peresmotr_by_worker"].get(w, [])
        if not rows:
            continue
        stamp(0)
        stamp(1, {0: w})
        for i, c in enumerate(rows, 1):
            stamp(2, {0: i, 1: c["fio"], 2: c["birth"], 3: c["address"],
                      4: c["issue_date"], 5: c["ipsu_num"], 6: c["srok"]})
