"""Оркестратор функции «Реестр»: парсинг → привязка → расчёт → запись .ods."""

from ...core import db as _db
from . import journal as _journal
from . import parser, registry_builder, storage
from .journal import norm_fio
from .ods_writer import generate as _generate

ALL_SHEETS = ("gos", "dop", "dengi", "peresmotr")


def prepare(gos_path, dop_path, ipsu_path, journal_path=None):
    """Распарсить входные файлы и определить новых (нераспределённых) клиентов.

    journal_path (необязательно) — «Отчёт по количеству заключённых договоров»: по нему
    отметки новый/пересмотр/снят определяются сравнением с прошлым месяцем ПО ФИО."""
    gos = parser.parse_registry(gos_path, "gos")
    dop = parser.parse_registry(dop_path, "dop")
    ipsu = parser.parse_ipsu(ipsu_path)

    wm = storage.load_worker_map()
    fio2w = wm.get("client_worker", {})

    wm_id = {}
    unassigned = {}  # ФИО -> подсказка работника (из колонки реестра)
    for r in gos.records + dop.records:
        if r.fio in fio2w:
            wm_id[r.client_id] = fio2w[r.fio]
        elif r.fio not in unassigned:
            unassigned[r.fio] = (r.worker or "").strip()

    reg_workers = sorted({(r.worker or "").strip()
                          for r in gos.records + dop.records if (r.worker or "").strip()})

    # Список клиентов (норм. ФИО -> отображаемое ФИО) для окна ручной пометки «пересмотр».
    client_fios = {}
    for r in gos.records + dop.records:
        k = norm_fio(r.fio)
        if k and k not in client_fios:
            client_fios[k] = r.fio

    journal = None
    if journal_path:
        jdata = _journal.parse_journal(journal_path)
        prev_j = storage.load_prev_journal()
        new_fios, per_fios, snyat = _journal.diff_marks(jdata["by_fio"], prev_j)
        journal = {
            "by_fio": _journal.to_storable(jdata["by_fio"]),
            "auto_new": sorted(new_fios),
            "auto_peresmotr": sorted(per_fios),
            "snyat": sorted(snyat),
            "period": jdata["period"],
            "had_prev": bool(prev_j),
        }

    return {
        "gos": gos,
        "dop": dop,
        "ipsu": ipsu,
        "worker_map_id": wm_id,
        "worker_order": wm.get("worker_order", []),
        "registry_workers": reg_workers,
        "unassigned_fios": list(unassigned.keys()),
        "unassigned_suggest": unassigned,
        "period_start": gos.period_start or dop.period_start,
        "client_fios": client_fios,
        "journal": journal,
    }


def assign_new(fio_to_worker):
    """Сохранить привязку новых клиентов (ФИО→работник) в постоянную базу."""
    wm = storage.load_worker_map()
    cw = wm.setdefault("client_worker", {})
    cw.update({fio: w for fio, w in fio_to_worker.items() if w})
    order = wm.setdefault("worker_order", [])
    for w in fio_to_worker.values():
        if w and w not in order:
            order.append(w)
    storage.save_worker_map(wm)


def all_workers():
    return list(storage.load_worker_map().get("worker_order", []))


def employee_workers():
    """Соцработники из единой базы (для списков выбора соцработника в «Реестре»)."""
    return _db.employee_worker_fios()


def generate(prepared, dept_number, zav_fio, out_path, sheets=ALL_SHEETS,
             mark_new_fios=None, mark_peresmotr_fios=None):
    """Сформировать реестр.

    mark_new_fios / mark_peresmotr_fios — множества нормализованных ФИО (из журнала и/или
    ручной пометки в окне). Если заданы, переопределяют авто-определение новый/пересмотр."""
    settings = storage.load_settings()
    prev = storage.load_prev()

    # Привязка с учётом только что назначенных клиентов.
    wm = storage.load_worker_map()
    fio2w = wm.get("client_worker", {})
    wm_id = {}
    for r in prepared["gos"].records + prepared["dop"].records:
        if r.fio in fio2w:
            wm_id[r.client_id] = fio2w[r.fio]

    prev_contracts = {k: set(v) for k, v in prev.get("contracts", {}).items()} or None
    prev_dop_ids = set(prev.get("dop_ids", [])) if prev.get("dop_ids") else None

    data = registry_builder.build(
        prepared["gos"], prepared["dop"], prepared["ipsu"],
        worker_map=wm_id, worker_order=wm.get("worker_order", []),
        prev_contracts=prev_contracts, prev_dop_ids=prev_dop_ids,
        mark_new_fios=mark_new_fios, mark_peresmotr_fios=mark_peresmotr_fios,
    )

    sig = {
        "zav_fio": zav_fio,
        "director": settings.get("director", ""),
        "deputy": settings.get("deputy", ""),
    }
    _generate(storage.template_path(), out_path, data, dept_number, sig, sheets=tuple(sheets))

    # Сохранить текущий месяц как «прошлый» для следующего раза.
    contracts = {}
    for r in prepared["gos"].records + prepared["dop"].records:
        contracts.setdefault(r.client_id, [])
        if r.contract and r.contract not in contracts[r.client_id]:
            contracts[r.client_id].append(r.contract)
    dop_ids = list(dict.fromkeys(r.client_id for r in prepared["dop"].records))
    storage.save_prev({"contracts": contracts, "dop_ids": dop_ids})
    # Журнал текущего месяца -> «прошлый журнал» для сравнения в следующем месяце.
    if prepared.get("journal"):
        storage.save_prev_journal(prepared["journal"]["by_fio"])

    return out_path
