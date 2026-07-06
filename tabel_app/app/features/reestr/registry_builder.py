"""Сборка данных итогового реестра из распарсенных входов.

Группирует клиентов по соцработникам, считает суммы (начислено + доп),
помечает «бесплатно»/«пересмотр»/«новый», готовит данные для всех 4 листов.
"""

from collections import defaultdict

from .journal import norm_fio
from .num2words_ru import rubles_kopecks_in_words


def _norm_worker(name):
    return (name or "").strip()


def _free(nachisleno):
    return abs(nachisleno) < 0.005


def _latest_ipsu(records):
    """Текущий (последний) ИПСУ клиента — по дате выдачи (формат дд.мм.гггг)."""
    def key(r):
        d = r.issue_date
        try:
            dd, mm, yy = d.split(".")
            return (int(yy), int(mm), int(dd))
        except Exception:
            return (0, 0, 0)
    return max(records, key=key) if records else None


def _is_peresmotr(client_id, gos_rec, dop_recs, ipsu_list, prev_contracts):
    """Признак «пересмотр» (новый договор у старого клиента) — по трём сигналам:
    1) в отчёте ИПСУ есть несколько программ и последняя выдана позже прочих
       и действует дольше (срок-конец в будущем за пределами остальных);
    2) номер договора отличается от прошлого месяца;
    3) дата заключения договора в реестре относится к текущему периоду.
    """
    # Сигнал 1: ИПСУ
    if ipsu_list and len(ipsu_list) >= 2:
        def end_key(r):
            try:
                tail = r.srok.split("-")[-1].strip()
                dd, mm, yy = tail.split(".")
                return (int(yy), int(mm), int(dd))
            except Exception:
                return (0, 0, 0)
        latest = _latest_ipsu(ipsu_list)
        others_max_end = max((end_key(r) for r in ipsu_list if r is not latest), default=(0, 0, 0))
        if latest and end_key(latest) > others_max_end:
            return True
    # Сигнал 2: смена номера договора по сравнению с прошлым месяцем
    if prev_contracts is not None:
        prev = prev_contracts.get(client_id)
        cur = gos_rec.contract if gos_rec else (dop_recs[0].contract if dop_recs else None)
        if prev and cur and cur not in prev:
            return True
    return False


def build(gos, dop, ipsu_records, worker_map=None, worker_order=None,
          prev_contracts=None, prev_dop_ids=None,
          mark_new_fios=None, mark_peresmotr_fios=None):
    """Собрать структуру итогового реестра.

    worker_map: {client_id: worker} (хранимая привязка, приоритетнее колонки реестра).
    worker_order: list[str] — порядок соцработников в документе.
    prev_contracts: {client_id: set(номеров договоров)} прошлого месяца (для пересмотр/новый).
    prev_dop_ids: set(client_id) — кто был в доп прошлого месяца (для пометки «новый»).
    mark_new_fios / mark_peresmotr_fios: множества нормализованных ФИО (из журнала +
        ручной правки). Если заданы (не None), ПЕРЕОПРЕДЕЛЯЮТ авто-эвристику новый/пересмотр.
    Возвращает dict с данными по листам + служебные списки (unassigned, peresmotr).
    """
    worker_map = dict(worker_map or {})

    def _peresmotr(fio, auto):
        return (norm_fio(fio) in mark_peresmotr_fios) if mark_peresmotr_fios is not None else auto

    def _new(fio, auto):
        return (norm_fio(fio) in mark_new_fios) if mark_new_fios is not None else auto

    # ИПСУ по клиенту
    ipsu_by_id = defaultdict(list)
    for r in ipsu_records:
        ipsu_by_id[r.client_id].append(r)

    # доп по клиенту (сумма начислено, записи)
    dop_by_id = defaultdict(list)
    for r in dop.records:
        dop_by_id[r.client_id].append(r)

    gos_by_id = {r.client_id: r for r in gos.records}

    # Привязка клиент -> соцработник: карта, иначе колонка реестра
    def worker_of(cid, fallback):
        return _norm_worker(worker_map.get(cid) or fallback) or "(не распределённые)"

    unassigned = []  # клиенты без явной привязки (нет в worker_map)
    # все клиенты (гос ∪ доп)
    all_ids = list(dict.fromkeys([r.client_id for r in gos.records] +
                                 [r.client_id for r in dop.records]))
    for cid in all_ids:
        if cid not in worker_map:
            src = gos_by_id.get(cid)
            fallback = src.worker if src else (dop_by_id[cid][0].worker if dop_by_id.get(cid) else "")
            if not _norm_worker(fallback):
                unassigned.append(cid)

    # ---- Лист «Гос_» (по работникам) ----
    workers = {}
    for r in gos.records:
        w = worker_of(r.client_id, r.worker)
        workers.setdefault(w, {"gos": [], "dop_only": []})
        dop_sum = round(sum(x.nachisleno for x in dop_by_id.get(r.client_id, [])), 2)
        per = _is_peresmotr(r.client_id, r, dop_by_id.get(r.client_id, []),
                            ipsu_by_id.get(r.client_id, []), prev_contracts)
        per = _peresmotr(r.fio, per)
        workers[w]["gos"].append({
            "client_id": r.client_id,
            "fio": r.fio,
            "contract": r.contract,
            "po_dogovoru": r.po_dogovoru,
            "k_oplate": r.nachisleno,
            "free": _free(r.nachisleno),
            "dop_sum": dop_sum if dop_sum else None,
            "peresmotr": per,
        })

    # «Д.» — клиенты с доп, но без гос
    gos_ids = set(gos_by_id.keys())
    for cid, recs in dop_by_id.items():
        if cid in gos_ids:
            continue
        w = worker_of(cid, recs[0].worker)
        workers.setdefault(w, {"gos": [], "dop_only": []})
        workers[w]["dop_only"].append({
            "client_id": cid,
            "fio": recs[0].fio,
            "dop_sum": round(sum(x.nachisleno for x in recs), 2),
        })

    # Сортировка клиентов по алфавиту внутри работника
    for w, d in workers.items():
        d["gos"].sort(key=lambda x: x["fio"])
        d["dop_only"].sort(key=lambda x: x["fio"])

    # Порядок работников
    if worker_order:
        order = [w for w in worker_order if w in workers] + \
                [w for w in sorted(workers) if w not in worker_order]
    else:
        order = sorted(workers)

    # Итоги по работникам (к оплате = начислено + доп)
    worker_totals = {}
    for w, d in workers.items():
        sum_k = round(sum(x["k_oplate"] for x in d["gos"]), 2)
        sum_po = round(sum(x["po_dogovoru"] for x in d["gos"]), 2)
        sum_dop = round(sum((x["dop_sum"] or 0) for x in d["gos"]) +
                        sum(x["dop_sum"] for x in d["dop_only"]), 2)
        worker_totals[w] = {
            "po_dogovoru": sum_po, "k_oplate": sum_k,
            "dop": sum_dop, "itogo": round(sum_k + sum_dop, 2),
        }

    # ---- Лист «Доп» (плоский список) ----
    dop_rows = []
    for r in sorted(dop.records, key=lambda x: x.fio):
        per = _is_peresmotr(r.client_id, gos_by_id.get(r.client_id), [r],
                            ipsu_by_id.get(r.client_id, []), prev_contracts)
        new = (prev_dop_ids is not None) and (r.client_id not in prev_dop_ids)
        per = _peresmotr(r.fio, per)
        new = _new(r.fio, new)
        dop_rows.append({
            "client_id": r.client_id,
            "fio_full": r.fio_full,
            "contract_raw": r.contract_raw,
            "date": r.contract_date,
            "summa": r.nachisleno,
            "new": new,
            "peresmotr": per,
        })
    dop_total = round(sum(r.nachisleno for r in dop.records), 2)

    # ---- Лист «пересмотр» (все клиенты, по работникам, срок из ИПСУ) ----
    peresmotr_rows = {w: [] for w in order}
    for cid in all_ids:
        src = gos_by_id.get(cid)
        recs = dop_by_id.get(cid, [])
        w = worker_of(cid, src.worker if src else (recs[0].worker if recs else ""))
        if w not in peresmotr_rows:
            peresmotr_rows[w] = []
        cur = _latest_ipsu(ipsu_by_id.get(cid, []))
        fio = src.fio if src else (recs[0].fio if recs else "")
        peresmotr_rows[w].append({
            "client_id": cid,
            "fio": fio,
            "birth": cur.birth if cur else (src.birth if src else ""),
            "address": cur.address if cur else (src.address if src else ""),
            "issue_date": cur.issue_date if cur else "",
            "ipsu_num": cur.ipsu_num if cur else "",
            "srok": cur.srok if cur else "",
        })
    for w in peresmotr_rows:
        peresmotr_rows[w].sort(key=lambda x: x["fio"])

    gos_total = round(sum(r.nachisleno for r in gos.records), 2)

    return {
        "period_start": gos.period_start or dop.period_start,
        "period_end": gos.period_end or dop.period_end,
        "worker_order": order,
        "gos_by_worker": workers,
        "worker_totals": worker_totals,
        "gos_total": gos_total,
        "gos_total_words": rubles_kopecks_in_words(gos_total),
        "dop_rows": dop_rows,
        "dop_total": dop_total,
        "dop_total_words": rubles_kopecks_in_words(dop_total),
        "peresmotr_by_worker": peresmotr_rows,
        "unassigned": unassigned,
    }
