"""Производственный календарь РФ.

Определяет для каждой даты: рабочий день / выходной (или праздник) /
сокращённый предпраздничный день, а также норму часов.

Данные по годам хранятся в data/calendar.json:
    {
      "2026": {
        "holidays":   ["01-01", ...],   # нерабочие праздничные и перенесённые дни (MM-DD)
        "short_days": ["04-30", ...],    # сокращённые предпраздничные дни (минус 1 час)
        "work_days":  ["05-13", ...]     # перенесённые РАБОЧИЕ дни (рабочая суббота/среда)
      }
    }
Обычные суббота/воскресенье определяются автоматически по дню недели.
work_days — это перенесённые рабочие дни (например рабочая суббота или рабочая
среда по переносу): они считаются рабочими, даже если выпали на выходной.
"""

import datetime

MONTHS_NOM = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


def month_title(month, year):
    """Заголовок месяца как в табеле, напр. 'Май 2026 года'."""
    return f"{MONTHS_NOM[month]} {year} года"


class ProductionCalendar:
    def __init__(self, data, full_hours=8, short_hours=7):
        self.data = data or {}
        self.full_hours = full_hours
        self.short_hours = short_hours

    def has_year(self, year):
        return str(year) in self.data

    def _year(self, year):
        return self.data.get(str(year), {})

    def _key(self, d):
        return f"{d.month:02d}-{d.day:02d}"

    def is_holiday(self, d):
        return self._key(d) in self._year(d.year).get("holidays", [])

    def is_short(self, d):
        return self._key(d) in self._year(d.year).get("short_days", [])

    def is_extra_workday(self, d):
        """Перенесённый рабочий день (рабочая суббота/среда по переносу)."""
        return self._key(d) in self._year(d.year).get("work_days", [])

    @staticmethod
    def is_weekend(d):
        return d.weekday() >= 5  # 5 = суббота, 6 = воскресенье

    def is_workday(self, d):
        if self.is_extra_workday(d):
            return True
        return not (self.is_weekend(d) or self.is_holiday(d))

    def hours(self, d):
        """Норма часов для рабочего дня (0 для выходного/праздника)."""
        if not self.is_workday(d):
            return 0
        return self.short_hours if self.is_short(d) else self.full_hours
