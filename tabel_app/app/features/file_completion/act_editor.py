"""Обновление месячного акта и проверка фактической разбивки на страницы."""
import calendar
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from docx import Document
from docx.shared import Mm
from pypdf import PdfReader
from ..timesheet.calendar_ru import MONTHS_NOM
from .names import recipient
from . import rtf

GEN = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()


def month_end(day):
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def signing_day(day, production):
    end = month_end(day)
    while end.month == day.month:
        if production.is_workday(end):
            return end
        end -= timedelta(days=1)
    raise ValueError("В календаре месяца отсутствуют рабочие дни.")


class ConversionError(ValueError):
    """Сбой внешнего преобразователя документов."""


def convert(source, folder, extension):
    office = shutil.which("soffice")
    if not office:
        for var in ("ProgramFiles", "ProgramFiles(x86)"):
            candidate = Path(os.environ.get(var, "")) / "LibreOffice/program/soffice.com"
            if candidate.is_file():
                office = str(candidate)
                break
    target = folder / (source.stem + "." + extension)
    if target.exists():
        target.unlink()
    if office:
        cmd = [office, "-env:UserInstallation=" + (folder / "profile").as_uri(),
               "--headless", "--convert-to", extension, "--outdir", str(folder), str(source)]
        env = None
    elif os.name == "nt":
        env = dict(os.environ, ACT_SOURCE=str(source), ACT_TARGET=str(target),
                   ACT_FORMAT="17" if extension == "pdf" else "16")
        script = """$ErrorActionPreference='Stop'
        $w=New-Object -ComObject Word.Application
        try {
            $w.AutomationSecurity=3
            $w.DisplayAlerts=0
            $d=$w.Documents.Open($env:ACT_SOURCE,$false,$true,$false)
            try {$d.SaveAs2($env:ACT_TARGET,[int]$env:ACT_FORMAT)} finally {$d.Close(0)}
        } finally {$w.Quit()}"""
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    else:
        raise ConversionError("Для преобразования и проверки страниц установите LibreOffice или Word.")
    try:
        subprocess.run(cmd, check=True, timeout=120, env=env, capture_output=True)
    except (subprocess.SubprocessError, OSError) as exc:
        raise ConversionError("Не удалось обработать документ через Word или LibreOffice.") from exc
    if not target.is_file():
        raise ConversionError("Офисный редактор не смог преобразовать документ.")
    return target


def replace_match(paragraph, match, replacement):
    start, end = match.span(1)
    offset = 0
    for run in paragraph.runs:
        value = run.text
        limit = offset + len(value)
        if offset < end and limit > start:
            left = value[:max(0, start-offset)]
            right = value[max(0, end-offset):]
            run.text = left + (replacement if offset <= start else "") + right
        offset = limit


def field_rules(month, signed, worker, director):
    dates = f"{month.replace(day=1):%d.%m.%Y} - {month_end(month):%d.%m.%Y}"
    rules = [
        (r"\bза\s+([а-яё]+\s+\d{4})(?=\s*г)", MONTHS_NOM[month.month].lower()+f" {month.year}"),
        (r"(\d{2}\.\d{2}\.\d{4}\s*[-–—]\s*\d{2}\.\d{2}\.\d{4})", dates),
        (r"^\s*([«\"]\d{1,2}[»\"]\s+[а-яё]+\s+\d{4})(?=\s*г)", f"«{signed.day}» {GEN[signed.month-1]} {signed.year}"),
        (r"^\s*(Директор(?:\s+филиала)?\s+_+\s*\([^)]*\))", f"Директор филиала _________________________ ({director})"),
    ]
    if worker:
        rules.append((r"Социальный работник\s+_+\s*\(([^)]*)\)", worker))
    return rules


def save_act(folder, client, extension, content):
    serial = 1
    while True:
        suffix = "" if serial == 1 else f"_{serial}"
        target = folder / f"{client}_акт{suffix}{extension}"
        try:
            output = target.open("xb")
        except FileExistsError:
            serial += 1
            continue
        with output:
            output.write(content)
        return target



def act_recipient(text):
    if not re.search(r"Акт\s+сдачи\s*[-–—‑]\s*при[её]мки", text, re.I):
        raise ValueError("Не найден заголовок акта сдачи-приёмки.")
    client = recipient(text)
    if not client:
        raise ValueError("Акт распознан. Проверьте ФИО в поле получателя услуг или заказчика.")
    return client


def prepare(source, folder, month, signed, worker, director):
    try:
        return prepare_docx(source, folder, month, signed, worker, director)
    except ConversionError:
        if source.suffix.lower() != ".rtf":
            raise
    raw = source.read_bytes()
    text, spans = rtf.parse(raw)
    client = act_recipient(text)
    for pattern, value in field_rules(month, signed, worker, director):
        matches = list(re.finditer(pattern, text, re.I | re.M))
        if not matches:
            raise ValueError("Не найдено поле для замены: " + value)
        for match in reversed(matches):
            raw = rtf.replace(raw, *match.span(1), value, (text, spans))
        text, spans = rtf.parse(raw)
    return save_act(folder, client, ".rtf", raw)


def prepare_docx(source, folder, month, signed, worker, director):
    from docx.text.paragraph import Paragraph
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        path = convert(source, temp, "docx") if source.suffix.lower() in (".doc", ".rtf") else source
        doc = Document(path)
        paragraphs = [Paragraph(node, doc) for node in doc.element.body.xpath(".//w:p")]
        text = "\n".join(p.text for p in paragraphs)
        client = act_recipient(text)
        rules = field_rules(month, signed, worker, director)
        for pattern, value in rules:
            hits = 0
            for p in paragraphs:
                for match in reversed(list(re.finditer(pattern, p.text, re.I))):
                    replace_match(p, match, value)
                    hits += 1
            if not hits:
                raise ValueError("Не найдено поле для замены: " + value)
        for section in doc.sections:
            section.page_width, section.page_height = Mm(210), Mm(297)
        draft = temp / "edited.docx"
        for margin in (None, 15, 10, 7):
            if margin:
                for section in doc.sections:
                    for side in ("left_margin","right_margin","top_margin","bottom_margin"):
                        setattr(section, side, min(getattr(section, side) or Mm(margin), Mm(margin)))
            doc.save(draft)
            pdf = convert(draft, temp, "pdf")
            if len(PdfReader(pdf).pages) == 1:
                break
        else:
            raise ValueError("Акт занимает больше одной страницы A4 даже с полями 7 мм.")
        return save_act(folder, client, ".docx", draft.read_bytes())
