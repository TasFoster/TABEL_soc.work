"""Экспорт видимой части маршрутного листа и заявления в Excel."""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from odf.style import DefaultStyle, MasterPage, PageLayout, Style
from odf.table import TableColumn
from odf.teletype import extractText
from odf.text import P

from ..reestr import ods_build as ob


def _properties(style):
    return {
        name: value
        for child in style.childNodes
        if child.nodeType == 1 and child.qname[1].endswith("-properties")
        for (_, name), value in child.attributes.items()
    }


def _apply_cell_style(cell, props):
    horizontal = {"start": "left", "end": "right", "justify": "left"}
    vertical = {"middle": "center", "top": "top", "bottom": "bottom"}
    alignment = props.get("text-align")
    cell.alignment = Alignment(
        horizontal=horizontal.get(alignment, alignment),
        vertical=vertical.get(props.get("vertical-align"), "center"),
        wrap_text=props.get("wrap-option") == "wrap",
    )
    cell.font = Font(
        name=props.get("font-name", "Arial"),
        size=float(props.get("font-size", "11pt").removesuffix("pt")),
        bold=props.get("font-weight") == "bold",
    )
    borders = {
        side: Side(style="thin", color="000000")
        for side in ("top", "bottom", "left", "right")
        if props.get(f"border-{side}", props.get("border", "none")) != "none"
    }
    if borders:
        cell.border = Border(**borders)


def _copy_cells(sheet, source, styles, row_count, col_count):
    defaults = styles.get(None, {})
    for start, row, repeated in ob.logical_rows(source):
        if start >= row_count:
            break
        row_props = styles.get(row.getAttribute("stylename"), {})
        row_height = row_props.get("row-height")
        for row_number in range(start + 1, min(start + repeated, row_count) + 1):
            if row_height:
                sheet.row_dimensions[row_number].height = float(row_height.removesuffix("pt"))
            for col, node in ob.logical_cells(row, col_count - 1).items():
                if node.qname[1] != "table-cell":
                    continue
                cell = sheet.cell(row_number, col + 1)
                if node.getAttribute("valuetype") == "float":
                    cell.value = float(node.getAttribute("value"))
                else:
                    text = "\n".join(extractText(p) for p in node.getElementsByType(P))
                    if text:
                        cell.value = text
                        cell.data_type = "s"
                _apply_cell_style(cell, {**defaults, **styles.get(node.getAttribute("stylename"), {})})
                width = int(node.getAttribute("numbercolumnsspanned") or 1)
                height = int(node.getAttribute("numberrowsspanned") or 1)
                if width > 1 or height > 1:
                    sheet.merge_cells(
                        start_row=row_number, end_row=min(row_number + height - 1, row_count),
                        start_column=col + 1, end_column=min(col + width, col_count),
                    )


def _set_print_layout(sheet, source, styles, page, row_count, col_count):
    for col, node in enumerate(source.getElementsByType(TableColumn)[:col_count], 1):
        width = styles.get(node.getAttribute("stylename"), {}).get("column-width")
        if width:
            pixels = float(width.removesuffix("cm")) / 2.54 * 96
            sheet.column_dimensions[get_column_letter(col)].width = (pixels - 5) / 7
    sheet.print_area = f"A1:{get_column_letter(col_count)}{row_count}"
    sheet.print_options.horizontalCentered = page.get("table-centering") == "horizontal"
    sheet.page_setup.orientation = page.get("print-orientation", "portrait")
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    for side in ("left", "right", "top", "bottom"):
        margin = page.get(f"margin-{side}")
        if margin:
            setattr(sheet.page_margins, side, float(margin.removesuffix("in")))


def save_xlsx(doc, areas, path):
    styles = {style.getAttribute("name"): _properties(style)
              for style in doc.getElementsByType(Style)}
    styles[None] = next((_properties(style) for style in doc.getElementsByType(DefaultStyle)
                         if style.getAttribute("family") == "table-cell"), {})
    masters = {master.getAttribute("name"): master.getAttribute("pagelayoutname")
               for master in doc.getElementsByType(MasterPage)}
    pages = {page.getAttribute("name"): _properties(page)
             for page in doc.getElementsByType(PageLayout)}
    sheet_layouts = {style.getAttribute("name"): masters.get(style.getAttribute("masterpagename"))
                     for style in doc.getElementsByType(Style)
                     if style.getAttribute("family") == "table"}
    wb = Workbook()
    wb.remove(wb.active)
    for source, row_count, col_count in areas:
        sheet = wb.create_sheet(source.getAttribute("name"))
        page = pages.get(sheet_layouts.get(source.getAttribute("stylename")), {})
        _copy_cells(sheet, source, styles, row_count, col_count)
        _set_print_layout(sheet, source, styles, page, row_count, col_count)
    wb.save(path)
    wb.close()
