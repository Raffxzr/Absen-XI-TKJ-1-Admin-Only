"""Logika presensi: pencatatan cepat (Tandai Semua Hadir), ubah status cepat, koreksi audit, dan laporan harian/mingguan/bulanan."""
import sqlite3
from datetime import timedelta

from .. import timeutil

STATUSES = {"H": "Hadir", "I": "Izin", "S": "Sakit", "A": "Alpa"}
STATUS_ORDER = ("H", "I", "S", "A")


def get_record(db, student_id, att_date):
    return db.execute("SELECT * FROM attendance_records WHERE student_id = ? AND att_date = ?",
                      (student_id, str(att_date))).fetchone()


def student_history(db, student_id, start=None, end=None, limit=None):
    sql = ("""SELECT r.*, u.full_name AS by_name,
                     EXISTS(SELECT 1 FROM attendance_corrections c WHERE c.record_id = r.id) AS corrected
                FROM attendance_records r
           LEFT JOIN users u ON u.id = r.updated_by
               WHERE r.student_id = ?""")
    args = [student_id]
    if start:
        sql += " AND r.att_date >= ?"
        args.append(str(start))
    if end:
        sql += " AND r.att_date <= ?"
        args.append(str(end))
    sql += " ORDER BY r.att_date DESC"
    if limit:
        sql += " LIMIT ?"
        args.append(limit)
    return db.execute(sql, args).fetchall()


def effective_days(db, start, end):
    """Hari efektif = tanggal yang memiliki minimal satu catatan presensi di kelas."""
    return db.execute("SELECT COUNT(DISTINCT att_date) FROM attendance_records WHERE att_date BETWEEN ? AND ?",
                      (str(start), str(end))).fetchone()[0]


def student_month_summary(db, student_id, year, month):
    start, end = timeutil.month_range(year, month)
    counts = {k: 0 for k in STATUS_ORDER}
    for row in db.execute("SELECT status, COUNT(*) n FROM attendance_records WHERE student_id = ? "
                          "AND att_date BETWEEN ? AND ? GROUP BY status", (student_id, str(start), str(end))):
        counts[row["status"]] = row["n"]
    eff = effective_days(db, start, end)
    belum = max(eff - sum(counts.values()), 0)
    pct = round(counts["H"] * 100 / eff, 1) if eff else None
    return {"counts": counts, "effective_days": eff, "belum": belum, "pct": pct,
            "year": year, "month": month}


def corrections_for_student(db, student_id, limit=20):
    return db.execute(
        """SELECT c.*, r.att_date, u.full_name AS by_name FROM attendance_corrections c
             JOIN attendance_records r ON r.id = c.record_id JOIN users u ON u.id = c.corrected_by
            WHERE r.student_id = ? ORDER BY c.corrected_at DESC, c.id DESC LIMIT ?""", (student_id, limit)).fetchall()


# ---------------------------------------------------------------- ringkasan harian (admin)
def day_overview(db, d, q=None, status=None, student_id=None):
    sql = """SELECT s.id AS student_id, s.full_name, s.is_active, s.roll_no, s.nis,
                    r.id AS record_id, r.status, r.note, r.submitted_at, r.source, r.updated_at,
                    u.full_name AS by_name,
                    EXISTS(SELECT 1 FROM attendance_corrections c WHERE c.record_id = r.id) AS corrected
               FROM students s
          LEFT JOIN attendance_records r ON r.student_id = s.id AND r.att_date = ?
          LEFT JOIN users u ON u.id = r.updated_by
              WHERE (s.is_active = 1 OR r.id IS NOT NULL)"""
    args = [str(d)]
    if q:
        sql += " AND s.name_key LIKE ? ESCAPE '\\'"
        args.append("%" + q.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if student_id:
        sql += " AND s.id = ?"
        args.append(student_id)
    if status == "belum":
        sql += " AND r.id IS NULL"
    elif status in STATUSES:
        sql += " AND r.status = ?"
        args.append(status)
    sql += " ORDER BY (s.roll_no IS NULL), s.roll_no, s.full_name"
    return db.execute(sql, args).fetchall()


def day_stats(rows):
    counts = {k: 0 for k in STATUS_ORDER}
    belum = 0
    for r in rows:
        if r["status"]:
            counts[r["status"]] += 1
        else:
            belum += 1
    total = len(rows)
    pct = round(counts["H"] * 100 / total, 1) if total else None
    return {"total": total, "counts": counts, "belum": belum, "pct": pct,
            "tercatat": total - belum}


# ---------------------------------------------------------------- tombol cepat: tandai semua hadir & ubah cepat
def mark_all_present(db, att_date, user_id, now):
    """Mencatat seluruh siswa aktif yang belum memiliki presensi pada `att_date` sebagai Hadir (H).
    Siswa yang sudah dicatat (mis. Izin/Sakit/Alpa) tidak ditimpa, dan seluruh status tetap bisa
    langsung diedit setelahnya."""
    if att_date > now.date():
        return False, 0, "Tanggal di masa depan belum dapat diisi presensi."
    missing = db.execute(
        """SELECT s.id FROM students s
            WHERE s.is_active = 1 AND NOT EXISTS (
                SELECT 1 FROM attendance_records r WHERE r.student_id = s.id AND r.att_date = ?
            ) ORDER BY s.roll_no, s.full_name""",
        (str(att_date),)).fetchall()
    if not missing:
        return True, 0, "Semua siswa aktif sudah tercatat pada tanggal ini. Silakan ubah status siswa yang tidak masuk pada tabel."
    ts = timeutil.iso(now)
    try:
        for row in missing:
            db.execute(
                """INSERT INTO attendance_records(student_id, att_date, status, note, submitted_at, source, updated_at, updated_by)
                   VALUES (?, ?, 'H', NULL, ?, 'admin', ?, ?)""",
                (row["id"], str(att_date), ts, ts, user_id))
        db.commit()
    except sqlite3.Error:
        db.rollback()
        raise
    return True, len(missing), (
        f"{len(missing)} siswa berhasil ditandai Hadir. "
        "Silakan ubah status pada baris siswa yang tidak masuk (Izin, Sakit, atau Alpa)."
    )


def quick_set_status(db, student_id, att_date, new_status, new_note, user_id, now):
    """Mengubah atau mencatat status presensi satu siswa secara cepat langsung dari tabel presensi.
    Bila mengubah catatan yang sudah ada (mis. dari Hadir ke Sakit/Izin/Alpa setelah Tandai Semua Hadir),
    perubahan otomatis dicatat di attendance_corrections."""
    new_status = (new_status or "").upper()
    new_note = " ".join((new_note or "").split()) or None
    if new_status not in STATUSES:
        return False, "Pilih status presensi yang valid (Hadir, Izin, Sakit, atau Alpa)."
    if new_note and len(new_note) > 200:
        return False, "Keterangan maksimal 200 karakter."
    if att_date > now.date():
        return False, "Tanggal presensi tidak boleh di masa depan."
    student = db.execute("SELECT id, full_name FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        return False, "Siswa tidak ditemukan."

    ts = timeutil.iso(now)
    try:
        existing = get_record(db, student_id, att_date)
        if existing:
            if existing["status"] == new_status and (existing["note"] or None) == new_note:
                return True, f"Status {student['full_name']} tetap {STATUSES[new_status]}."
            db.execute(
                "UPDATE attendance_records SET status = ?, note = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                (new_status, new_note, ts, user_id, existing["id"]))
            reason = f"Perubahan cepat di daftar presensi ({STATUSES[existing['status']]} → {STATUSES[new_status]})"
            db.execute(
                """INSERT INTO attendance_corrections(record_id, old_status, new_status, old_note, new_note, reason, corrected_by, corrected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (existing["id"], existing["status"], new_status, existing["note"], new_note, reason, user_id, ts))
        else:
            db.execute(
                """INSERT INTO attendance_records(student_id, att_date, status, note, submitted_at, source, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, ?, 'admin', ?, ?)""",
                (student_id, str(att_date), new_status, new_note, ts, ts, user_id))
        db.commit()
    except sqlite3.Error:
        db.rollback()
        raise
    return True, f"Presensi {student['full_name']} disimpan sebagai {STATUSES[new_status]}."


# ---------------------------------------------------------------- koreksi detail
def correct_record(db, student_id, att_date, new_status, new_note, reason, user_id, now):
    """Buat/ubah catatan presensi lewat halaman Koreksi Detail. Setiap perubahan dicatat di
    attendance_corrections beserta siapa dan kapan. Mengembalikan (ok, pesan)."""
    new_status = (new_status or "").upper()
    reason = " ".join((reason or "").split())
    new_note = " ".join((new_note or "").split()) or None
    if new_status not in STATUSES:
        return False, "Pilih status presensi yang valid."
    if len(reason) < 3:
        return False, "Alasan perubahan wajib diisi (minimal 3 karakter)."
    if len(reason) > 300 or (new_note and len(new_note) > 200):
        return False, "Alasan maksimal 300 karakter dan keterangan maksimal 200 karakter."
    if att_date > now.date():
        return False, "Tanggal presensi tidak boleh di masa depan."
    if not db.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone():
        return False, "Siswa tidak ditemukan."

    ts = timeutil.iso(now)
    try:
        existing = get_record(db, student_id, att_date)
        if existing:
            if existing["status"] == new_status and (existing["note"] or None) == new_note:
                return False, "Tidak ada perubahan pada status maupun keterangan."
            db.execute("UPDATE attendance_records SET status = ?, note = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                       (new_status, new_note, ts, user_id, existing["id"]))
            record_id, old_status, old_note = existing["id"], existing["status"], existing["note"]
        else:
            cur = db.execute(
                "INSERT INTO attendance_records(student_id, att_date, status, note, submitted_at, source, updated_at, updated_by) "
                "VALUES (?,?,?,?,?, 'admin', ?, ?)", (student_id, str(att_date), new_status, new_note, ts, ts, user_id))
            record_id, old_status, old_note = cur.lastrowid, None, None
        db.execute("INSERT INTO attendance_corrections(record_id, old_status, new_status, old_note, new_note, reason, corrected_by, corrected_at) "
                   "VALUES (?,?,?,?,?,?,?,?)", (record_id, old_status, new_status, old_note, new_note, reason, user_id, ts))
        db.commit()
    except sqlite3.Error:
        db.rollback()
        raise
    return True, "Perubahan presensi tersimpan dan dicatat dalam riwayat."


def mark_missing_alpa(db, att_date, user_id, settings, now):
    """Tandai Alpa untuk semua siswa aktif yang belum punya catatan pada tanggal tertentu."""
    if att_date > now.date():
        return 0, "Tanggal di masa depan tidak dapat ditandai."
    missing = db.execute(
        """SELECT s.id FROM students s
            WHERE s.is_active = 1 AND NOT EXISTS (SELECT 1 FROM attendance_records r
                  WHERE r.student_id = s.id AND r.att_date = ?)""", (str(att_date),)).fetchall()
    if not missing:
        return 0, "Tidak ada siswa yang belum tercatat pada tanggal ini."
    ts = timeutil.iso(now)
    try:
        for row in missing:
            cur = db.execute(
                "INSERT INTO attendance_records(student_id, att_date, status, note, submitted_at, source, updated_at, updated_by) "
                "VALUES (?,?, 'A', 'Tidak hadir tanpa keterangan', ?, 'admin', ?, ?)",
                (row["id"], str(att_date), ts, ts, user_id))
            db.execute("INSERT INTO attendance_corrections(record_id, old_status, new_status, old_note, new_note, reason, corrected_by, corrected_at) "
                       "VALUES (?, NULL, 'A', NULL, 'Tidak hadir tanpa keterangan', 'Penandaan Alpa massal untuk siswa yang belum tercatat', ?, ?)",
                       (cur.lastrowid, user_id, ts))
        db.commit()
    except sqlite3.Error:
        db.rollback()
        raise
    return len(missing), f"{len(missing)} siswa ditandai Alpa."


# ---------------------------------------------------------------- laporan mingguan & bulanan
def _period_matrix(db, start, end):
    """Helper bersama untuk menyusun matriks rekap rentang tanggal [start, end]."""
    days = [r[0] for r in db.execute(
        "SELECT DISTINCT att_date FROM attendance_records WHERE att_date BETWEEN ? AND ? ORDER BY att_date",
        (str(start), str(end)))]
    records = {}
    for r in db.execute("SELECT student_id, att_date, status FROM attendance_records WHERE att_date BETWEEN ? AND ?",
                        (str(start), str(end))):
        records.setdefault(r["student_id"], {})[r["att_date"]] = r["status"]
    students = db.execute(
        """SELECT s.id AS student_id, s.full_name, s.roll_no, s.is_active
             FROM students s
         ORDER BY (s.roll_no IS NULL), s.roll_no, s.full_name""").fetchall()
    rows = []
    for st in students:
        cells = records.get(st["student_id"], {})
        if not st["is_active"] and not cells:
            continue
        counts = {k: 0 for k in STATUS_ORDER}
        for v in cells.values():
            counts[v] += 1
        belum = len(days) - sum(counts.values())
        rows.append({
            "student_id": st["student_id"],
            "full_name": st["full_name"],
            "roll_no": st["roll_no"],
            "counts": counts,
            "belum": belum,
            "cells": cells,
            "pct": round(counts["H"] * 100 / len(days), 1) if days else None,
        })
    totals = {k: sum(r["counts"][k] for r in rows) for k in STATUS_ORDER}
    class_pct = round(totals["H"] * 100 / (len(days) * len(rows)), 1) if days and rows else None
    return {
        "days": days,
        "rows": rows,
        "totals": totals,
        "belum_total": sum(r["belum"] for r in rows),
        "class_pct": class_pct,
    }


def week_report(db, ref_date):
    """Rekap presensi mingguan (Senin s.d. Minggu pada minggu `ref_date`)."""
    start, end = timeutil.week_range(ref_date)
    base = _period_matrix(db, start, end)
    # Tampilkan Senin-Jumat secara baku, tambah Sabtu/Minggu bila ada catatan presensi di hari tersebut
    active_set = set(base["days"])
    week_days = []
    for i in range(7):
        d = (start + timedelta(days=i)).isoformat()
        if i < 5 or d in active_set:
            week_days.append(d)
    base.update({
        "start": start,
        "end": end,
        "week_days": week_days,
        "label": timeutil.week_label(start, end),
    })
    return base


def month_report(db, year, month):
    start, end = timeutil.month_range(year, month)
    base = _period_matrix(db, start, end)
    base.update({"year": year, "month": month})
    return base
