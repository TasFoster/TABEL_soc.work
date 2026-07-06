"""Чтение поездок из файла соцработника и (best-effort) распознавание билетов.

* read_trips(.ods) — берёт поездки (дата/откуда/куда/цель) из файла вида образца.
* ocr_tickets(.jpg) — пытается распознать билеты со скана (Windows OCR, офлайн).
  Распознавание этих цветных/повёрнутых билетов НЕнадёжно, поэтому результат —
  лишь предзаполнение: номер/серию/цену пользователь сверяет и правит вручную.
"""

import re

from odf.opendocument import load
from odf.style import Style, TableCellProperties
from odf.table import Table

from ..reestr import ods_build as ob


def _report_sheet(doc):
    tables = doc.spreadsheet.getElementsByType(Table)
    for t in tables:
        nm = (t.getAttribute("name") or "").lower()
        if "отчет" in nm or "проезд" in nm:
            return t
    return tables[0]


def _bg_map(doc):
    """Карта: имя стиля ячейки -> цвет фона (#RRGGBB) из стилей документа."""
    m = {}
    for cont in (doc.automaticstyles, doc.styles):
        for st in cont.getElementsByType(Style):
            name = st.getAttribute("name")
            for tcp in st.getElementsByType(TableCellProperties):
                bg = tcp.getAttribute("backgroundcolor")
                if bg:
                    m[name] = bg
    return m


def _is_cyan(hexcolor):
    """Голубой (cyan) фон — пометка ДОПОЛНИТЕЛЬНОЙ поездки в отчёте."""
    if not hexcolor or not hexcolor.startswith("#") or len(hexcolor) < 7:
        return False
    try:
        r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        return False
    return g >= 200 and b >= 200 and r <= g - 60 and r <= b - 60


def _row_is_dop(cells, bg):
    """Строка-поездка — доп, если фон её ячеек (1..4) голубой."""
    for ci in (1, 2, 3, 4):
        cell = cells.get(ci)
        if cell is None:
            continue
        if _is_cyan(bg.get(cell.getAttribute("stylename"))):
            return True
    return False


def read_trips(ods_path):
    """Вернуть (trips, header). trips — список {date, frm, to, purpose, dop}.

    dop=True у дополнительных поездок (помечены голубым в исходном файле) — нужно для
    группировки строк по дням при простановке дат (см. service.assign_dates)."""
    doc = load(ods_path)
    t = _report_sheet(doc)
    bg = _bg_map(doc)
    trips, header = [], {}
    for start, row, rep in ob.logical_rows(t):
        cells = ob.logical_cells(row, 5)

        def cv(c):
            return ob.cell_text(cells[c]).strip() if c in cells else ""

        c0 = cv(0)
        if c0.isdigit() and start >= 6:
            trips.append({"date": cv(1), "frm": cv(2), "to": cv(3), "purpose": cv(4),
                          "dop": _row_is_dop(cells, bg)})
        elif "Ф.И.О" in c0:
            header["worker_full"] = re.sub(r"^.*сотрудника", "", c0).strip()
        elif c0.startswith("Наименование должности"):
            header["position_line"] = c0
        else:
            m = re.search(r"За\s+(.+?)\s+(\d{4})", c0)
            if m:
                header["month_upper"], header["year"] = m.group(1).strip(), m.group(2)
    return trips, header


def read_tickets(ods_path):
    """Существующие билеты из столбца «Номер и серия» -> [(номер, серия)]."""
    doc = load(ods_path)
    t = _report_sheet(doc)
    out = []
    for start, row, rep in ob.logical_rows(t):
        cells = ob.logical_cells(row, 5)
        c0 = ob.cell_text(cells[0]).strip() if 0 in cells else ""
        if c0.isdigit() and start >= 6:
            raw = ob.cell_text(cells[5]).strip() if 5 in cells else ""
            m = re.match(r"\s*(\d+)\s*(.*)$", raw)
            out.append((m.group(1), m.group(2).strip()) if m else (raw, ""))
    return out


# --------------------------------------------------------------- OCR (best-effort)
# Серия билета («4МН-571», «ВА-996») печатается обычным шрифтом и распознаётся
# надёжно; по серии однозначно определяется цена. НОМЕР билета напечатан
# матричным (точечным) шрифтом — его офлайн-OCR не берёт, поэтому номер —
# лишь попытка, его сотрудник вписывает/сверяет вручную по скану.

_INN_PARTS = ("6432028036", "6451405201")           # ИНН перевозчиков — не номер
_SERIES_RE = re.compile(r"(\d?\s*[А-ЯA-Zа-я]{1,3}\s*[-–—]\s*\d{3})")
_NUM_RE = re.compile(r"\d{5,7}")


def ocr_available():
    try:
        import winrt.windows.media.ocr  # noqa: F401
        import cv2  # noqa: F401
        return True
    except Exception:
        return False


def ocr_tickets(image_path):
    """Распознать билеты со скана -> список (номер, серия) в порядке чтения.

    Серия — надёжно; номер — best-effort (часто пусто из-за матричного шрифта).
    Цену вычисляет вызывающий по серии. [] если OCR недоступен."""
    try:
        return _ocr_tickets_impl(image_path)
    except Exception:
        return []


def _norm_series(s):
    s = re.sub(r"[\s.]", "", s).upper().replace("–", "-").replace("—", "-")
    s = s.replace("MH", "МН").replace("BA", "ВА").replace("BБ", "ВБ")
    return s


def _parse_ticket(text):
    t = text.replace("\n", " ")
    ser = _SERIES_RE.search(t)
    series = _norm_series(ser.group(1)) if ser else ""
    nums = [m for m in _NUM_RE.findall(t)
            if not any(m in inn for inn in _INN_PARTS)]
    number = nums[0] if nums else ""
    kw = sum(k in t.upper() for k in ("АВТОБУС", "РУБ", "СЕРИЯ", "БИЛЕТ"))
    return number, series, kw


def _ocr_tickets_impl(image_path):
    import asyncio
    import os
    import tempfile

    import cv2
    import numpy as np
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage import FileAccessMode, StorageFile

    eng = OcrEngine.try_create_from_user_profile_languages()
    if eng is None:
        return []

    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []
    boxes = _segment_tickets(img, cv2, np)
    tmp = os.path.join(tempfile.gettempdir(), "_proezd_ocr.png")

    async def ocr_png(path):
        f = await StorageFile.get_file_from_path_async(path)
        s = await f.open_async(FileAccessMode.READ)
        dec = await BitmapDecoder.create_async(s)
        bmp = await dec.get_software_bitmap_async()
        return (await eng.recognize_async(bmp)).text

    out = []
    for (x, y, w, h) in boxes:
        crop = img[y:y + h, x:x + w]
        best = ("", "", -1)
        rotations = [None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE]
        for code in rotations:
            c = crop if code is None else cv2.rotate(crop, code)
            big = cv2.resize(c, (c.shape[1] * 2, c.shape[0] * 2))
            cv2.imwrite(tmp, _binarize(big, cv2, np))
            num, ser, kw = _parse_ticket(asyncio.run(ocr_png(tmp)))
            score = kw + (2 if ser else 0) + (1 if num else 0)
            cur = best[2] + (2 if best[1] else 0) + (1 if best[0] else 0)
            if score > cur:
                best = (num, ser, score)
        if best[1] or best[0]:
            out.append((best[0], best[1]))
    try:
        os.remove(tmp)
    except OSError:
        pass
    return out


def _binarize(crop, cv2, np):
    b, g, r = cv2.split(crop.astype(np.int16))
    ink = (255 - np.minimum(np.minimum(b, g), r)).astype(np.uint8)
    _, bw = cv2.threshold(ink, 40, 255, cv2.THRESH_BINARY)
    return 255 - bw


def _segment_tickets(img, cv2, np):
    """Найти отдельные билеты (по цветным рамкам) -> боксы в порядке чтения."""
    H, W = img.shape[:2]
    b, g, r = cv2.split(img.astype(np.int16))
    ink = (255 - np.minimum(np.minimum(b, g), r)).astype(np.uint8)
    mask = (ink > 45).astype(np.uint8) * 255
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25)))
    closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(closed, 8)
    area = W * H
    boxes = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if 0.004 * area < a < 0.06 * area and 0.25 < w / h < 4.0:
            boxes.append((int(x), int(y), int(w), int(h)))
    rowh = max((h for _, _, _, h in boxes), default=300)
    boxes.sort(key=lambda bx: (round(bx[1] / (rowh * 0.7)), bx[0]))
    return boxes
