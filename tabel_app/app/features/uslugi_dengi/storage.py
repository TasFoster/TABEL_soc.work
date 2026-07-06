"""Хранилище функции «Услуги-Деньги»: путь к шаблону."""

import os

from ...core import storage as _core

FEATURE = "uslugi_dengi"
_PKG = os.path.dirname(os.path.abspath(__file__))


def template_path():
    return _core.template_path(FEATURE, _PKG, "uslugi_dengi_template.xlsx")
