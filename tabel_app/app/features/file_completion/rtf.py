"""Текст RTF с координатами исходных токенов для правок без пересборки таблиц."""
import re
TOKEN = re.compile(r"\\'([0-9a-fA-F]{2})|\\([a-zA-Z]+)(-?\d+)? ?|\\([^a-zA-Z])|([{}])|([^\\{}\r\n]+)")
SKIP = {'fonttbl','colortbl','stylesheet','info','pict','object','header','footer',
        'listtable','listoverridetable','rsidtbl','themedata','colorschememapping','xmlnstbl','datastore'}


def parse(raw):
    if not raw.startswith(b'{\\rtf') or len(raw) > 32_000_000:
        raise ValueError('Ожидается RTF до 32 МБ.')
    source = raw.decode('latin1')
    out, spans, stack = [], [], []
    skip, uc, fallback = False, 1, 0
    def emit(text, start, end):
        nonlocal fallback
        if skip:
            return
        if fallback:
            fallback -= 1
            return
        for ch in text:
            out.append(ch); spans.append((start, end))
    for m in TOKEN.finditer(source):
        hexa, word, arg, symbol, brace, plain = m.groups()
        if brace == '{':
            stack.append((skip, uc))
        elif brace == '}':
            if not stack:
                raise ValueError('Нарушена структура RTF.')
            skip, uc = stack.pop()
        elif hexa:
            emit(bytes.fromhex(hexa).decode('cp1251'), m.start(), m.end())
        elif word:
            if word in SKIP:
                skip = True
            elif word == 'bin':
                raise ValueError('RTF с двоичными объектами не поддерживается.')
            elif word == 'uc':
                uc = int(arg)
            elif word == 'u' and not skip:
                fallback = 0
                emit(chr(int(arg) % 65536), m.start(), m.end())
                fallback = uc
            elif word in ('par','line','cell','row','tab'):
                emit('\t' if word in ('cell','tab') else '\n', m.start(), m.end())
        elif symbol:
            if symbol == '*':
                skip = True
            elif symbol in ('\\','{','}'):
                emit(symbol, m.start(), m.end())
            elif symbol == '~':
                emit('\u00a0', m.start(), m.end())
        elif plain:
            for offset,ch in enumerate(plain):
                emit(ch.encode('latin1').decode('cp1251'), m.start()+offset, m.start()+offset+1)
    if stack:
        raise ValueError('Незавершённый RTF.')
    return ''.join(out), spans


def escape(text):
    return ''.join('\\par ' if ch == '\n' else '\\'+ch if ch in '\\{}' else
                   ch if ord(ch)<128 else '\\u%d?' % (ord(ch) if ord(ch)<32768 else ord(ch)-65536)
                   for ch in text)


def replace(raw, start, end, replacement, parsed=None):
    text, spans = parsed if parsed is not None else parse(raw)
    tokens = sorted(set(spans[start:end]))
    if '\n' in text[start:end] and '\n' not in replacement:
        # При схлопывании нескольких абзацев их поздние \pard сбрасывают
        # нумерацию первого абзаца, хотя видимый listtext «11.» остаётся.
        # Убираем настройки удаляемых абзацев вместе с их текстом.
        paragraph_words = {'pard', 's', 'ls', 'ilvl', 'fi', 'li', 'ri', 'lin', 'rin',
                           'sb', 'sa', 'sl', 'slmult', 'ql', 'qr', 'qj', 'qc',
                           'tx', 'keep', 'keepn', 'widctlpar', 'nowidctlpar',
                           'outlinelevel', 'contextualspace'}
        lower, upper = tokens[0][0], tokens[-1][1]
        for match in TOKEN.finditer(raw.decode('latin1'), lower, upper):
            if match.group(2) in paragraph_words:
                tokens.append((match.start(), match.end()))
        tokens = sorted(set(tokens))
    if not tokens:
        raise ValueError('Пустая область замены.')
    # Удаляются только текстовые токены, управляющие группы и стили остаются.
    source = raw.decode('latin1')
    parts = [source[:tokens[0][0]], escape(replacement)]
    cursor = tokens[0][0]
    for a, b in tokens:
        parts.append(source[cursor:a])
        if source.startswith('\\u', a) and source[b:b + 1] == '?':
            b += 1
        cursor = b
    parts.append(source[cursor:])
    return ''.join(parts).encode('latin1')
