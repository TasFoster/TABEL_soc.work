"""Архив сформированных документов поверх core.db.

Каждый сформированный файл (всех функций) сохраняется КОПИЕЙ в базу (+ параметры),
чтобы позже открыть/пересохранить в окне «Сохранённые документы». Сохранение в базу
не должно мешать основной работе — ошибки глушатся.
"""

import json
import os
import tempfile

from . import db

FEATURE_TITLES = {
    "timesheet": "Табель",
    "reestr": "Реестр",
    "prilozhenie": "Приложение к табелю",
    "proezd": "Проезд",
    "uslugi_dengi": "Услуги-Деньги",
    "grafiki": "График проверок",
    "protokol": "Протокол",
}


def save_file(feature, file_path, params=None, title=None):
    """Сохранить копию готового файла в архив. True — успех."""
    try:
        with open(file_path, "rb") as f:
            content = f.read()
        name = os.path.basename(file_path)
        db.documents_add(feature, title or name, name, params, content)
        return True
    except Exception:  # noqa: BLE001 — архив не должен ломать формирование
        return False


def list_documents():
    return db.documents_list()


def parse_params(raw):
    """params (JSON-строка из БД) -> dict; пустой при ошибке."""
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}


def params_brief(raw):
    """Короткая человекочитаемая строка параметров документа (период/№/отделение)."""
    p = parse_params(raw)
    parts = []
    if p.get("number"):
        parts.append(f"№{p['number']}")
    if p.get("date"):
        parts.append(str(p["date"]))
    m, y = p.get("month"), p.get("year")
    try:
        if m and y:
            parts.append(f"{int(m):02d}.{y}")
        elif y:
            parts.append(str(y))
    except (ValueError, TypeError):
        pass
    if p.get("half"):
        parts.append(f"{p['half']}-е полуг.")
    period = {"first": "1–15", "second": "16–конец"}.get(p.get("period"))
    if period:
        parts.append(period)
    if p.get("dept"):
        parts.append(f"отд.№{p['dept']}")
    if p.get("worker"):
        parts.append(str(p["worker"])[:24])
    return " ".join(parts)


def last_params(feature):
    """Параметры последнего (самого свежего) документа функции из архива или {}."""
    for d in db.documents_list():   # отсортированы по дате DESC
        if d.get("feature") == feature:
            return parse_params(d.get("params"))
    return {}


def extract_to_temp(doc_id):
    """Извлечь документ во временный файл, вернуть путь (для открытия)."""
    name, content = db.documents_get(doc_id)
    if content is None:
        return None
    path = os.path.join(tempfile.gettempdir(), name or f"doc_{doc_id}")
    with open(path, "wb") as f:
        f.write(content)
    return path


def save_as(doc_id, dest_path):
    name, content = db.documents_get(doc_id)
    if content is None:
        return False
    with open(dest_path, "wb") as f:
        f.write(content)
    return True


def delete(doc_id):
    db.documents_delete(doc_id)
