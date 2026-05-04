"""
Period filter utilities.
Computes (start_date, end_date) for the 9 supported period options.
All ranges are inclusive on both ends.
"""

from datetime import date, datetime, timedelta
from typing import Tuple

PERIOD_OPTIONS = [
    "Esta semana",
    "Semana pasada",
    "Este mes",
    "Mes pasado",
    "Este trimestre",
    "Trimestre pasado",
    "Este semestre",
    "Este año",
    "Año pasado",
]


def _quarter_bounds(year: int, q_index: int) -> Tuple[date, date]:
    """q_index: 0=Q1, 1=Q2, 2=Q3, 3=Q4"""
    start_month = q_index * 3 + 1
    end_month = start_month + 2
    start = date(year, start_month, 1)
    if end_month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, end_month + 1, 1) - timedelta(days=1)
    return start, end


def get_period_dates(period: str, ref: date | None = None) -> Tuple[date, date]:
    """Return (start_date, end_date) inclusive."""
    today = ref or date.today()

    if period == "Esta semana":
        start = today - timedelta(days=today.weekday())  # Monday
        return start, today

    if period == "Semana pasada":
        last_sunday = today - timedelta(days=today.weekday() + 1)
        last_monday = last_sunday - timedelta(days=6)
        return last_monday, last_sunday

    if period == "Este mes":
        return today.replace(day=1), today

    if period == "Mes pasado":
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        start = end.replace(day=1)
        return start, end

    if period == "Este trimestre":
        q = (today.month - 1) // 3
        start = date(today.year, q * 3 + 1, 1)
        return start, today

    if period == "Trimestre pasado":
        q = (today.month - 1) // 3
        if q == 0:
            return _quarter_bounds(today.year - 1, 3)
        return _quarter_bounds(today.year, q - 1)

    if period == "Este semestre":
        if today.month <= 6:
            return date(today.year, 1, 1), today
        return date(today.year, 7, 1), today

    if period == "Este año":
        return date(today.year, 1, 1), today

    if period == "Año pasado":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)

    raise ValueError(f"Periodo desconocido: {period}")


def to_ms(d: date) -> int:
    """Convert a date to UTC midnight millis (HubSpot search filter format)."""
    return int(datetime(d.year, d.month, d.day).timestamp() * 1000)


def to_ms_end(d: date) -> int:
    """End-of-day millis (inclusive upper bound)."""
    dt = datetime(d.year, d.month, d.day, 23, 59, 59)
    return int(dt.timestamp() * 1000)
