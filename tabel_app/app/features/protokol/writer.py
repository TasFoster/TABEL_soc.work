"""Формирование протокола рабочего совещания (.odt) БЕЗ Word — через odfpy.

Вёрстка повторяет образец (`протокол/Протоколы/…`): Times New Roman 14pt,
заголовок и подзаголовок по центру (жирные), «Присутствовали:» и тело — слева,
подпись «Зав.отделением №N            Фамилия И.О.» в конце.
"""

from odf.opendocument import OpenDocumentText
from odf.style import (FontFace, ParagraphProperties, Style, TextProperties)
from odf.text import P, S

FONT = "Times New Roman"
SIZE = "14pt"


class ProtokolWriterError(Exception):
    pass


def _styles(doc):
    """Зарегистрировать и вернуть именованные стили абзацев."""
    doc.fontfacedecls.addElement(FontFace(name=FONT, fontfamily=FONT))

    def mk(name, align, bold=False):
        st = Style(name=name, family="paragraph")
        st.addElement(ParagraphProperties(textalign=align))
        tp = {"fontname": FONT, "fontsize": SIZE,
              "fontsizeasian": SIZE, "fontsizecomplex": SIZE,
              "fontnameasian": FONT, "fontnamecomplex": FONT}
        if bold:
            tp.update(fontweight="bold", fontweightasian="bold",
                      fontweightcomplex="bold")
        st.addElement(TextProperties(**tp))
        doc.styles.addElement(st)
        return st

    return {
        "title": mk("ProtTitle", "center", bold=True),
        "left": mk("ProtLeft", "start"),
    }


def _add_p(doc, style, text=""):
    """Добавить абзац; повторяющиеся пробелы кодируются <text:s> (ODT иначе схлопывает)."""
    p = P(stylename=style)
    if text:
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == " ":
                j = i
                while j < len(text) and text[j] == " ":
                    j += 1
                n = j - i
                if n == 1:
                    p.addText(" ")
                else:
                    p.addElement(S(c=n))
                i = j
            else:
                j = i
                while j < len(text) and text[j] != " ":
                    j += 1
                p.addText(text[i:j])
                i = j
    doc.text.addElement(p)
    return p


def generate(out_path, ctx, attendees, body, absentees=None):
    """ctx: number, date, dept_no, zav. attendees/absentees: списки ФИО. body: текст повестки."""
    doc = OpenDocumentText()
    st = _styles(doc)

    n = ctx.get("number", "")
    dept_no = ctx.get("dept_no", "")
    date = ctx.get("date", "")
    zav = ctx.get("zav", "")

    _add_p(doc, st["title"], f"Протокол № {n}")
    _add_p(doc, st["title"],
           f"рабочего совещания отделения социального обслуживания "
           f"на дому № {dept_no} от {date}")
    _add_p(doc, st["left"])

    _add_p(doc, st["left"], "Присутствовали:")
    for fio in attendees:
        _add_p(doc, st["left"], str(fio).strip())
    _add_p(doc, st["left"])

    if absentees:
        _add_p(doc, st["left"], "Отсутствовали:")
        for fio in absentees:
            _add_p(doc, st["left"], str(fio).strip())
        _add_p(doc, st["left"])

    # Тело (повестка / решения / Разное) — построчно, как введено пользователем.
    for line in body.split("\n"):
        _add_p(doc, st["left"], line.rstrip())

    _add_p(doc, st["left"])
    _add_p(doc, st["left"], f"Зав.отделением №{dept_no}" + " " * 37 + zav)

    doc.save(out_path)
    return out_path
