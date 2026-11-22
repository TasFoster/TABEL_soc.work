import re

_WORD = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
_NAME = rf"({_WORD}[ \t]+{_WORD}(?:[ \t]+{_WORD})?)"


def recipient(text):
    for pattern in (rf"Заказчик[ \t:\r\n]+{_NAME}(?=\s*(?:\n|$))",
                    rf"стороны,\s*и\s+{_NAME},\s*именуем"):
        match = re.search(pattern, text)
        if match:
            return "_".join(match[1].split())
    return None
