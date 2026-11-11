"""Общая база данных приложения (SQLite) — единое хранилище для всех функций.

Файл базы:  <рядом с программой>/data/app.db

Единый источник правды для ВСЕХ трёх функций:
  • отделения, сотрудники, реквизиты/подписи, производственный календарь;
  • таблицы функции «Приложение к табелю» (нагрузка/периоды/отсутствия/перераспред.);
  • клиенты «Реестра» и их группы по соцработникам (reestr_*).

«Табель» и «Реестр» читают/пишут эту же базу (через свои storage-обёртки), поэтому
правки состава отделения, данных соцработника и клиентов видны во всех функциях и
сохраняются между запусками.

Засев и перенос данных делает ensure_seeded() в виде идемпотентных шагов с флагами в
таблице meta (seeded / ts_migrated / reestr_seeded). При обновлении уже работающей
базы правки из прежних JSON переносятся однократно, причём id сотрудников сохраняются
(сверка по табельному/ФИО), чтобы не потерять привязанные данные «Приложения».

Слой намеренно тонкий: соединение + схема + засев/миграция + простые помощники.
"""

import datetime
import glob
import json
import os
import sqlite3
from contextlib import closing

from . import storage as _storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ext_id               TEXT,
    name                 TEXT NOT NULL,
    organization         TEXT,
    responsible_fio      TEXT,
    responsible_position TEXT,
    sort_order           INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS employees (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dept_id     INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    n           INTEGER,
    fio         TEXT NOT NULL,
    tab_number  TEXT,
    oklad       REAL,
    position    TEXT,
    sort_order  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings_kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS calendar_years (
    year       INTEGER PRIMARY KEY,
    holidays   TEXT,
    short_days TEXT,
    work_days  TEXT          -- перенесённые РАБОЧИЕ дни (рабочая суббота/среда), MM-DD
);

-- ---- Функция «Приложение к табелю» -------------------------------------
-- Постоянная нагрузка сотрудника (стандартное число обслуживаемых в день
-- по каждому сектору) + норма. Не зависит от месяца, редактируется.
CREATE TABLE IF NOT EXISTS pril_load_default (
    employee_id INTEGER PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,
    load_gor    REAL DEFAULT 0,
    load_chast  REAL DEFAULT 0,
    norma_gor   REAL DEFAULT 10,
    norma_chast REAL DEFAULT 8,
    active      INTEGER DEFAULT 1
);

-- Помесячные переопределения нагрузки по периодам дат (блоками).
-- Если на (employee, year, month, sector) есть строки — они задают значения
-- по дням; иначе берётся постоянная нагрузка из pril_load_default.
CREATE TABLE IF NOT EXISTS pril_period (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    sector      TEXT NOT NULL,          -- 'gor' | 'chast'
    day_from    INTEGER NOT NULL,
    day_to      INTEGER NOT NULL,
    value       REAL NOT NULL
);

-- Отсутствия (импортируются из Табеля, правятся вручную здесь).
CREATE TABLE IF NOT EXISTS pril_absence (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    day_from    INTEGER NOT NULL,
    day_to      INTEGER NOT NULL,
    code        TEXT
);

-- Ручное перераспределение чел/дней: на дни day_from..day_to по сектору
-- передать value человек/день от одного сотрудника другому.
CREATE TABLE IF NOT EXISTS pril_redistribution (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    year             INTEGER NOT NULL,
    month            INTEGER NOT NULL,
    sector           TEXT NOT NULL,
    from_employee_id INTEGER REFERENCES employees(id) ON DELETE CASCADE,
    to_employee_id   INTEGER REFERENCES employees(id) ON DELETE CASCADE,
    day_from         INTEGER NOT NULL,
    day_to           INTEGER NOT NULL,
    value            REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ---- Функция «Реестр»: клиенты и их группы (соцработники) --------------
-- Соцработники (группы) и их порядок отображения в реестре.
CREATE TABLE IF NOT EXISTS reestr_workers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fio         TEXT NOT NULL UNIQUE,
    employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,  -- связь по ФИО
    sort_order  INTEGER DEFAULT 0
);

-- Клиенты и закреплённый за ними соцработник (по ФИО).
CREATE TABLE IF NOT EXISTS reestr_clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fio         TEXT NOT NULL UNIQUE,
    worker_fio  TEXT,
    sort_order  INTEGER DEFAULT 0
);

-- Служебные блобы Реестра в JSON (напр. данные прошлого месяца).
CREATE TABLE IF NOT EXISTS reestr_kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ---- Функция «Проверка качества»: телефоны клиентов (по ФИО) -----------
-- В реестре телефонов нет; вводятся вручную и запоминаются, чтобы подставлять
-- в следующий раз. Ключ — ФИО клиента (нормализовано по пробелам, регистр сохранён).
CREATE TABLE IF NOT EXISTS pk_phones (
    client_fio TEXT PRIMARY KEY,
    phone      TEXT
);

-- ---- Функция «Планы»: соцработник «Заслушивания» по (отд, год, месяц) --------
-- План задач фиксирован; из года в год меняется только год в датах и соцработник,
-- чей отчёт заслушивается. Здесь запоминаем выбранного соцработника, чтобы не
-- вводить заново; ключ — отделение + год + месяц. Пусто => берётся из шаблона.
CREATE TABLE IF NOT EXISTS plany_workers (
    dept   TEXT,
    year   INTEGER,
    month  INTEGER,
    worker TEXT,
    PRIMARY KEY (dept, year, month)
);

-- ---- Архив сформированных документов (все функции) --------------------
-- Копия каждого сгенерированного файла + параметры, чтобы открыть/пересохранить
-- позже и (в будущем) переиспользовать настройки.
CREATE TABLE IF NOT EXISTS documents (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    feature    TEXT NOT NULL,      -- ключ функции (timesheet/reestr/.../grafiki)
    title      TEXT,               -- человекочитаемое имя
    filename   TEXT,               -- имя файла с расширением
    created_at TEXT,               -- дата/время формирования (ISO)
    params     TEXT,               -- JSON параметров (период/отделение и т.п.)
    content    BLOB                -- содержимое файла
);
CREATE INDEX IF NOT EXISTS idx_documents_feature_latest
    ON documents(feature, created_at DESC, id DESC);
"""


def db_path():
    return os.path.join(_storage.app_base_dir(), "data", "app.db")


def backup_dir():
    d = os.path.join(_storage.app_base_dir(), "data", "backups")
    os.makedirs(d, exist_ok=True)
    return d


def _embed_protocol_files(connection):
    """Дополнительные JSON хранятся внутри переносимой копии SQLite."""
    from pathlib import Path
    connection.execute("CREATE TABLE IF NOT EXISTS transfer_files (name TEXT PRIMARY KEY, content BLOB NOT NULL)")
    connection.execute("DELETE FROM transfer_files")
    folder = Path(_storage.app_base_dir()) / "data" / "protokol"
    for pattern in ("draft_*.json", "history_*.json"):
        for path in folder.glob(pattern):
            connection.execute("INSERT INTO transfer_files VALUES (?, ?)", (path.name, path.read_bytes()))
    connection.commit()


def _snapshot(dest):
    import contextlib
    with contextlib.closing(sqlite3.connect(db_path())) as source:
        with contextlib.closing(sqlite3.connect(dest)) as target:
            source.backup(target)
            _embed_protocol_files(target)


def backup_db(keep=10):
    """Сделать резервную копию app.db (если есть) в data/backups с ротацией (последние keep).

    Вызывается один раз при запуске ДО миграции схемы — чтобы при сбое было откуда
    восстановиться. На свежей установке (файла ещё нет) ничего не делает."""
    src = db_path()
    if not os.path.exists(src) or os.path.getsize(src) == 0:
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = os.path.join(backup_dir(), f"app-{stamp}.db")
    try:
        _snapshot(dest)
    except Exception:
        if os.path.exists(dest):
            os.remove(dest)
        return None
    files = sorted(glob.glob(os.path.join(backup_dir(), "app-*.db")))
    for old in files[:-keep]:
        try:
            os.remove(old)
        except OSError:
            pass
    return dest


def export_db(dest):
    """Единая копия базы, черновиков и истории протоколов."""
    ensure_seeded()
    if os.path.realpath(dest) == os.path.realpath(db_path()):
        raise ValueError("Выберите отдельный файл для экспорта.")
    import tempfile
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(dest)), suffix=".db")
    os.close(fd)
    try:
        _snapshot(temporary)
        os.replace(temporary, dest)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return dest


def import_db(src):
    """Проверить комплект, сохранить текущие данные и заменить с откатом при ошибке."""
    import re
    import shutil
    import tempfile
    from pathlib import Path
    if os.path.realpath(src) == os.path.realpath(db_path()):
        raise ValueError("Нельзя импортировать рабочую базу в саму себя.")
    test = sqlite3.connect(Path(src).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if test.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Повреждённая база данных.")
        test.execute("SELECT 1 FROM departments LIMIT 1")
        bundled = test.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='transfer_files'").fetchone()
        files = test.execute("SELECT name, content FROM transfer_files").fetchall() if bundled else []
        for name, content in files:
            if not re.fullmatch(r"(?:draft_[A-Za-z0-9_]+|history_[a-f0-9]+)\.json", name):
                raise ValueError("Недопустимое имя файла в копии.")
            json.loads(content)
    finally:
        test.close()
    if os.path.exists(db_path()) and backup_db() is None:
        raise OSError("Не удалось создать резервную копию. Импорт отменён.")
    folder = Path(_storage.feature_data_dir("protokol"))
    # Старые .db не содержат комплект JSON: сохраняем имеющиеся протоколы.
    with tempfile.TemporaryDirectory(dir=Path(db_path()).parent) as temp:
        temp = Path(temp)
        staged = temp / "incoming.db"
        shutil.copy2(src, staged)
        old_db = temp / "previous.db"
        had_db = os.path.exists(db_path())
        if had_db:
            shutil.copy2(db_path(), old_db)
        old_files = {p.name: p.read_bytes() for pattern in ("draft_*.json", "history_*.json") for p in folder.glob(pattern)}
        try:
            if bundled:
                for name in old_files:
                    (folder / name).unlink()
                for name, content in files:
                    (folder / name).write_bytes(content)
            os.replace(staged, db_path())
        except Exception:
            if bundled:
                for pattern in ("draft_*.json", "history_*.json"):
                    for path in folder.glob(pattern):
                        path.unlink()
                for name, content in old_files.items():
                    (folder / name).write_bytes(content)
            if had_db:
                os.replace(old_db, db_path())
            raise
    global _ENSURED
    _ENSURED = False
    return True


def get_conn():
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.executescript(SCHEMA)
        _migrate_schema(conn)
        conn.commit()
    finally:
        if own:
            conn.close()


def _migrate_schema(conn):
    """Безопасные доработки схемы на уже существующих базах (ADD COLUMN)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(calendar_years)")}
    if "work_days" not in cols:
        conn.execute("ALTER TABLE calendar_years ADD COLUMN work_days TEXT")


# ----------------------------------------------------------------- засев
def _meta_get(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def _meta_set(conn, key, value):
    conn.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


_ENSURED = False


def ensure_seeded():
    """Создать схему, засеять справочники и однократно перенести данные из JSON.

    Состоит из независимых идемпотентных шагов, каждый со своим флагом в meta:
      • seeded        — первичный засев из JSON Табеля (только на чистой базе);
      • ts_migrated   — однократный перенос правок состава/настроек/календаря,
                        сделанных в «Табеле» в JSON после засева, в базу;
      • reestr_seeded — однократная загрузка клиентов/групп «Реестра» в базу.
    В рамках процесса выполняется один раз (далее — пустышка).
    """
    global _ENSURED
    if _ENSURED:
        return
    backup_db()  # резервная копия существующей базы ДО возможной миграции схемы
    conn = get_conn()
    try:
        init_db(conn)  # создаст и новые таблицы (CREATE TABLE IF NOT EXISTS)
        fresh = not _meta_get(conn, "seeded")
        if fresh:
            _seed_departments_employees(conn)
            _seed_settings(conn)
            _seed_calendar(conn)
            _seed_pril_loads(conn)
            _meta_set(conn, "seeded", "1")
            _meta_set(conn, "ts_migrated", "1")  # свежая база уже из актуального JSON
        if not _meta_get(conn, "ts_migrated"):
            _migrate_timesheet_from_json(conn)
            _meta_set(conn, "ts_migrated", "1")
        if not _meta_get(conn, "reestr_seeded"):
            _seed_reestr(conn)
            _meta_set(conn, "reestr_seeded", "1")
        conn.commit()
    finally:
        conn.close()
    _ENSURED = True


def _read_timesheet_json(name):
    """Прочитать JSON Табеля (из data/timesheet или из значений по умолчанию)."""
    pkg = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "features", "timesheet",
    )
    try:
        return _storage.load_json("timesheet", pkg, name)
    except Exception:  # noqa: BLE001 — нет файла/значения по умолчанию
        return None


def _seed_departments_employees(conn):
    data = _read_timesheet_json("departments.json")
    if not data:
        return
    for di, dept in enumerate(data.get("departments", [])):
        cur = conn.execute(
            "INSERT INTO departments(ext_id,name,organization,responsible_fio,"
            "responsible_position,sort_order) VALUES(?,?,?,?,?,?)",
            (dept.get("id"), dept.get("name", ""), dept.get("organization", ""),
             dept.get("responsible_fio", ""), dept.get("responsible_position", ""), di),
        )
        dept_id = cur.lastrowid
        for ei, emp in enumerate(dept.get("employees", [])):
            conn.execute(
                "INSERT INTO employees(dept_id,n,fio,tab_number,oklad,position,sort_order)"
                " VALUES(?,?,?,?,?,?,?)",
                (dept_id, emp.get("n", ei + 1), emp.get("fio", ""),
                 str(emp.get("tab_number", "")), _num(emp.get("oklad")),
                 emp.get("position", ""), ei),
            )


def _seed_settings(conn):
    data = _read_timesheet_json("settings.json")
    if not data:
        return
    for key, value in data.items():
        conn.execute(
            "INSERT INTO settings_kv(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO NOTHING",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def _seed_calendar(conn):
    data = _read_timesheet_json("calendar.json")
    if not data:
        return
    for year, ydata in data.items():
        conn.execute(
            "INSERT INTO calendar_years(year,holidays,short_days,work_days) "
            "VALUES(?,?,?,?) ON CONFLICT(year) DO NOTHING",
            (int(year),
             json.dumps(ydata.get("holidays", []), ensure_ascii=False),
             json.dumps(ydata.get("short_days", []), ensure_ascii=False),
             json.dumps(ydata.get("work_days", []), ensure_ascii=False)),
        )


def _seed_pril_loads(conn):
    """Засеять постоянную нагрузку соцработников из loads_seed.json (по ФИО)."""
    pkg = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "features", "prilozhenie",
    )
    seed = None
    try:
        seed = _storage.load_json("prilozhenie", pkg, "loads_seed.json")
    except Exception:  # noqa: BLE001
        seed = None
    by_fio = {}
    if seed:
        for item in seed:
            by_fio[_norm_fio(item.get("fio", ""))] = item
    rows = conn.execute("SELECT id, fio FROM employees").fetchall()
    for row in rows:
        item = by_fio.get(_norm_fio(row["fio"]))
        if item is None:
            # Зав. отделения и не найденные — нагрузка 0, не активны в приложении.
            conn.execute(
                "INSERT OR IGNORE INTO pril_load_default(employee_id,load_gor,"
                "load_chast,norma_gor,norma_chast,active) VALUES(?,?,?,?,?,?)",
                (row["id"], 0, 0, 10, 8, 0),
            )
            continue
        conn.execute(
            "INSERT OR IGNORE INTO pril_load_default(employee_id,load_gor,"
            "load_chast,norma_gor,norma_chast,active) VALUES(?,?,?,?,?,?)",
            (row["id"], _num(item.get("load_gor", 0)), _num(item.get("load_chast", 0)),
             _num(item.get("norma_gor", 10)) or 10, _num(item.get("norma_chast", 8)) or 8, 1),
        )


def _num(v):
    if v in (None, ""):
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def _norm_fio(s):
    return " ".join(str(s).split()).strip().lower()


# ===================================================================== миграция
def _migrate_timesheet_from_json(conn):
    """Однократно влить правки состава/настроек/календаря из JSON Табеля в базу.

    Состав сверяется по табельному номеру/ФИО, поэтому id существующих сотрудников
    (а значит и привязанные к ним данные «Приложения») сохраняются. Настройки и
    календарь перезаписываются значениями из JSON (актуальная версия — у Табеля).
    """
    data = _read_timesheet_json("departments.json")
    if data and data.get("departments"):
        replace_departments(conn, data["departments"], match_by_fio=True)
    settings = _read_timesheet_json("settings.json")
    if settings:
        write_settings(conn, settings)
    calendar = _read_timesheet_json("calendar.json")
    if calendar:
        write_calendar(conn, calendar)


def _seed_reestr(conn):
    """Однократно загрузить клиентов и группы «Реестра» в базу.

    Берём пользовательский worker_map.json (сохранит сделанные назначения), иначе
    зашитый grouping_seed.json. prev_month.json, если есть, кладём в reestr_kv.
    """
    wm = None
    user_wm = os.path.join(_storage.feature_data_dir("reestr"), "worker_map.json")
    if os.path.exists(user_wm):
        try:
            with open(user_wm, "r", encoding="utf-8") as f:
                wm = json.load(f)
        except Exception:  # noqa: BLE001
            wm = None
    if wm is None:
        pkg = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "features", "reestr",
        )
        try:
            wm = _storage.load_json("reestr", pkg, "grouping_seed.json")
        except Exception:  # noqa: BLE001
            wm = None
    if wm:
        reestr_save_map(conn, {
            "worker_order": list(wm.get("worker_order", [])),
            "client_worker": dict(wm.get("client_worker", {})),
        })
    prev_path = os.path.join(_storage.feature_data_dir("reestr"), "prev_month.json")
    if os.path.exists(prev_path):
        try:
            with open(prev_path, "r", encoding="utf-8") as f:
                reestr_set_kv(conn, "prev_month", json.load(f))
        except Exception:  # noqa: BLE001
            pass


# ============================================================ помощники (conn)
def replace_departments(conn, departments, match_by_fio=False):
    """Привести таблицы departments/employees к переданному составу.

    departments — список словарей формы timesheet.storage.load_departments
    ({_db_id, id, name, organization, responsible_fio, responsible_position,
      employees:[{_db_id, n, fio, tab_number, oklad, position}]}).
    Сотрудник опознаётся по _db_id; при match_by_fio (перенос из JSON, где _db_id
    нет) — по табельному номеру, затем по ФИО. Это сохраняет id и привязанные к нему
    данные «Приложения» (pril_* с ON DELETE CASCADE). Отсутствующие — удаляются.
    """
    seen_dept_ids = []
    for di, dept in enumerate(departments):
        dept_id = dept.get("_db_id")
        ext_id = dept.get("id") or None
        name = dept.get("name", "")
        if dept_id is None and match_by_fio:
            row = None
            if ext_id:
                row = conn.execute(
                    "SELECT id FROM departments WHERE ext_id=?", (ext_id,)).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT id FROM departments WHERE name=?", (name,)).fetchone()
            if row is not None:
                dept_id = row["id"]
        exists = dept_id is not None and conn.execute(
            "SELECT 1 FROM departments WHERE id=?", (dept_id,)).fetchone()
        if exists:
            conn.execute(
                "UPDATE departments SET ext_id=?, name=?, organization=?, "
                "responsible_fio=?, responsible_position=?, sort_order=? WHERE id=?",
                (ext_id, name, dept.get("organization", ""),
                 dept.get("responsible_fio", ""), dept.get("responsible_position", ""),
                 di, dept_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO departments(ext_id,name,organization,responsible_fio,"
                "responsible_position,sort_order) VALUES(?,?,?,?,?,?)",
                (ext_id, name, dept.get("organization", ""),
                 dept.get("responsible_fio", ""), dept.get("responsible_position", ""), di),
            )
            dept_id = cur.lastrowid
        seen_dept_ids.append(dept_id)
        _replace_employees(conn, dept_id, dept.get("employees", []), match_by_fio)
    if seen_dept_ids:
        q = ",".join("?" * len(seen_dept_ids))
        conn.execute(
            f"DELETE FROM departments WHERE id NOT IN ({q})", tuple(seen_dept_ids))
    else:
        conn.execute("DELETE FROM departments")


def _replace_employees(conn, dept_id, employees, match_by_fio):
    existing = conn.execute(
        "SELECT id, tab_number, fio FROM employees WHERE dept_id=?", (dept_id,)).fetchall()
    by_tab, by_fio = {}, {}
    for r in existing:
        if r["tab_number"]:
            by_tab.setdefault(str(r["tab_number"]).strip(), r["id"])
        by_fio.setdefault(_norm_fio(r["fio"]), r["id"])
    seen = []
    for ei, emp in enumerate(employees):
        eid = emp.get("_db_id")
        fio = emp.get("fio", "")
        tab = str(emp.get("tab_number", "") or "").strip()
        if eid is None and match_by_fio:
            if tab and tab in by_tab:
                eid = by_tab[tab]
            elif _norm_fio(fio) in by_fio:
                eid = by_fio[_norm_fio(fio)]
        n = emp.get("n", ei + 1)
        oklad = _num(emp.get("oklad"))
        pos = emp.get("position", "")
        exists = eid is not None and conn.execute(
            "SELECT 1 FROM employees WHERE id=? AND dept_id=?", (eid, dept_id)).fetchone()
        if exists:
            conn.execute(
                "UPDATE employees SET n=?, fio=?, tab_number=?, oklad=?, position=?, "
                "sort_order=? WHERE id=?", (n, fio, tab, oklad, pos, ei, eid))
        else:
            cur = conn.execute(
                "INSERT INTO employees(dept_id,n,fio,tab_number,oklad,position,sort_order)"
                " VALUES(?,?,?,?,?,?,?)", (dept_id, n, fio, tab, oklad, pos, ei))
            eid = cur.lastrowid
            active = 0 if "зав" in (pos or "").lower() else 1
            conn.execute(
                "INSERT OR IGNORE INTO pril_load_default(employee_id,load_gor,load_chast,"
                "norma_gor,norma_chast,active) VALUES(?,?,?,?,?,?)",
                (eid, 0, 0, 10, 8, active))
        seen.append(eid)
    if seen:
        q = ",".join("?" * len(seen))
        conn.execute(
            f"DELETE FROM employees WHERE dept_id=? AND id NOT IN ({q})", (dept_id, *seen))
    else:
        conn.execute("DELETE FROM employees WHERE dept_id=?", (dept_id,))


def _departments_to_dict(conn):
    out = []
    depts = conn.execute("SELECT * FROM departments ORDER BY sort_order, id").fetchall()
    employees_by_department = {}
    for emp in conn.execute("SELECT * FROM employees ORDER BY dept_id, sort_order, n, id"):
        employees_by_department.setdefault(emp["dept_id"], []).append(emp)
    for d in depts:
        emps = employees_by_department.get(d["id"], [])
        out.append({
            "_db_id": d["id"],
            "id": d["ext_id"] or "",
            "name": d["name"],
            "organization": d["organization"] or "",
            "responsible_fio": d["responsible_fio"] or "",
            "responsible_position": d["responsible_position"] or "",
            "employees": [{
                "_db_id": e["id"],
                "n": e["n"] if e["n"] is not None else i + 1,
                "fio": e["fio"],
                "tab_number": e["tab_number"] or "",
                "oklad": e["oklad"] if e["oklad"] is not None else "",
                "position": e["position"] or "",
            } for i, e in enumerate(emps)],
        })
    return {"departments": out}


def read_settings(conn):
    rows = conn.execute("SELECT key, value FROM settings_kv").fetchall()
    out = {}
    for r in rows:
        try:
            out[r["key"]] = json.loads(r["value"])
        except (ValueError, TypeError):
            out[r["key"]] = r["value"]
    return out


def write_settings(conn, data):
    for key, value in data.items():
        conn.execute(
            "INSERT INTO settings_kv(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)))


def read_calendar(conn):
    rows = conn.execute(
        "SELECT year, holidays, short_days, work_days FROM calendar_years").fetchall()
    out = {}
    for r in rows:
        out[str(r["year"])] = {
            "holidays": json.loads(r["holidays"] or "[]"),
            "short_days": json.loads(r["short_days"] or "[]"),
            "work_days": json.loads(r["work_days"] or "[]"),
        }
    return out


def write_calendar(conn, data):
    conn.execute("DELETE FROM calendar_years")
    for year, yd in data.items():
        conn.execute(
            "INSERT INTO calendar_years(year,holidays,short_days,work_days) "
            "VALUES(?,?,?,?)",
            (int(year),
             json.dumps(yd.get("holidays", []), ensure_ascii=False),
             json.dumps(yd.get("short_days", []), ensure_ascii=False),
             json.dumps(yd.get("work_days", []), ensure_ascii=False)))


def reestr_load_map(conn):
    workers = conn.execute(
        "SELECT fio FROM reestr_workers ORDER BY sort_order, id").fetchall()
    clients = conn.execute(
        "SELECT fio, worker_fio FROM reestr_clients ORDER BY sort_order, id").fetchall()
    return {
        "worker_order": [r["fio"] for r in workers],
        "client_worker": {r["fio"]: r["worker_fio"] for r in clients},
    }


def reestr_save_map(conn, obj):
    """Полностью заменить клиентов и группы (зависимостей по FK нет)."""
    conn.execute("DELETE FROM reestr_clients")
    conn.execute("DELETE FROM reestr_workers")
    emp_by_fio = {_norm_fio(r["fio"]): r["id"]
                  for r in conn.execute("SELECT id, fio FROM employees").fetchall()}
    for i, fio in enumerate(obj.get("worker_order", [])):
        if not fio:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO reestr_workers(fio, employee_id, sort_order) "
            "VALUES(?,?,?)", (fio, emp_by_fio.get(_norm_fio(fio)), i))
    for i, (cfio, wfio) in enumerate(obj.get("client_worker", {}).items()):
        if not cfio:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO reestr_clients(fio, worker_fio, sort_order) "
            "VALUES(?,?,?)", (cfio, wfio, i))


def reestr_get_kv(conn, key, default=None):
    r = conn.execute("SELECT value FROM reestr_kv WHERE key=?", (key,)).fetchone()
    if not r:
        return default
    try:
        return json.loads(r["value"])
    except (ValueError, TypeError):
        return default


def reestr_set_kv(conn, key, obj):
    conn.execute(
        "INSERT INTO reestr_kv(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(obj, ensure_ascii=False)))


# ============================================ публичный API для функций (своё conn)
def departments_load():
    ensure_seeded()
    with get_conn() as conn:
        return _departments_to_dict(conn)


def departments_save(data):
    ensure_seeded()
    with get_conn() as conn:
        replace_departments(conn, data.get("departments", []))
        conn.commit()


def settings_load():
    ensure_seeded()
    with get_conn() as conn:
        return read_settings(conn)


def settings_save(data):
    ensure_seeded()
    with get_conn() as conn:
        write_settings(conn, data)
        conn.commit()


def calendar_load():
    ensure_seeded()
    with get_conn() as conn:
        return read_calendar(conn)


def calendar_save(data):
    ensure_seeded()
    with get_conn() as conn:
        write_calendar(conn, data)
        conn.commit()


def reestr_map_load():
    ensure_seeded()
    with get_conn() as conn:
        return reestr_load_map(conn)


def reestr_map_save(obj):
    ensure_seeded()
    with get_conn() as conn:
        reestr_save_map(conn, obj)
        conn.commit()


def reestr_kv_load(key, default=None):
    ensure_seeded()
    with get_conn() as conn:
        return reestr_get_kv(conn, key, default)


def reestr_kv_save(key, obj):
    ensure_seeded()
    with get_conn() as conn:
        reestr_set_kv(conn, key, obj)
        conn.commit()


def employee_worker_fios():
    """ФИО соцработников из единой базы (для списков выбора в «Реестре»)."""
    ensure_seeded()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT fio, position FROM employees ORDER BY sort_order, n, id").fetchall()
    return [r["fio"] for r in rows if "работник" in (r["position"] or "").lower()]


# =================================== телефоны клиентов «Проверки качества»
def _pk_key(fio):
    """Ключ телефона: нормализуем только пробелы, регистр сохраняем (в отличие от
    _norm_fio, который приводит к нижнему регистру — тут ФИО должно остаться читаемым)."""
    return " ".join(str(fio or "").split())


def pk_phone_load(client_fio):
    ensure_seeded()
    with get_conn() as conn:
        r = conn.execute("SELECT phone FROM pk_phones WHERE client_fio=?",
                         (_pk_key(client_fio),)).fetchone()
    return r["phone"] if r and r["phone"] else ""


def pk_phone_save(client_fio, phone):
    key = _pk_key(client_fio)
    if not key:
        return
    ensure_seeded()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO pk_phones(client_fio, phone) VALUES(?,?) "
            "ON CONFLICT(client_fio) DO UPDATE SET phone=excluded.phone",
            (key, (phone or "").strip()))
        conn.commit()


def pk_phones_load_all():
    ensure_seeded()
    with get_conn() as conn:
        rows = conn.execute("SELECT client_fio, phone FROM pk_phones ORDER BY client_fio").fetchall()
    return {r["client_fio"]: r["phone"] for r in rows}


def pk_phone_delete(client_fio):
    ensure_seeded()
    with get_conn() as conn:
        conn.execute("DELETE FROM pk_phones WHERE client_fio=?", (_pk_key(client_fio),))
        conn.commit()


# =================================== соцработники «Заслушивания» функции «Планы»
def plany_worker_load(dept, year, month):
    """Сохранённый соцработник для (отд, год, месяц) или '' если не задан."""
    ensure_seeded()
    with get_conn() as conn:
        r = conn.execute(
            "SELECT worker FROM plany_workers WHERE dept=? AND year=? AND month=?",
            (str(dept), int(year), int(month))).fetchone()
    return r["worker"] if r and r["worker"] else ""


def plany_worker_save(dept, year, month, worker):
    ensure_seeded()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO plany_workers(dept, year, month, worker) VALUES(?,?,?,?) "
            "ON CONFLICT(dept, year, month) DO UPDATE SET worker=excluded.worker",
            (str(dept), int(year), int(month), (worker or "").strip()))
        conn.commit()


def plany_workers_load_all(dept, year):
    """Все заданные соцработники за год как {месяц: соцработник}."""
    ensure_seeded()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT month, worker FROM plany_workers WHERE dept=? AND year=?",
            (str(dept), int(year))).fetchall()
    return {int(r["month"]): r["worker"] for r in rows if r["worker"]}


# ======================================================= архив документов
def documents_add(feature, title, filename, params, content):
    """Сохранить сформированный документ (копию файла + параметры) в базу."""
    ensure_seeded()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO documents(feature,title,filename,created_at,params,content) "
            "VALUES(?,?,?,?,?,?)",
            (feature, title, filename,
             datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             json.dumps(params or {}, ensure_ascii=False), content))
        conn.commit()


def documents_last_params(feature):
    """Только параметры последнего документа функции, без загрузки всего архива."""
    ensure_seeded()
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT params FROM documents WHERE feature=? "
            "ORDER BY created_at DESC, id DESC LIMIT 1", (feature,)).fetchone()
    return row["params"] if row else None


def documents_list():
    """Список документов (без содержимого), новые сверху."""
    ensure_seeded()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, feature, title, filename, created_at, params, length(content) AS size "
            "FROM documents ORDER BY created_at DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


def documents_get(doc_id):
    """(filename, content_bytes) по id или (None, None)."""
    ensure_seeded()
    with get_conn() as conn:
        r = conn.execute(
            "SELECT filename, content FROM documents WHERE id=?", (doc_id,)).fetchone()
    return (r["filename"], r["content"]) if r else (None, None)


def documents_delete(doc_id):
    ensure_seeded()
    with get_conn() as conn:
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        conn.commit()
