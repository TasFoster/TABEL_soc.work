"""Модель данных функции «Приложение к табелю»."""

from dataclasses import dataclass, field

SECTORS = ("gor", "chast")
SECTOR_LABEL = {"gor": "гор.", "chast": "част"}
# Порог-предупреждение (человек/день на сотрудника по сектору) = 2× норма.
THRESHOLD = {"gor": 20, "chast": 16}


@dataclass
class Worker:
    employee_id: int
    n: int
    fio: str
    oklad: float = 0
    load_gor: float = 0
    load_chast: float = 0
    norma_gor: float = 10
    norma_chast: float = 8
    active: bool = True

    def load(self, sector):
        return self.load_gor if sector == "gor" else self.load_chast

    def norma(self, sector):
        return self.norma_gor if sector == "gor" else self.norma_chast


@dataclass
class Period:
    """Помесячное переопределение нагрузки сотрудника по периоду дат."""
    employee_id: int
    sector: str
    day_from: int
    day_to: int
    value: float


@dataclass
class Absence:
    employee_id: int
    day_from: int
    day_to: int
    code: str = ""


@dataclass
class Redistribution:
    """Передать value чел/день в секторе от одного сотрудника другому
    на дни day_from..day_to."""
    sector: str
    from_employee_id: int
    to_employee_id: int
    day_from: int
    day_to: int
    value: float
