"""Модель функции «Отчёт по госзаданию».

Услуги из источника сопоставляются со справочником ПО НАЗВАНИЮ (нормализованному),
т.к. порядок и номера колонок в выгрузке не гарантированы. Категория услуги
(main — лист «госзадание», dop — лист «дополнительные», skip — не выводить)
берётся из редактируемого справочника; неизвестная услуга по умолчанию — dop.
"""

import re
from dataclasses import dataclass, field

MAIN = "main"
DOP = "dop"
SKIP = "skip"


def normalize(s):
    """Привести название услуги к каноническому виду для сравнения."""
    s = str(s or "").lower().replace("ё", "е")
    s = re.sub(r"[^а-яa-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Client:
    """Получатель услуг (строка источника)."""
    fio: str
    birth: str = ""
    sex: str = ""
    total: float = 0.0                      # «Всего услуг» из источника
    counts: dict = field(default_factory=dict)   # {название услуги (как в файле): количество}


class ServiceCatalog:
    """Справочник услуг: название -> категория (main/dop/skip) + порядок колонки."""

    def __init__(self, services):
        self._items = []
        for s in services or []:
            nm = (s.get("name") or "").strip()
            if not nm:
                continue
            self._items.append({
                "name": nm,
                "norm": normalize(nm),
                "category": s.get("category", DOP),
                "order": s.get("order", 999),
            })
        self._by_norm = {it["norm"]: it for it in self._items}

    def lookup(self, name):
        """Запись справочника по названию (точное совпадение по нормализации) или None."""
        return self._by_norm.get(normalize(name))

    def category_of(self, name):
        it = self.lookup(name)
        return it["category"] if it else None

    def order_of(self, name):
        it = self.lookup(name)
        return it["order"] if it else 999

    def add(self, name, category=DOP):
        """Добавить новую услугу (с порядком в конце своей категории). Вернуть запись."""
        nm = (name or "").strip()
        if not nm:
            return None
        existing = self.lookup(nm)
        if existing:
            return existing
        base = 100 if category == DOP else (0 if category == MAIN else 900)
        order = max([it["order"] for it in self._items] + [base]) + 1
        it = {"name": nm, "norm": normalize(nm), "category": category, "order": order}
        self._items.append(it)
        self._by_norm[it["norm"]] = it
        return it

    def to_list(self):
        return [{"name": it["name"], "category": it["category"], "order": it["order"]}
                for it in sorted(self._items, key=lambda x: x["order"])]
