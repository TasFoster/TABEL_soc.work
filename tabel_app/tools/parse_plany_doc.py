# -*- coding: utf-8 -*-
"""Одноразовый парсер планов .doc (через уже сохранённые DocBook XML) -> JSON-шаблон.

Читает scratchpad/xml/otd{5,9}_{01..12}.xml, строит plany_templates.json.
"""
import xml.etree.ElementTree as ET
import re, json, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

XML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'xml')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plany_templates.json')

MONTHS = {1:'январь',2:'февраль',3:'март',4:'апрель',5:'май',6:'июнь',
          7:'июль',8:'август',9:'сентябрь',10:'октябрь',11:'ноябрь',12:'декабрь'}

# Нормализация явных опечаток в исходниках (год плана = 2026). Прочие годы верны и
# сдвигаются единым offset при генерации. Ключ (отд, месяц) -> [(искать, заменить)].
NORMALIZE = {
    ('5', 1):  [('12.01.25', '12.01.26')],
    ('5', 9):  [('30.09.25', '30.09.26')],
    ('9', 7):  [('на июль 2024 года', 'на июль 2026 года')],
    ('9', 10): [('29.10.25', '29.10.26')],
}


def apply_norm(otd, m, s):
    for a, b in NORMALIZE.get((otd, m), ()):
        s = s.replace(a, b)
    return s


def load_xml(path):
    raw = open(path, encoding='utf-8').read()
    raw = re.sub(r'<!DOCTYPE.*?>', '', raw, flags=re.DOTALL)
    return ET.fromstring(raw)


def el_text(el):
    s = ''.join(el.itertext())
    s = s.replace('\xa0', ' ')
    s = re.sub(r'[ \t]*\n[ \t]*', ' ', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def classify_section(raw_title, rows, idx):
    """Каноническое название раздела по (ненадёжному) заголовку + содержимому строк.

    В исходниках отд.5 названия «Контроль»/«Работа с кадрами» часто теряются или
    сбиты (пустые/«зав. отделением»), поэтому раздел определяем по смыслу строк."""
    # Первый раздел всегда «Организационная работа» (в нём легитимно есть пункты
    # «Контроль за…» и «Поздравление…», поэтому по содержимому его не трогаем).
    if idx == 0:
        return 'Организационная работа'
    t = raw_title.strip().rstrip('.').strip().lower()
    joined = ' '.join(r[1] for r in rows).lower()
    if 'заслушивание' in joined or 'контрол' in t:
        return 'Контроль и качество'
    if 'кадр' in t or ('замен' in joined and 'отпуск' in joined):
        return 'Работа с кадрами'
    if 'юбилей' in t or 'мероприятия к' in t or any(
            k in joined for k in ('поздравлени', 'праздничн', 'юбилейн', 'блокадн', 'дню ')):
        return 'Мероприятия к юбилейным и праздничным датам, праздникам и акциям'
    if 'контрол' in joined:  # раздел контроля без «Заслушивания» и без явного названия
        return 'Контроль и качество'
    if 'организац' in t:
        return 'Организационная работа'
    return raw_title.strip() or 'Организационная работа'


def parse_tgroups(tgroups):
    """tgroup-ы всех таблиц последовательно.

    cols>=5 — строки данных; cols<5 — «разделитель». Разделитель с ТЕКСТОМ начинает
    новый раздел; ПУСТОЙ разделитель — это перенос раздела на новую страницу
    (продолжение текущего, не новый раздел). Пустые разделы без строк отбрасываются."""
    raw_sections = []
    col_widths = []
    current = None

    def ensure_current():
        nonlocal current
        if current is None:
            current = {'title': '', 'rows': []}
            raw_sections.append(current)

    for tg in tgroups:
        cols = int(tg.get('cols', '0'))
        if cols >= 5 and not col_widths:
            ws = [cs.get('colwidth', '') for cs in tg.findall('colspec')]
            col_widths.extend(ws[:5])  # только 5 значимых колонок (без артефактов)
        rows = [[el_text(e) for e in row.findall('entry')] for row in tg.findall('.//row')]
        if cols < 5:
            title = ''
            for r in rows:
                for cell in r:
                    if cell.strip():
                        title = cell.strip()
                        break
                if title:
                    break
            if title:  # реальный новый раздел
                current = {'title': title, 'rows': []}
                raw_sections.append(current)
            else:       # пустой разделитель = перенос страницы: продолжаем текущий
                ensure_current()
        else:
            for cells in rows:
                first = (cells[0] if cells else '').strip()
                second = (cells[1] if len(cells) > 1 else '').strip()
                if first == '№' or second == 'Мероприятия':
                    continue
                if not any(c.strip() for c in cells):
                    continue
                ensure_current()
                current['rows'].append((cells + [''] * 5)[:5])

    # отбросить пустые разделы, переименовать по содержимому
    sections = []
    for sec in raw_sections:
        if not sec['rows']:
            continue
        sec['title'] = classify_section(sec['title'], sec['rows'], len(sections))
        sections.append(sec)
    return sections, col_widths


def parse_file(path):
    root = load_xml(path)
    state = {'header': [], 'footer': [], 'after': False, 'tgroups': []}

    def walk(el, in_chapter=False):
        for c in list(el):
            if c.tag == 'bookinfo':
                continue  # метаданные книги (битая кодировка) — пропускаем
            if c.tag == 'informaltable':
                state['tgroups'].extend(c.findall('tgroup'))
                state['after'] = True
                continue
            nested = c.find('.//informaltable')
            if nested is not None and c.tag in ('para', 'title'):
                state['tgroups'].extend(nested.findall('tgroup'))
                state['after'] = True
                continue
            if c.tag in ('title', 'para'):
                if not in_chapter:
                    continue  # заголовок уровня книги — тоже метаданные
                txt = el_text(c)
                if txt:
                    (state['footer'] if state['after'] else state['header']).append(txt)
            else:
                walk(c, in_chapter or c.tag == 'chapter')
    walk(root)
    sections, widths = parse_tgroups(state['tgroups'])
    state['table'] = sections
    state['widths'] = widths
    return state


def extract_worker(sections):
    """Найти строку 'Заслушивание ... социального работника <ФИО>' -> (pos, prefix, worker, suffix)."""
    for si, sec in enumerate(sections):
        for ri, row in enumerate(sec['rows']):
            m = row[1]
            if 'Заслушивание' in m and 'работник' in m:
                mm = re.search(r'работник[а-яё]*\s+(.*?)(\s*о\s+(?:выполнени|проделанн|гос)|$)',
                               m, re.IGNORECASE)
                if mm and mm.group(1).strip():
                    w = mm.group(1).strip()
                    prefix = m[:mm.start(1)]
                    suffix = m[mm.start(1) + len(mm.group(1)):]
                    return [si, ri], prefix, w, suffix
                # имени нет — точка вставки после «работник...»
                am = re.search(r'работник[а-яё]*\s*', m, re.IGNORECASE)
                if am:
                    return [si, ri], m[:am.end()], '', m[am.end():]
                return [si, ri], m, '', ''
    return None, '', '', ''


def main():
    data = {'baseline_year': 2026, 'departments': {}}
    report = []
    for otd in ('5', '9'):
        dept = {'dept_no': otd, 'months': {}}
        for m in range(1, 13):
            path = os.path.join(XML_DIR, 'otd%s_%02d.xml' % (otd, m))
            st = parse_file(path)
            sections = st['table'] or []
            # нормализация опечаток
            st['header'] = [apply_norm(otd, m, x) for x in st['header']]
            st['footer'] = [apply_norm(otd, m, x) for x in st['footer']]
            for sec in sections:
                sec['title'] = apply_norm(otd, m, sec['title'])
                sec['rows'] = [[apply_norm(otd, m, c) for c in row] for row in sec['rows']]
            pos, prefix, worker, suffix = extract_worker(sections)
            month = {
                'month_name': MONTHS[m],
                'header': st['header'],
                'footer': st['footer'],
                'col_widths': st['widths'],
                'sections': sections,
                'sign_pos': pos,
                'sign_prefix': prefix,
                'sign_worker': worker,
                'sign_suffix': suffix,
            }
            dept['months'][str(m)] = month
            years = sorted(set(re.findall(r'\b(20\d\d)\b', ' '.join(st['header'] + st['footer'] +
                          [c for sec in sections for row in sec['rows'] for c in row]))))
            yy = sorted(set(re.findall(r'\d{1,2}\.\d{1,2}\.(\d\d)\b',
                          ' '.join(c for sec in sections for row in sec['rows'] for c in row))))
            nrows = sum(len(s['rows']) for s in sections)
            report.append('отд%s м%02d: разделов=%d строк=%d годы=%s ГГ=%s работник=%r' %
                          (otd, m, len(sections), nrows, ','.join(years), ','.join(sorted(set(yy))), worker))
        data['departments'][otd] = dept
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print('\n'.join(report))
    print('\nЗаписано:', OUT)


main()
