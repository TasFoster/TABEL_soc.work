"""Число прописью по-русски (рубли и копейки)."""

_UNITS = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_UNITS_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
          "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят",
         "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот",
             "семьсот", "восемьсот", "девятьсот"]


def _triple(n, female=False):
    units = _UNITS_F if female else _UNITS
    words = []
    h, rem = divmod(n, 100)
    if h:
        words.append(_HUNDREDS[h])
    if 10 <= rem <= 19:
        words.append(_TEENS[rem - 10])
    else:
        t, u = divmod(rem, 10)
        if t:
            words.append(_TENS[t])
        if u:
            words.append(units[u])
    return words


def _plural(n, forms):
    """forms = (1, 2, 5): рубль/рубля/рублей."""
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


_SCALES = [
    ("", "", False),
    ("тысяча", "тысячи", True),     # тысячи — женский род
    ("миллион", "миллиона", False),
    ("миллиард", "миллиарда", False),
]


def int_in_words(n, female=False):
    """Целое число прописью: 44 -> 'сорок четыре', 1626 -> 'одна тысяча шестьсот…'."""
    n = int(n)
    if n == 0:
        return "ноль"
    groups = []
    x = n
    while x > 0:
        groups.append(x % 1000)
        x //= 1000
    words = []
    for idx in range(len(groups) - 1, -1, -1):
        g = groups[idx]
        if g == 0:
            continue
        words += _triple(g, female=(idx == 1) or (female and idx == 0))
        if idx == 1:
            words.append(_plural(g, ("тысяча", "тысячи", "тысяч")))
        elif idx == 2:
            words.append(_plural(g, ("миллион", "миллиона", "миллионов")))
        elif idx == 3:
            words.append(_plural(g, ("миллиард", "миллиарда", "миллиардов")))
    return " ".join(w for w in words if w)


def rubles_kopecks_in_words(amount):
    """Напр. 34599.0 -> 'тридцать четыре тысячи пятьсот девяносто девять рублей 00 копеек'.
    Рубли — прописью, копейки — цифрами (как в исходном документе)."""
    amount = round(float(amount) + 1e-9, 2)
    rub = int(amount)
    kop = int(round((amount - rub) * 100))

    if rub == 0:
        words = ["ноль"]
    else:
        words = []
        groups = []
        n = rub
        while n > 0:
            groups.append(n % 1000)
            n //= 1000
        for idx in range(len(groups) - 1, -1, -1):
            g = groups[idx]
            if g == 0:
                continue
            scale_word, scale_word2, female = _SCALES[idx] if idx < len(_SCALES) else ("", "", False)
            words += _triple(g, female=female and idx == 1)
            if idx == 1:
                words.append(_plural(g, ("тысяча", "тысячи", "тысяч")))
            elif idx == 2:
                words.append(_plural(g, ("миллион", "миллиона", "миллионов")))
            elif idx == 3:
                words.append(_plural(g, ("миллиард", "миллиарда", "миллиардов")))

    rub_word = _plural(rub, ("рубль", "рубля", "рублей"))
    text = " ".join(w for w in words if w)
    return f"{text} {rub_word} {kop:02d} копеек"
