"""Ручные показатели печатной формы, без изменения норм рабочего времени."""
import math

FIELDS = (("rate", "Ставка"), ("holiday_days", "Праздничные — дни"),
          ("holiday_hours", "Праздничные — часы"), ("night_days", "Ночные — дни"),
          ("night_hours", "Ночные — часы"))


def parse_indicators(raw, period_days):
    result = {}
    for key, label in FIELDS:
        text = str(raw.get(key, "")).strip().replace(",", ".")
        if not text:
            continue
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"{label}: введите число") from None
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{label}: требуется конечное неотрицательное число")
        if key.endswith('_days') and (not value.is_integer() or value > period_days):
            raise ValueError(f"{label}: целое число от 0 до {period_days}")
        if key.endswith('_hours') and value > period_days * 24:
            raise ValueError(f"{label}: больше часов, чем в выбранном периоде")
        result[key] = int(value) if value.is_integer() else value
    return result
