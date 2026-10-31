"""Utilitas waktu. Seluruh aplikasi memakai WIB (UTC+7, tanpa DST)."""
import calendar
from datetime import date, datetime, timedelta, timezone

from flask import current_app

WIB = timezone(timedelta(hours=7), "WIB")
DAYS_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
MONTHS_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
             "Agustus", "September", "Oktober", "November", "Desember"]


def now():
    fn = current_app.config.get("NOW_FUNC")
    return fn() if fn else datetime.now(WIB)


def today():
    return now().date()


def iso(dt):
    return dt.isoformat(timespec="seconds")


def parse_iso(value):
    return datetime.fromisoformat(value)


def _as_date(d):
    return date.fromisoformat(d) if isinstance(d, str) else d


def fmt_long(d):
    d = _as_date(d)
    return f"{DAYS_ID[d.weekday()]}, {d.day} {MONTHS_ID[d.month - 1]} {d.year}"


def fmt_short(d):
    return _as_date(d).strftime("%d/%m/%Y")


def fmt_day_month(d):
    d = _as_date(d)
    return f"{DAYS_ID[d.weekday()][:3]}, {d.day} {MONTHS_ID[d.month - 1][:3]}"


def fmt_time(value):
    if not value:
        return "-"
    if isinstance(value, str):
        value = parse_iso(value)
    return value.astimezone(WIB).strftime("%H:%M")


def fmt_datetime(value):
    if not value:
        return "-"
    if isinstance(value, str):
        value = parse_iso(value)
    value = value.astimezone(WIB)
    return f"{value.day} {MONTHS_ID[value.month - 1][:3]} {value.year}, {value:%H:%M} WIB"


def month_label(year, month):
    return f"{MONTHS_ID[month - 1]} {year}"


def month_range(year, month):
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def week_range(d):
    """Mengembalikan (senin, minggu) untuk tanggal `d`."""
    d = _as_date(d)
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def week_label(start, end):
    """Label rentang minggu dalam bahasa Indonesia (contoh: 26 Okt – 1 Nov 2026)."""
    start, end = _as_date(start), _as_date(end)
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS_ID[start.month - 1]} {start.year}"
    if start.year == end.year:
        return f"{start.day} {MONTHS_ID[start.month - 1][:3]} – {end.day} {MONTHS_ID[end.month - 1][:3]} {end.year}"
    return f"{start.day} {MONTHS_ID[start.month - 1][:3]} {start.year} – {end.day} {MONTHS_ID[end.month - 1][:3]} {end.year}"


def parse_date_arg(value, default):
    try:
        return date.fromisoformat(value) if value else default
    except (TypeError, ValueError):
        return default


def parse_week_arg(value, default):
    """Menerima tanggal YYYY-MM-DD (atau YYYY-Www) dan mengembalikan hari Senin pada minggu tersebut."""
    ref = default
    if value:
        try:
            if "-W" in str(value):
                ref = date.fromisocalendar(*[int(x) for x in str(value).split("-W")] + [1])
            else:
                ref = date.fromisoformat(str(value))
        except (TypeError, ValueError):
            ref = default
    monday, _ = week_range(ref)
    return monday


def parse_month_arg(value, default):
    """'2026-10' -> (2026, 10); nilai tidak valid memakai tahun/bulan dari `default` (date)."""
    try:
        y, m = value.split("-")
        y, m = int(y), int(m)
        if 2000 <= y <= 2100 and 1 <= m <= 12:
            return y, m
    except (AttributeError, ValueError):
        pass
    return default.year, default.month


def shift_month(year, month, delta):
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1
