"""Запуск приложения (главное меню функций).

Двойной клик по собранному .exe или `python main.py` из исходников.
Функции находятся в app/features/<имя>; список — в app/features/registry.py.
"""

import os
import sys

# Чтобы импорт пакета app работал и из исходников, и из .exe.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


_MUTEX = None


def _create_app_mutex():
    """Именованный мьютекс, чтобы установщик (Inno AppMutex) видел запущенную программу
    и предложил закрыть её перед обновлением. Не мешает работе при ошибке."""
    global _MUTEX
    try:
        import ctypes
        _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "TabelAppRunningMutex")
    except Exception:  # noqa: BLE001
        _MUTEX = None


def _selftest():
    """Скрытая самопроверка: формирует тестовый табель и пишет результат в файл.

    Нужна, чтобы проверить работу из собранного .exe (в оконном режиме нет консоли)."""
    import datetime
    import traceback

    base = _base_dir()
    log = os.path.join(base, "selftest_result.txt")
    try:
        from app.features.timesheet import storage
        from app.features.timesheet.service import generate_timesheet

        deps = storage.load_departments()
        dept = deps["departments"][0]
        today = datetime.date.today()
        out = os.path.join(base, "selftest_output.xls")
        generate_timesheet(dept, today.year, today.month, {}, out)
        with open(log, "w", encoding="utf-8") as f:
            f.write("OK " + out)
    except Exception:
        with open(log, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())


def _selftest_reestr():
    """Самопроверка функции «Реестр»: формирует .ods из папки с тремя файлами.
    Папка передаётся следующим аргументом после --selftest-reestr."""
    import traceback

    base = _base_dir()
    log = os.path.join(base, "selftest_reestr_result.txt")
    try:
        idx = sys.argv.index("--selftest-reestr")
        folder = sys.argv[idx + 1]
        from app.features.reestr import gui as rgui, service

        found = rgui._detect(folder)
        prep = service.prepare(found["gos"], found["dop"], found["ipsu"])
        out = os.path.join(base, "selftest_reestr.ods")
        service.generate(prep, dept_number="9", zav_fio="Т.И.Шершнева", out_path=out)
        with open(log, "w", encoding="utf-8") as f:
            f.write("OK " + out)
    except Exception:
        with open(log, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())


def _selftest_pril():
    """Самопроверка функции «Приложение к табелю»: засев БД + формирование .xls."""
    import datetime
    import traceback

    base = _base_dir()
    log = os.path.join(base, "selftest_pril_result.txt")
    try:
        from app.features.prilozhenie import service, storage

        storage.ensure_ready()
        depts = storage.list_departments()
        dept_id = depts[0]["id"]
        today = datetime.date.today()
        out = os.path.join(base, "selftest_pril.xls")
        _, res = service.generate_prilozhenie(dept_id, today.year, today.month, out)
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"OK {out}\nИтого город={res['grand_total']['gor']} "
                    f"частный={res['grand_total']['chast']}")
    except Exception:
        with open(log, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())


def _selftest_proezd():
    """Самопроверка «Проезд»: поездки и билеты из шаблона-образца -> .ods."""
    import traceback

    import datetime

    base = _base_dir()
    log = os.path.join(base, "selftest_proezd_result.txt")
    try:
        from app.features.proezd import service, storage

        tpl = storage.template_path()
        prepared = service.prepare(tpl)
        hdr = prepared["header"]
        s = storage.load_settings()
        today = datetime.date.today()
        month = service._month_index(hdr.get("month_upper", ""), s) or today.month
        ys = str(hdr.get("year", "")).strip()
        year = int(ys) if ys.isdigit() else today.year
        rows, note = service.build_rows(prepared, year, month, s)
        out = os.path.join(base, "selftest_proezd.ods")
        service.generate(rows, hdr, year, month, out)
        total = sum(r["price"] for r in rows)
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"OK {out}\nПоездок={len(rows)} сумма={total} "
                    f"OCR={'есть' if prepared['ocr_available'] else 'нет'}\n{note}")
    except Exception:
        with open(log, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())


def _selftest_uslugi():
    """Самопроверка «Услуги-Деньги»: из папки с отчётом 071 и xlsx льготников -> .xlsx.
    Папка передаётся следующим аргументом после --selftest-uslugi."""
    import traceback

    base = _base_dir()
    log = os.path.join(base, "selftest_uslugi_result.txt")
    try:
        idx = sys.argv.index("--selftest-uslugi")
        folder = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "."
        from app.features.uslugi_dengi import service

        f071 = fben = None
        for fn in os.listdir(folder):
            p = os.path.join(folder, fn)
            low = fn.lower()
            if low.endswith(".xls") and "071" in low:
                f071 = p
            elif (low.endswith(".xlsx") or low.endswith(".xls")) and (
                    "бесплат" in low or "частич" in low):
                fben = p
        data = service.prepare(f071, fben)
        out = os.path.join(base, "selftest_uslugi.xlsx")
        service.generate(data, out, 2, 2026, "9")
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"OK {out}\nуслуг071={len(data['counts071'])} "
                    f"бесплатников={len(data['free_clients'])} "
                    f"частичников={len(data['part_cnt_clients'])}")
    except Exception:
        with open(log, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())


def _selftest_protokol():
    """Самопроверка «Протокол»: реквизиты + соцработники из БД -> .odt."""
    import datetime
    import traceback

    base = _base_dir()
    log = os.path.join(base, "selftest_protokol_result.txt")
    try:
        from app.features.protokol import service, storage

        depts = storage.list_departments()
        dept = depts[0]
        people = storage.soc_workers(dept["id"])
        attendees = people[:-1] if len(people) > 1 else people
        absentees = people[-1:] if len(people) > 1 else []
        today = datetime.date.today()
        d = service.last_working_wednesday(today.year, today.month)
        out = os.path.join(base, "selftest_protokol.odt")
        service.generate(out, "1", service.format_date(d), attendees,
                         service.default_body(today.month), absentees=absentees)
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"OK {out}\nдата(последняя раб. среда)={service.format_date(d)} "
                    f"присутств={len(attendees)} отсутств={len(absentees)}")
    except Exception:
        with open(log, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())


def _selftest_gos():
    """Самопроверка «Отчёт по госзаданию»: из файла-источника -> .ods.
    Путь к файлу передаётся следующим аргументом после --selftest-gos."""
    import traceback

    base = _base_dir()
    log = os.path.join(base, "selftest_gos_result.txt")
    try:
        idx = sys.argv.index("--selftest-gos")
        src = sys.argv[idx + 1]
        from app.features.gos_zadanie import service

        data = service.prepare(src)
        out = os.path.join(base, "selftest_gos.ods")
        service.generate(data, out)
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"OK {out}\nполучателей={len(data['clients'])} "
                    f"основных={len(data['main_services'])} доп={len(data['dop_services'])} "
                    f"новых_услуг={len(data['new_services'])}")
    except Exception:
        with open(log, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())


def _selftest_pk():
    """Самопроверка «Проверка качества»: реестр .xls -> .ods (все четверги месяца).
    Путь к реестру передаётся следующим аргументом после --selftest-pk."""
    import datetime
    import traceback

    base = _base_dir()
    log = os.path.join(base, "selftest_pk_result.txt")
    try:
        idx = sys.argv.index("--selftest-pk")
        src = sys.argv[idx + 1]
        from app.features.proverka_kachestva import service

        wc = service.parse_workers_clients(src)
        if not wc["order"]:
            raise RuntimeError("в реестре не найдено ни одного соцработника")
        today = datetime.date.today()
        thus = service.month_thursdays(today.year, today.month)
        rows = []
        for worker in wc["order"][:3]:
            for j, (client, addr) in enumerate(wc["by_worker"][worker][:3]):
                d = thus[j % len(thus)] if thus else today
                rows.append({"date": service.format_date(d), "worker": worker,
                             "client": client, "address": addr, "phone": "", "result": "нет"})
        ctx = {"title": service.default_title("9"),
               "sign": service.default_sign("9", "Шершнева Т.И."),
               "dept_no": "9", "zav": "Шершнева Т.И."}
        out = os.path.join(base, "selftest_pk.ods")
        service.generate(out, ctx, rows)
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"OK {out}\nсоцработников={len(wc['order'])} "
                    f"строк={len(rows)} четвергов={len(thus)}")
    except Exception:
        with open(log, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())


def _selftest_peresmotr():
    """Самопроверка «Пересмотр»: отчёт ИПСУ -> список с окончанием срока -> .ods.
    Путь к отчёту ИПСУ передаётся следующим аргументом после --selftest-peresmotr."""
    import traceback

    base = _base_dir()
    log = os.path.join(base, "selftest_peresmotr_result.txt")
    try:
        idx = sys.argv.index("--selftest-peresmotr")
        src = sys.argv[idx + 1]
        from app.features.peresmotr import service

        # период — из последней даты окончания в отчёте (чтобы точно что-то нашлось)
        recs = service.reestr_parser.parse_ipsu(src)
        ends = [service.end_date(r.srok) for r in recs]
        ends = [e for e in ends if e]
        y, m = (ends[0].year, ends[0].month) if ends else (2026, 5)
        rows = service.find_expiring(src, y, m)
        ctx = {"title": service.default_title(y, m)}
        out = os.path.join(base, "selftest_peresmotr.ods")
        service.generate(out, ctx, rows)
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"OK {out}\nпериод={m:02d}.{y} записей={len(rows)} всего_ИПСУ={len(recs)}")
    except Exception:
        with open(log, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())


if __name__ == "__main__":
    try:
        from app.core import logging_setup
        logging_setup.setup()
    except Exception:  # noqa: BLE001 — логирование не должно мешать запуску
        pass
    if "--selftest" in sys.argv:
        _selftest()
    elif "--selftest-reestr" in sys.argv:
        _selftest_reestr()
    elif "--selftest-pril" in sys.argv:
        _selftest_pril()
    elif "--selftest-proezd" in sys.argv:
        _selftest_proezd()
    elif "--selftest-uslugi" in sys.argv:
        _selftest_uslugi()
    elif "--selftest-protokol" in sys.argv:
        _selftest_protokol()
    elif "--selftest-gos" in sys.argv:
        _selftest_gos()
    elif "--selftest-pk" in sys.argv:
        _selftest_pk()
    elif "--selftest-peresmotr" in sys.argv:
        _selftest_peresmotr()
    else:
        _create_app_mutex()
        from app.shell import run

        run()
