"""Запись .xls без Microsoft Excel (на базе xlwt).

Содержит то, чего не хватает «голому» xlwt для верстки наших документов:

* ``ColourPalette`` — распределитель произвольных RGB-цветов по пользовательским
  слотам палитры .xls (xlwt по умолчанию умеет лишь 8 «именованных» цветов).
* мелкие помощники сборки стилей (границы, сплошная заливка, ширина колонки).
* ``TemplateStyles`` — перенос оформления из .xls-шаблона (через ``xlrd`` с
  ``formatting_info=True``) в стили xlwt, чтобы размножать строки-прототипы
  с сохранением вида (шрифт, выравнивание, границы, заливка, числовой формат).

Используется писателями «Табеля» и «Приложения к табелю».
"""

import xlwt


# --- Перевод ширины столбца Excel (в «символах») в единицы xlwt (1/256 символа).
def col_width(chars):
    """Ширина столбца Excel (в «символах») -> единицы ширины xlwt (1/256 символа).

    Excel хранит ширину с поправкой на отступы ячейки (~5 px при ширине цифры 7 px
    для Calibri 11), поэтому видимым N символам соответствует (N + 5/7) * 256.
    """
    return int(round((chars + 0.714) * 256))


def row_height(points):
    """Высота строки в пунктах -> твипы (1/20 пункта), как ждёт xlwt."""
    return int(round(points * 20))


class ColourPalette:
    """Сопоставляет (r, g, b) -> индекс палитры .xls.

    Палитра .xls — это 64 слота; пользовательские (8..63) можно переопределить
    на любой RGB. Мы раздаём их по порядку начиная с 0x20, чтобы не задеть
    стандартные низкие индексы (чёрный/белый/основные цвета), на которые могут
    ссылаться границы и шрифты по умолчанию.
    """

    FIRST_SLOT = 0x20  # 32
    LAST_SLOT = 0x3F   # 63

    def __init__(self, book):
        self._book = book
        self._by_rgb = {}
        self._next = self.FIRST_SLOT

    def index(self, rgb):
        """Вернуть индекс палитры для RGB-кортежа; None -> None (авто/без цвета)."""
        if rgb is None:
            return None
        rgb = (int(rgb[0]) & 255, int(rgb[1]) & 255, int(rgb[2]) & 255)
        got = self._by_rgb.get(rgb)
        if got is not None:
            return got
        if self._next > self.LAST_SLOT:
            return self._nearest(rgb)
        idx = self._next
        self._next += 1
        self._book.set_colour_RGB(idx, *rgb)
        self._by_rgb[rgb] = idx
        return idx

    def index_hex(self, value):
        """RGB из целого 0xRRGGBB."""
        return self.index(((value >> 16) & 255, (value >> 8) & 255, value & 255))

    def _nearest(self, rgb):
        best, bd = None, None
        for known, idx in self._by_rgb.items():
            d = sum((a - b) ** 2 for a, b in zip(known, rgb))
            if bd is None or d < bd:
                best, bd = idx, d
        return best


def thin_borders(colour=None):
    """Стиль с тонкими границами со всех сторон."""
    b = xlwt.Borders()
    b.left = b.right = b.top = b.bottom = xlwt.Borders.THIN
    if colour is not None:
        b.left_colour = b.right_colour = b.top_colour = b.bottom_colour = colour
    return b


def solid_fill(colour_index):
    """Сплошная заливка указанным цветом палитры."""
    p = xlwt.Pattern()
    p.pattern = xlwt.Pattern.SOLID_PATTERN
    p.pattern_fore_colour = colour_index
    return p


class TemplateStyles:
    """Перенос оформления из .xls-шаблона (xlrd) в стили xlwt.

    Параметры:
        rb — книга xlrd, открытая с ``formatting_info=True``;
        wb — целевая книга xlwt;
        palette — ``ColourPalette`` над этой же книгой.

    ``xfstyle(idx)`` отдаёт (с кешем) готовый ``xlwt.XFStyle`` для XF-индекса
    исходной книги. ``cell_style(sheet, r, c)`` — то же по координате ячейки.
    """

    def __init__(self, rb, wb, palette):
        self.rb = rb
        self.wb = wb
        self.pal = palette
        self._cache = {}

    # --- цвета ---
    def _colour(self, idx):
        rgb = self.rb.colour_map.get(idx)
        return self.pal.index(rgb) if rgb else None

    # --- XF -> XFStyle ---
    def xfstyle(self, xf_index):
        st = self._cache.get(xf_index)
        if st is None:
            st = self._translate(xf_index)
            self._cache[xf_index] = st
        return st

    def cell_style(self, sheet, r, c):
        return self.xfstyle(sheet.cell_xf_index(r, c))

    def _translate(self, xf_index):
        xf = self.rb.xf_list[xf_index]
        st = xlwt.XFStyle()

        fmt = self.rb.format_map.get(xf.format_key)
        if fmt is not None and fmt.format_str:
            st.num_format_str = fmt.format_str

        rf = self.rb.font_list[xf.font_index]
        wf = xlwt.Font()
        wf.name = rf.name or "Arial"
        wf.height = rf.height or 200
        wf.bold = bool(getattr(rf, "bold", 0)) or getattr(rf, "weight", 400) >= 700
        wf.italic = bool(rf.italic)
        wf.underline = bool(getattr(rf, "underline_type", 0) or getattr(rf, "underlined", 0))
        wf.struck_out = bool(getattr(rf, "struck_out", 0))
        fc = self._colour(rf.colour_index)
        if fc is not None:
            wf.colour_index = fc
        st.font = wf

        al = xlwt.Alignment()
        a = xf.alignment
        al.horz = a.hor_align
        al.vert = a.vert_align
        al.wrap = a.text_wrapped
        rot = getattr(a, "rotation", 0) or 0
        if 0 <= rot <= 90:
            al.rota = rot
        elif 91 <= rot <= 180:           # xlrd: 91..180 -> по часовой 1..90
            al.rota = 90 - rot           # xlwt: отрицательные = по часовой
        st.alignment = al

        bd = xlwt.Borders()
        bo = xf.border
        bd.left = bo.left_line_style
        bd.right = bo.right_line_style
        bd.top = bo.top_line_style
        bd.bottom = bo.bottom_line_style
        for side, cidx in (("left", bo.left_colour_index), ("right", bo.right_colour_index),
                           ("top", bo.top_colour_index), ("bottom", bo.bottom_colour_index)):
            c = self._colour(cidx)
            if c is not None:
                setattr(bd, side + "_colour", c)
        st.borders = bd

        bg = xf.background
        if bg.fill_pattern == 1:  # сплошная заливка
            fc = self._colour(bg.pattern_colour_index)
            if fc is not None:
                st.pattern = solid_fill(fc)

        return st

    # --- доступ к геометрии шаблона ---
    def clone_style(self, st):
        """Глубокая копия XFStyle (чтобы менять заливку, не трогая кеш)."""
        import copy
        return copy.deepcopy(st)
