"""Очистка печатных колонтитулов в готовых ODF и XLSX."""
import os
import tempfile
import zipfile
from xml.etree import ElementTree as ET


def remove_headers_footers(path):
    namespaces = {"urn:oasis:names:tc:opendocument:xmlns:style:1.0", "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    names = {"header", "footer", "header-left", "footer-left", "header-first", "footer-first", "headerFooter"}
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(temporary, "w") as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename.endswith(".xml") and data.strip():
                    from xml.dom import minidom
                    doc = minidom.parseString(data)
                    changed = False
                    for node in list(doc.getElementsByTagName("*")):
                        if node.namespaceURI in namespaces and node.localName in names:
                            node.parentNode.removeChild(node)
                            changed = True
                    if changed:
                        data = doc.toxml(encoding="utf-8")
                target.writestr(info, data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
