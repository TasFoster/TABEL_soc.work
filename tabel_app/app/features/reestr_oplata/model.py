"""Структурная модель разобранного реестра .ods для функции «Реестр по оплате».

Каждый датакласс хранит ССЫЛКУ на реальный odfpy-элемент строки (`row`) — так правки
и удаление применяются прямо к дереву документа, а адреса формул пересобираются по
финальной раскладке (см. ods_editor.rebuild_formulas).
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class GosClient:
    row: Any                 # odfpy TableRow
    is_dop_line: bool        # True для строк «Д.» (доп-клиент в блоке Гос_)
    num: int
    fio_full: str            # ФИО с датой рождения (столбец C)
    fio_norm: str
    contract_raw: str        # «Договор №221-З-09» (столбец D)
    contract: str            # «221-З-09»
    e_oplata: Any            # столбец E (число или 'бесплатно')
    f_koplate: Any           # столбец F
    peresmotr: str           # столбец G (метка)
    h_dop: Optional[float]   # столбец H (доп-сумма)


@dataclass
class GosBlock:
    worker_fio: str
    marker_row: Any
    name_row: Any
    itogo_row: Any
    clients: List[GosClient] = field(default_factory=list)
    dop_lines: List[GosClient] = field(default_factory=list)

    def data_rows(self):
        """Клиентские строки блока по порядку в документе (для диапазона SUM)."""
        return self.clients + self.dop_lines


@dataclass
class DopRow:
    row: Any
    num: int
    fio_full: str
    fio_norm: str
    contract_raw: str
    contract: str
    date: str
    summa: float             # столбец E (логич. 5)
    mark: str                # столбец K (логич. 10)


@dataclass
class DengiRow:
    row: Any
    worker_fio: str
    ref_block: Optional[GosBlock]   # блок Гос_, на Итого которого ссылается формула


@dataclass
class RegistryModel:
    doc: Any
    gos_table: Any
    dop_table: Any
    dengi_table: Any
    gos_blocks: List[GosBlock] = field(default_factory=list)
    gos_vsego_row: Any = None
    gos_letter_cell: Any = None
    dop_rows: List[DopRow] = field(default_factory=list)
    dop_itogo_row: Any = None
    dop_letter_cell: Any = None
    dengi_rows: List[DengiRow] = field(default_factory=list)
    dengi_itogo_row: Any = None

    def block_by_worker(self, worker_fio):
        for b in self.gos_blocks:
            if b.worker_fio == worker_fio:
                return b
        return None
