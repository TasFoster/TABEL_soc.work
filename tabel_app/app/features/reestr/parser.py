"""Чтение входных файлов функции «Реестр» (.xls через xlrd).

Парсер устойчив к разным форматам реестра: колонки определяются по тексту
заголовков (строки-заголовки + подзаголовки), а не по фиксированным номерам.
Поэтому работают и полный формат (с адресом/периодом/кол-вом/«по договору»),
и сокращённый (только ФИО/договор/дата/начислено/соцработник).
"""

import re

import xlrd

from .model import IpsuRecord, RegistryInput, ServiceRecord

_BIRTH_RE = re.compile(r"\s*\d{2}\.\d{2}\.\d{4}\s*г\.?\s*р\.?\s*$")
_CONTRACT_RE = re.compile(r"(\d+\s*-\s*[ЗзЗ]\s*-\s*\d+(?:\s*-\s*[ДдD])?)", re.IGNORECASE)
_PERIOD_RE = re.compile(r"с\s*(\d{2}\.\d{2}\.\d{4})\s*по\s*(\d{2}\.\d{2}\.\d{4})")


def _s(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(v)
    return str(v).strip()


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = _s(v).replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _cell(sheet, r, c):
    """Безопасное чтение ячейки: '' если колонка отсутствует/за границей."""
    if c is None or c < 0 or r < 0 or r >= sheet.nrows or c >= sheet.ncols:
        return ""
    return sheet.cell(r, c).value


def split_fio(full):
    full = _s(full)
    m = _BIRTH_RE.search(full)
    if m:
        birth = re.search(r"\d{2}\.\d{2}\.\d{4}", m.group(0))
        return full[: m.start()].strip(), (birth.group(0) if birth else "")
    return full, ""


def extract_contract(raw):
    raw = _s(raw)
    matches = _CONTRACT_RE.findall(raw)
    if matches:
        return re.sub(r"\s*", "", matches[-1])
    return raw


def _find_period(sheet):
    for r in range(min(sheet.nrows, 12)):
        for c in range(sheet.ncols):
            m = _PERIOD_RE.search(_s(sheet.cell(r, c).value))
            if m:
                return m.group(1), m.group(2)
    return "", ""


def _find_header_row(sheet):
    for r in range(min(sheet.nrows, 15)):
        joined = " ".join(_s(sheet.cell(r, c).value) for c in range(sheet.ncols)).lower()
        if "фио" in joined and ("п/п" in joined or "№" in joined):
            return r
    return 6


def _build_colmap(sheet, hr):
    """Сопоставить поля колонкам по тексту заголовка (строки hr и hr+1)."""
    colmap = {}

    def claim(field, c):
        if field not in colmap:
            colmap[field] = c

    for r in (hr, hr + 1):
        for c in range(sheet.ncols):
            t = _s(sheet.cell(r, c).value).lower()
            if not t:
                continue
            if "п/п" in t:
                claim("id", c)
            if "фио" in t:
                claim("fio", c)
            if "адрес" in t:
                claim("address", c)
            if "период" in t:
                claim("period", c)
            if "кол-во" in t or "количество" in t:
                claim("count", c)
            if ("соцработник" in t or "социальный работник" in t or "оказавш" in t):
                claim("worker", c)
            if "дата" in t and ("заключ" in t or "договор" in t):
                claim("contract_date", c)
            elif "договор" in t and "сумм" not in t:
                claim("contract", c)
            if "по договору" in t:
                claim("po_dogovoru", c)
            if "начислено" in t:
                claim("nachisleno", c)
            if "оплачено" in t:
                claim("oplacheno", c)
    return colmap


def parse_registry(path, kind):
    """Разобрать реестр (kind='gos'|'dop'), определяя колонки по заголовкам."""
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)
    ps, pe = _find_period(sheet)
    hr = _find_header_row(sheet)
    cm = _build_colmap(sheet, hr)

    c_id = cm.get("id", 2)
    c_fio = cm.get("fio", 3)
    c_addr = cm.get("address")
    c_contract = cm.get("contract")
    c_date = cm.get("contract_date")
    c_period = cm.get("period")
    c_count = cm.get("count")
    c_po = cm.get("po_dogovoru")
    c_nach = cm.get("nachisleno")
    c_opl = cm.get("oplacheno")
    c_worker = cm.get("worker")

    reg = RegistryInput(kind=kind, department_name="", period_start=ps, period_end=pe)

    for r in range(hr + 1, sheet.nrows):
        d = _s(_cell(sheet, r, c_fio))
        cid = _s(_cell(sheet, r, c_id))
        if not d and not cid:
            continue
        if "Отделение" in d or "Филиал" in d:
            reg.department_name = d
            reg.subtotal_count = _num(_cell(sheet, r, c_count))
            reg.subtotal_po_dogovoru = _num(_cell(sheet, r, c_po))
            reg.subtotal_nachisleno = _num(_cell(sheet, r, c_nach))
            reg.subtotal_oplacheno = _num(_cell(sheet, r, c_opl))
            continue
        if not d:
            continue
        contract_raw = _s(_cell(sheet, r, c_contract))
        contract = extract_contract(contract_raw)
        worker = _s(_cell(sheet, r, c_worker))
        nachisleno = _num(_cell(sheet, r, c_nach))
        count = _num(_cell(sheet, r, c_count))
        # Пропустить строки, не являющиеся записями об услуге (подписи/футер):
        # нет ни договора, ни работника, ни суммы, ни кол-ва.
        if not contract and not worker and nachisleno == 0 and count == 0:
            continue
        fio, birth = split_fio(d)
        # «по договору» может отсутствовать (сокращённый формат) — берём начислено.
        po = _num(_cell(sheet, r, c_po)) if c_po is not None else nachisleno
        reg.records.append(ServiceRecord(
            client_id=cid,
            fio=fio,
            fio_full=d,
            birth=birth,
            address=_s(_cell(sheet, r, c_addr)),
            contract_raw=contract_raw,
            contract=contract,
            contract_date=_s(_cell(sheet, r, c_date)),
            period=_s(_cell(sheet, r, c_period)),
            count=count,
            po_dogovoru=po,
            nachisleno=nachisleno,
            oplacheno=_num(_cell(sheet, r, c_opl)),
            worker=worker,
        ))
    return reg


def parse_ipsu(path):
    """Разобрать отчёт ИПСУ. Колонки определяются по заголовкам."""
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)
    hr = 6
    for r in range(min(sheet.nrows, 15)):
        joined = " ".join(_s(sheet.cell(r, c).value) for c in range(sheet.ncols))
        if "Срок предоставления" in joined or "ФИО" in joined:
            hr = r
            break

    # карта колонок ИПСУ
    cmap = {}
    for c in range(sheet.ncols):
        t = _s(sheet.cell(hr, c).value).lower()
        if "фио" in t and "fio" not in cmap:
            cmap["fio"] = c
        elif "дата рожд" in t:
            cmap["birth"] = c
        elif "адрес" in t:
            cmap["address"] = c
        elif "дата выдачи" in t:
            cmap["issue"] = c
        elif "№ ипсу" in t or "номер ипсу" in t:
            cmap["num"] = c
        elif "срок" in t:
            cmap["srok"] = c
    c_fio = cmap.get("fio", 2)
    c_id = c_fio - 1 if c_fio >= 1 else 1  # ID обычно в колонке слева от ФИО

    out = []
    for r in range(hr + 1, sheet.nrows):
        fio = _s(_cell(sheet, r, c_fio))
        cid = _s(_cell(sheet, r, c_id))
        if not cid or not fio:
            continue
        out.append(IpsuRecord(
            client_id=cid,
            fio=fio,
            birth=_s(_cell(sheet, r, cmap.get("birth", 3))),
            address=_s(_cell(sheet, r, cmap.get("address", 4))),
            issue_date=_s(_cell(sheet, r, cmap.get("issue", 5))),
            ipsu_num=_s(_cell(sheet, r, cmap.get("num", 6))),
            srok=_s(_cell(sheet, r, cmap.get("srok", 7))),
        ))
    return out
