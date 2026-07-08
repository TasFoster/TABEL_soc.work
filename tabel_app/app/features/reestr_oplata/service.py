"""Контроллер функции «Реестр по оплате».

Сравнивает готовый реестр (модель из ods_editor.load_model) с отчётом о
заключённых договорах за месяц (journal.parse_journal_detailed) и строит ПЛАН
предлагаемых изменений (суммы / снятые / новые / доп). Пользователь в окне
подтверждает изменения галочками; apply_plan применяет выбранные операции и
пересобирает живые формулы (ods_editor.rebuild_formulas).

Сопоставление клиентов — ПО ФИО (+ № договора), как и в остальном реестре
(номер строки между месяцами нестабилен).
"""

from dataclasses import dataclass, field

from ..reestr import ods_build as ob
from ..reestr.journal import norm_fio, parse_journal_detailed
from . import ods_editor as ed

# Категории изменений (для группировки в предпросмотре)
CAT_SUM = "sum"            # Гос: изменить суммы E/F/H существующего клиента
CAT_SNYAT = "snyat"        # Гос: обнулить снятого клиента (нет в журнале)
CAT_NEW = "new"            # Гос: новый клиент (нужно назначить соцработника)
CAT_DOP_NEW = "dop_new"    # Доп: новая строка (доп-договор существующего клиента)
CAT_DOP_SNYAT = "dop_snyat"  # Доп: обнулить строку (нет в журнале)
CAT_DOP_UPD = "dop_upd"    # Доп: обновить сумму существующей строки (сменился ярлык договора)

CAT_TITLES = {
    CAT_SUM: "Суммы (Гос)",
    CAT_SNYAT: "Снятые (Гос)",
    CAT_NEW: "Новые клиенты (Гос)",
    CAT_DOP_UPD: "Доп: обновить сумму",
    CAT_DOP_NEW: "Новые доп-строки",
    CAT_DOP_SNYAT: "Снятые доп-строки",
}


@dataclass
class Change:
    category: str
    fio: str
    worker: str                       # соцработник (для CAT_NEW назначается в окне)
    detail: str                       # текст «было → стало»
    selected: bool = True
    data: dict = field(default_factory=dict)


@dataclass
class Plan:
    period: tuple
    changes: list = field(default_factory=list)

    def by_category(self, cat):
        return [c for c in self.changes if c.category == cat]

    @property
    def selected(self):
        return [c for c in self.changes if c.selected]


def _num(v):
    return float(v) if isinstance(v, (int, float)) else 0.0


def _d(v):
    return ob._disp(round(_num(v), 2))


def _gos_sum(rec, contract):
    """Гос-сумма клиента из журнала: по № договора, иначе первая (договор сменился)."""
    g = rec.get("gos", {})
    if contract in g:
        return round(g[contract], 2)
    return round(next(iter(g.values()), 0.0), 2)


def _dop_total(rec):
    return round(sum(rec.get("dop", {}).values()), 2)


# --------------------------------------------------------------- построение плана
def compute_plan(model, journal):
    """Построить план изменений реестра по разобранному журналу (parse_journal_detailed)."""
    by = journal["by_fio"]
    period = journal["period"]
    plan = Plan(period=period)

    reg_fios = {c.fio_norm for b in model.gos_blocks
                for c in b.clients + b.dop_lines}

    for b in model.gos_blocks:
        for c in b.clients:                       # обычные клиенты Гос_
            rec = by.get(c.fio_norm)
            if rec is None:
                if _num(c.e_oplata) or _num(c.f_koplate) or _num(c.h_dop):
                    plan.changes.append(Change(
                        CAT_SNYAT, c.fio_full, b.worker_fio, "обнулить (нет в журнале)",
                        data={"client": c}))
                continue
            ne = _gos_sum(rec, c.contract)
            nh = _dop_total(rec) or None
            old = (_num(c.e_oplata), _num(c.f_koplate), _num(c.h_dop))
            new = (ne, ne, _num(nh))
            if old != new:
                plan.changes.append(Change(
                    CAT_SUM, c.fio_full, b.worker_fio, _delta(old, new),
                    data={"client": c, "e": ne, "f": ne, "h": nh}))

        for c in b.dop_lines:                     # строки «Д.» (доп-only в Гос_)
            rec = by.get(c.fio_norm)
            nh = _dop_total(rec) if rec else 0.0
            if _num(c.h_dop) == nh:
                continue
            if rec is None:
                plan.changes.append(Change(
                    CAT_SNYAT, c.fio_full, b.worker_fio, "обнулить доп (нет в журнале)",
                    data={"client": c}))
            else:
                plan.changes.append(Change(
                    CAT_SUM, c.fio_full, b.worker_fio,
                    f"доп {_d(c.h_dop)} → {_d(nh)}",
                    data={"client": c, "e": None, "f": None, "h": nh or None}))

    # Новые клиенты: есть в журнале, нет в реестре (нужна привязка к соцработнику)
    for key, rec in by.items():
        if key in reg_fios:
            continue
        gcontract = next(iter(rec.get("gos", {}).keys()), "")
        gsum = _gos_sum(rec, gcontract) if rec.get("gos") else 0.0
        dsum = _dop_total(rec)
        detail = f"гос {_d(gsum)}" + (f", доп {_d(dsum)}" if dsum else "")
        plan.changes.append(Change(
            CAT_NEW, rec["fio"], "", detail,
            data={"fio": rec["fio"], "contract": gcontract, "e": gsum, "f": gsum,
                  "h": dsum or None, "dop": dict(rec.get("dop", {})), "period": period}))

    # Доп-лист: новые доп-строки существующих клиентов
    dop_keys = {(r.fio_norm, r.contract) for r in model.dop_rows}
    for key, rec in by.items():
        if key not in reg_fios:
            continue                              # доп новых клиентов добавит CAT_NEW
        for contract, s in rec.get("dop", {}).items():
            if (key, contract) not in dop_keys:
                plan.changes.append(Change(
                    CAT_DOP_NEW, rec["fio"], "", f"доп +{_d(s)}",
                    data={"fio": rec["fio"], "contract": contract,
                          "summa": round(s, 2), "period": period}))

    # Доп-лист: снятые строки (нет в журнале)
    for r in model.dop_rows:
        rec = by.get(r.fio_norm)
        if (rec is None or r.contract not in rec.get("dop", {})) and r.summa:
            plan.changes.append(Change(
                CAT_DOP_SNYAT, r.fio_full, "", "обнулить доп",
                data={"dop": r}))

    _collapse_dop_relabels(plan)
    return plan


def _collapse_dop_relabels(plan):
    """Схлопнуть ложные пары «снять доп + новая доп» одного ФИО.

    В листе Доп «Доп. соглашение №N к договору …» не совпадает по № договора с
    журналом → тот же доп ошибочно выглядит как снятая старая строка + новая.
    При равной сумме — это лишь смена ярлыка договора (подавить), при разной —
    обновить сумму существующей строки Доп.
    """
    from collections import defaultdict
    snyat, new = defaultdict(list), defaultdict(list)
    for ch in plan.changes:
        if ch.category == CAT_DOP_SNYAT:
            snyat[norm_fio(ch.fio)].append(ch)
        elif ch.category == CAT_DOP_NEW:
            new[norm_fio(ch.fio)].append(ch)

    drop, extra = set(), []
    for key in set(snyat) & set(new):
        if len(snyat[key]) != 1 or len(new[key]) != 1:
            continue                              # неоднозначно — оставить как есть
        s, n = snyat[key][0], new[key][0]
        drop.add(id(s))
        drop.add(id(n))
        row = s.data["dop"]
        new_summa = n.data["summa"]
        if abs(row.summa - new_summa) >= 0.005:   # сумма изменилась — обновить строку
            extra.append(Change(
                CAT_DOP_UPD, n.fio, "", f"доп {_d(row.summa)} → {_d(new_summa)}",
                data={"dop": row, "summa": new_summa}))
    if drop or extra:
        plan.changes = [c for c in plan.changes if id(c) not in drop] + extra


def _delta(old, new):
    oe, of, oh = old
    ne, nf, nh = new
    parts = []
    if (oe, of) != (ne, nf):
        parts.append(f"к оплате {_d(of)} → {_d(nf)}")
    if oh != nh:
        parts.append(f"доп {_d(oh)} → {_d(nh)}")
    return "; ".join(parts) or "без изменений"


# --------------------------------------------------------------- применение плана
def apply_plan(model, plan, journal):
    """Применить выбранные изменения плана и пересобрать живые формулы."""
    # № договоров, уже присутствующих в листе Доп — чтобы не задваивать строки,
    # если тот же доп-договор есть под другим написанием имени.
    dop_contracts = {r.contract for r in model.dop_rows if r.contract}

    def add_dop(fio, contract, period, summa):
        if contract and contract in dop_contracts:
            return
        ed.add_dop_row(model, fio, contract, period[0], round(summa, 2))
        dop_contracts.add(contract)

    for ch in plan.selected:
        d = ch.data
        if ch.category == CAT_SUM:
            c = d["client"]
            if d["e"] is not None:
                ed.set_gos_sums(c, d["e"], d["f"])
            ed.set_gos_dop(c, d["h"])
        elif ch.category == CAT_SNYAT:
            ed.zero_gos_client(d["client"])
        elif ch.category == CAT_NEW:
            block = model.block_by_worker(ch.worker)
            if block is None:
                continue                          # соцработник не назначен — пропустить
            ed.add_gos_client(model, block, d["fio"], d["contract"],
                              d["e"], d["f"], d["h"])
            for contract, s in d.get("dop", {}).items():
                add_dop(d["fio"], contract, d["period"], s)
        elif ch.category == CAT_DOP_NEW:
            add_dop(d["fio"], d["contract"], d["period"], d["summa"])
        elif ch.category == CAT_DOP_UPD:
            ed.set_dop_sum(d["dop"], d["summa"])
        elif ch.category == CAT_DOP_SNYAT:
            ed.set_dop_sum(d["dop"], 0)

    _sync_dop_sums(model, journal)                # суммы существующих доп-строк из журнала
    ed.rebuild_formulas(model, journal["period"])


def _sync_dop_sums(model, journal):
    """Обновить суммы уже существующих строк Доп из журнала (по ФИО + № договора)."""
    by = journal["by_fio"]
    for r in model.dop_rows:
        rec = by.get(r.fio_norm)
        if rec and r.contract in rec.get("dop", {}):
            s = round(rec["dop"][r.contract], 2)
            if r.summa != s:
                ed.set_dop_sum(r, s)


# --------------------------------------------------------------- фасад для окна
def analyze(ods_path, journal_path):
    """Загрузить реестр + журнал, вернуть (model, journal_dict, plan)."""
    model = ed.load_model(ods_path)
    journal = parse_journal_detailed(journal_path)
    if not journal["by_fio"]:
        raise ed.ReestrOplataError(
            "В журнале не найдены договоры — проверьте, что выбран «Отчёт по "
            "количеству заключённых договоров».")
    plan = compute_plan(model, journal)
    return model, journal, plan


def worker_names(model):
    return [b.worker_fio for b in model.gos_blocks]
