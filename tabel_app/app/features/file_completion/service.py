"""Контроллер проверки, преобразования и очереди файлов."""
import difflib
import re
import zipfile
from pathlib import Path
from . import rtf
TYPES = {'additional':'Договоры на дополнительные услуги', 'free':'Договоры на бесплатные услуги',
         'paid':'Договоры на государственные услуги — платные',
         'additional_act':'Акты на государственные и дополнительные услуги'}


def validate_rules(rules):
    for key in TYPES:
        for rule in rules[key]:
            if not isinstance(rule.get('before_variants', []), list) or any(
                not isinstance(v,str) or not v.strip() for v in rule.get('before_variants', [])):
                raise ValueError('before_variants должен содержать непустые строки.')
        rows = rules[key]
        if not rows or any(not isinstance(r.get('before'), str) or not r['before'].strip() or
                           not isinstance(r.get('after'), str) or not r['after'].strip() or
                           r['before'] == r['after'] or not isinstance(r.get('count'), int) or r['count']<1 for r in rows):
            raise ValueError('Укажите непустые разные before/after и положительное count для каждого типа.')


def locate(text, fragment):
    # Пробелы/переносы Word могут различаться, содержание должно совпадать.
    pattern = r'\s+'.join(re.escape(x) for x in fragment.split())
    return list(re.finditer(pattern, text))


def locate_before(text, rule):
    fragments = [rule['before']] + rule.get('before_variants', [])
    found = {(m.start(),m.end()):m for fragment in fragments for m in locate(text,fragment)}
    return [found[key] for key in sorted(found)]


def transform(raw, kind, rules):
    validate_rules(rules)
    parsed = rtf.parse(raw)
    text = parsed[0]
    if kind not in TYPES:
        raise ValueError('Неизвестный тип договора.')
    # Тип определяется заголовком внутри документа, а не именем файла.
    act = bool(re.search(r'Акт\s+сдачи[-–‑]при[её]мки\s+оказанных\s+'
                         r'(?:(?:государственных|дополнительных)\s+)?социальных\s+услуг'
                         r'|Акт\s+сдачи[-–‑]при[её]мки\s+оказанных\s+'
                         r'(?:государственных|дополнительных)\s+услуг', text, re.I))
    if act != (kind == 'additional_act'):
        raise ValueError('Тип документа не соответствует выбранному: акт или договор.')
    additional = 'Договор о предоставлении дополнительных социальных услуг' in text
    if not act and additional != (kind == 'additional'):
        raise ValueError('Тип договора не соответствует выбранному.')
    if kind in ('free','paid'):
        match = re.search(r'Стоимость\s+Услуг,\s+предусмотренных\s+настоящим\s+Договором,\s+составляет\s+([\d ,\.]+)', text)
        if not match:
            raise ValueError('Не найдена сумма договора для проверки типа.')
        zero = float(match[1].replace(' ','').replace(',','.')) == 0
        if zero != (kind == 'free'):
            raise ValueError('Сумма договора не соответствует выбранному типу.')
    states = []
    for rule in rules[kind]:
        before, after = locate_before(text,rule), locate(text,rule['after'])
        # after может содержать before (добавление предложения).
        covered = [b for b in before if not any(a.start()<=b.start() and b.end()<=a.end() for a in after)]
        if len(after)==rule['count'] and not covered:
            states.append('done')
        elif len(covered)==rule['count'] and not after:
            states.append('draft')
        else:
            raise ValueError('Неоднозначный или частично дополненный файл: проверьте текст и правила.')
    if all(s=='done' for s in states):
        return raw, 'Уже готов — пропущен', ''
    if any(s=='done' for s in states):
        raise ValueError('Часть дополнений уже внесена. Требуется ручная проверка.')
    result = raw
    for rule in rules[kind]:
        # При замене справа налево смещения слева остаются действительными.
        for m in reversed(locate_before(parsed[0], rule)):
            result = rtf.replace(result, m.start(), m.end(), rule['after'], parsed)
        parsed = rtf.parse(result)
    final = parsed[0]
    for rule in rules[kind]:
        if len(locate(final, rule['after'])) != rule['count']:
            raise ValueError('Не удалось проверить результат.')
    diff = '\n'.join(difflib.unified_diff(text.splitlines(),final.splitlines(),fromfile='Черновик',tofile='Результат',lineterm=''))
    return result, 'Готов к сохранению', diff


def read_inputs(paths):
    rows = []
    for path in paths:
        path = Path(path)
        try:
            if path.suffix.lower()=='.zip':
                with zipfile.ZipFile(path) as archive:
                    entries = [e for e in archive.infolist() if not e.is_dir()]
                    if len(entries)>2000 or sum(e.file_size for e in entries)>512_000_000:
                        raise ValueError('ZIP превышает 2000 файлов или 512 МБ.')
                    for entry in entries:
                        name = entry.filename
                        try:
                            if Path(name).suffix.lower()!='.rtf' or entry.file_size>32_000_000:
                                raise ValueError('Поддерживается только RTF до 32 МБ.')
                            rows.append({'name':path.name+' / '+name,'raw':archive.read(entry)})
                        except Exception as exc:
                            rows.append({'name':name,'error':str(exc)})
            else:
                if path.suffix.lower()!='.rtf' or path.stat().st_size>32_000_000:
                    raise ValueError('Поддерживается только RTF до 32 МБ.')
                rows.append({'name':path.name,'raw':path.read_bytes()})
        except Exception as exc:
            rows.append({'name':str(path),'error':str(exc)})
    return rows


def save_results(rows, destination, zipped=False):
    folder = Path(destination).parent if zipped else Path(destination)
    folder.mkdir(parents=True,exist_ok=True)
    outputs = {}
    for i,row in enumerate(rows,1):
        if row.get('result') is not None and row.get('changed'):
            # Плоские уникальные имена, без извлечения путей из ZIP.
            stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(row['name'].split(' / ')[-1]).stem).rstrip('. ')[:120] or 'договор'
            outputs[f'{i:03d}_{stem}_готовый.rtf'] = row['result']
    if not outputs:
        raise ValueError('Нет новых результатов для сохранения.')
    if zipped:
        target = Path(destination)
        if target.exists():
            raise ValueError('Выберите новое имя ZIP, чтобы сохранить исходники.')
        with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
            for name,content in outputs.items(): archive.writestr(name,content)
    else:
        if any((folder/name).exists() for name in outputs):
            raise ValueError('В папке уже есть результаты с такими именами. Выберите пустую папку.')
        for name,content in outputs.items():
            with (folder/name).open('xb') as stream: stream.write(content)
    return len(outputs)
