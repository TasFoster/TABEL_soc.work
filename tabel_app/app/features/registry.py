"""Реестр функций приложения (мягкая регистрация).

Чтобы ДОБАВИТЬ НОВУЮ ФУНКЦИЮ:
  1. Создайте папку app/features/<имя>/ со своим кодом и (при необходимости)
     подпапками data/ и templates/.
  2. Реализуйте функцию open_<имя>(master) -> tk.Toplevel, открывающую её окно.
  3. Добавьте свою функцию-регистратор в кортеж _REGISTRARS ниже.
Главное меню само покажет новую кнопку.

Регистрация «мягкая»: каждая функция добавляется в try/except. Если модуль функции
исключён из конкретной сборки (например, «Проезд» в лёгкой версии через
--exclude-module), импорт упадёт и функция просто не появится — ядро править не нужно
(принцип Open/Closed; см. docs/АРХИТЕКТУРА.md §6).
"""

import sys


class Feature:
    def __init__(self, key, title, description, opener):
        self.key = key
        self.title = title
        self.description = description
        self._opener = opener

    def open(self, master):
        return self._opener(master)


def _add_timesheet(features):
    from .timesheet import FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION
    from .timesheet.gui import open_timesheet
    features.append(Feature(FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION, open_timesheet))


def _add_prilozhenie(features):
    from .prilozhenie import FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION
    from .prilozhenie.gui import open_prilozhenie
    features.append(Feature(FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION, open_prilozhenie))


def _add_reestr_oplata(features):
    from .reestr_oplata import FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION
    from .reestr_oplata.gui import open_reestr_oplata
    features.append(Feature(FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION, open_reestr_oplata))


def _add_proezd(features):
    from .proezd import FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION
    from .proezd.gui import open_proezd
    features.append(Feature(FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION, open_proezd))


def _add_uslugi_dengi(features):
    from .uslugi_dengi import FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION
    from .uslugi_dengi.gui import open_uslugi_dengi
    features.append(Feature(FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION, open_uslugi_dengi))


def _add_grafiki(features):
    from .grafiki import FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION
    from .grafiki.gui import open_grafiki
    features.append(Feature(FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION, open_grafiki))


def _add_gos_zadanie(features):
    from .gos_zadanie import FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION
    from .gos_zadanie.gui import open_gos_zadanie
    features.append(Feature(FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION, open_gos_zadanie))


def _add_proverka_kachestva(features):
    from .proverka_kachestva import FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION
    from .proverka_kachestva.gui import open_proverka_kachestva
    features.append(Feature(FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION,
                            open_proverka_kachestva))


def _add_peresmotr(features):
    from .peresmotr import FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION
    from .peresmotr.gui import open_peresmotr
    features.append(Feature(FEATURE_KEY, FEATURE_TITLE, FEATURE_DESCRIPTION, open_peresmotr))


# Порядок отображения в главном меню. Добавляйте сюда новые функции-регистраторы.
# «Протокол» удалён; старый «Реестр» убран из меню (общие модули пакета reestr
# и редактор клиентов ClientsManager остаются) — его заменил «Реестр по оплате».
_REGISTRARS = (_add_timesheet, _add_prilozhenie, _add_reestr_oplata, _add_proezd,
               _add_uslugi_dengi, _add_grafiki, _add_gos_zadanie,
               _add_proverka_kachestva, _add_peresmotr)


def get_features():
    features = []
    for add in _REGISTRARS:
        try:
            add(features)
        except Exception as e:  # noqa: BLE001 — функция отсутствует в этой сборке
            print(f"[registry] функция пропущена ({add.__name__}): {e}", file=sys.stderr)
    return features
