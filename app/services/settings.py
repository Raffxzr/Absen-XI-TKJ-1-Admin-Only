"""Pengaturan jadwal sesi presensi dan informasi kelas."""
import re
from datetime import datetime

from .. import timeutil

DAY_KEYS = range(7)  # 0 = Senin ... 6 = Minggu
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

DEFAULTS = {}
for _i in DAY_KEYS:
    DEFAULTS[f"sched_{_i}_open"] = ""
    DEFAULTS[f"sched_{_i}_close"] = ""


def load(db):
    data = dict(DEFAULTS)
    for row in db.execute("SELECT key, value FROM settings"):
        if row["key"] in data:
            data[row["key"]] = row["value"]
    return data


def save(db, updates):
    for key, value in updates.items():
        if key in DEFAULTS:
            db.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                       "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    db.commit()


def validate_form(form):
    """Validasi isian halaman Pengaturan. Mengembalikan (nilai_bersih, daftar_error)."""
    clean, errors = {}, []
    for i in DAY_KEYS:
        name = timeutil.DAYS_ID[i]
        o = (form.get(f"sched_{i}_open") or "").strip()
        c = (form.get(f"sched_{i}_close") or "").strip()
        if not o and not c:
            clean[f"sched_{i}_open"] = clean[f"sched_{i}_close"] = ""
            continue
        if not (TIME_RE.match(o) and TIME_RE.match(c)):
            errors.append(f"{name}: isi jam buka dan jam tutup dengan format JJ:MM (contoh 06:30), atau kosongkan keduanya.")
            continue
        if o >= c:
            errors.append(f"{name}: jam tutup harus lebih akhir dari jam buka.")
            continue
        clean[f"sched_{i}_open"], clean[f"sched_{i}_close"] = o, c
    return clean, errors


def window_for(settings, d):
    """Jadwal (buka, tutup) berupa string 'HH:MM' untuk tanggal d, atau None bila tidak diatur."""
    o, c = settings.get(f"sched_{d.weekday()}_open", ""), settings.get(f"sched_{d.weekday()}_close", "")
    return (o, c) if o and c else None


def window_state(settings, now):
    """Status jadwal sesi presensi pada waktu `now`:
    unset (jadwal belum diatur), off (tidak ada sesi hari ini), before, open, after."""
    if not any(settings.get(f"sched_{i}_open") for i in DAY_KEYS):
        return {"state": "unset", "open": None, "close": None, "seconds_left": 0,
                "message": "Jadwal jam presensi opsional belum diatur. Admin tetap dapat mencatat presensi kapan saja."}
    win = window_for(settings, now.date())
    if not win:
        return {"state": "off", "open": None, "close": None, "seconds_left": 0,
                "message": "Tidak ada jadwal sesi rutin hari ini."}
    o, c = win
    open_dt = datetime.combine(now.date(), datetime.strptime(o, "%H:%M").time(), tzinfo=now.tzinfo)
    close_dt = datetime.combine(now.date(), datetime.strptime(c, "%H:%M").time(), tzinfo=now.tzinfo)
    if now < open_dt:
        return {"state": "before", "open": o, "close": c, "seconds_left": 0,
                "message": f"Jadwal sesi presensi dimulai pukul {o} WIB."}
    if now >= close_dt:
        return {"state": "after", "open": o, "close": c, "seconds_left": 0,
                "message": f"Jadwal sesi presensi hari ini telah selesai ({o}–{c} WIB)."}
    return {"state": "open", "open": o, "close": c, "seconds_left": int((close_dt - now).total_seconds()),
            "message": f"Sesi presensi sedang berlangsung sampai pukul {c} WIB."}
