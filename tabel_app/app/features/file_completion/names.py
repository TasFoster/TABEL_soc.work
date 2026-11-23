import re

_WORD = r"[А-ЯЁ][А-ЯЁа-яё]+(?:[-‑][А-ЯЁа-яё]+)*"
_NAME = rf"({_WORD}[ \t]+{_WORD}(?:[ \t]+{_WORD})?)"
_LABEL = r"(?:ф\.?\s*и\.?\s*о\.?\s+)?получател[ья](?:\s+социальных)?\s+услуг"
_SEPARATOR = r"[ \t]*(?:\(ФИО\))?[ \t]*[:—–-]?[ \t]*(?:\n[ \t]*)?"
_END = r"(?=[ \t]*(?:$|[,;(]))"


def recipient(text):
    text = text.replace("\xa0", " ").replace("\r", "")
    # Явное поле получателя имеет приоритет над реквизитами заказчика.
    for label in (_LABEL, r"заказчик"):
        pattern = rf"(?:^|\t)[ \t]*(?i:{label}){_SEPARATOR}{_NAME}{_END}"
        names = {"_".join(m[1].split()) for m in re.finditer(pattern, text, re.M)}
        if names:
            return names.pop() if len(names) == 1 else None
        if label == _LABEL and re.search(r"(?im)^\s*(?:законный\s+)?представитель\s*[:—–-]|действующ\w*\s+в\s+интересах", text):
            return None
    match = re.search(rf"стороны,\s*и\s+{_NAME},\s*именуем", text)
    return "_".join(match[1].split()) if match else None
