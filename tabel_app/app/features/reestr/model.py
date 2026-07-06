"""Модель данных функции «Реестр»."""

from dataclasses import dataclass, field


@dataclass
class ServiceRecord:
    """Строка реестра (гос или доп) по одному клиенту."""
    client_id: str
    fio: str            # ФИО без даты рождения
    fio_full: str       # как в файле (с «дд.мм.ггггг.р.»)
    birth: str          # дата рождения (если выделена)
    address: str
    contract_raw: str   # «№ договора» как в файле
    contract: str       # извлечённый номер договора (напр. «804-З-09»)
    contract_date: str  # дата заключения договора
    period: str         # период оказания услуг (напр. «2026.05»)
    count: float        # кол-во услуг
    po_dogovoru: float  # сумма по договору (K)
    nachisleno: float   # начислено (L)
    oplacheno: float    # оплачено (M)
    worker: str         # соцработник (N)


@dataclass
class IpsuRecord:
    """Строка отчёта ИПСУ по одной программе (у клиента может быть несколько)."""
    client_id: str
    fio: str
    birth: str
    address: str
    issue_date: str     # дата выдачи ИПСУ (F)
    ipsu_num: str       # № ИПСУ (G)
    srok: str           # срок предоставления услуги (H), напр. «01.04.2026 - 31.03.2029»


@dataclass
class RegistryInput:
    """Распарсенный реестр (гос или доп)."""
    kind: str                       # 'gos' | 'dop'
    department_name: str            # из шапки/итоговой строки
    period_start: str               # из заголовка («01.05.2026»)
    period_end: str
    records: list = field(default_factory=list)   # list[ServiceRecord]
    subtotal_count: float = 0.0
    subtotal_po_dogovoru: float = 0.0
    subtotal_nachisleno: float = 0.0
    subtotal_oplacheno: float = 0.0
