"""Manajemen data master siswa kelas (tanpa akun login siswa)."""
import re
import sqlite3

from .. import security, timeutil

NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ .,'’\-]{1,98}[A-Za-zÀ-ÖØ-öø-ÿ.]$")
NIS_RE = re.compile(r"^[0-9A-Za-z.\-]{3,20}$")


def list_students(db, q=None, status="semua"):
    sql = """SELECT s.id, s.full_name, s.is_active, s.roll_no, s.nis, s.created_at
               FROM students s WHERE 1=1"""
    args = []
    if q:
        sql += " AND s.name_key LIKE ? ESCAPE '\\'"
        args.append("%" + q.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if status == "aktif":
        sql += " AND s.is_active = 1"
    elif status == "nonaktif":
        sql += " AND s.is_active = 0"
    sql += " ORDER BY (s.roll_no IS NULL), s.roll_no, s.full_name"
    return db.execute(sql, args).fetchall()


def get_student(db, student_id):
    return db.execute(
        """SELECT s.id, s.full_name, s.is_active, s.created_at, s.roll_no, s.nis, s.class_id
             FROM students s WHERE s.id = ?""", (student_id,)).fetchone()


def counts(db):
    row = db.execute("SELECT COUNT(*) total, COALESCE(SUM(s.is_active),0) aktif FROM students s").fetchone()
    return {"total": row["total"], "aktif": row["aktif"], "nonaktif": row["total"] - row["aktif"]}


def _validate(db, full_name, roll_no, nis, exclude_id=None):
    errors = {}
    name = security.clean_name(full_name)
    if not NAME_RE.match(name):
        errors["full_name"] = "Nama lengkap 3–100 karakter, hanya huruf, spasi, titik, koma, apostrof, dan tanda hubung."
    else:
        dup = db.execute("SELECT id FROM students WHERE name_key = ?", (security.name_key(name),)).fetchone()
        if dup and dup["id"] != exclude_id:
            errors["full_name"] = ("Nama ini sudah terdaftar di kelas. Bedakan dengan tambahan yang tetap, "
                                   "misalnya inisial nama orang tua atau tanda (B) di akhir nama.")
    roll = None
    if str(roll_no or "").strip():
        if not re.fullmatch(r"\d{1,3}", str(roll_no).strip()) or int(roll_no) < 1:
            errors["roll_no"] = "Nomor absen harus angka 1–999."
        else:
            roll = int(roll_no)
            dup = db.execute(
                "SELECT id FROM students WHERE roll_no = ? AND class_id = (SELECT id FROM classes ORDER BY id LIMIT 1)",
                (roll,)).fetchone()
            if dup and dup["id"] != exclude_id:
                errors["roll_no"] = f"Nomor absen {roll} sudah dipakai siswa lain."
    nis = (nis or "").strip() or None
    if nis:
        if not NIS_RE.match(nis):
            errors["nis"] = "NIS 3–20 karakter (huruf, angka, titik, atau tanda hubung)."
        else:
            dup = db.execute("SELECT id FROM students WHERE nis = ?", (nis,)).fetchone()
            if dup and dup["id"] != exclude_id:
                errors["nis"] = "NIS ini sudah terdaftar pada siswa lain."
    return name, roll, nis, errors


def create_student(db, class_id, full_name, roll_no=None, nis=None):
    """Menambahkan data siswa baru. Mengembalikan (student_id, errors)."""
    name, roll, nis, errors = _validate(db, full_name, roll_no, nis)
    if errors:
        return None, errors
    if roll is None:
        roll = (db.execute("SELECT COALESCE(MAX(roll_no),0) FROM students WHERE class_id = ?", (class_id,)).fetchone()[0]) + 1
    try:
        cur = db.execute(
            "INSERT INTO students(class_id, full_name, name_key, roll_no, nis, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?)",
            (class_id, name, security.name_key(name), roll, nis, timeutil.iso(timeutil.now())))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return None, {"full_name": "Data bentrok dengan siswa yang sudah ada (nama, nomor absen, atau NIS)."}
    return cur.lastrowid, {}


def update_student(db, student_id, full_name, roll_no, nis):
    name, roll, nis, errors = _validate(db, full_name, roll_no, nis, exclude_id=student_id)
    if errors:
        return errors
    try:
        db.execute("UPDATE students SET full_name = ?, name_key = ?, roll_no = ?, nis = ? WHERE id = ?",
                   (name, security.name_key(name), roll, nis, student_id))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return {"full_name": "Data bentrok dengan siswa yang sudah ada (nama, nomor absen, atau NIS)."}
    return {}


def set_active(db, student_id, active):
    db.execute("UPDATE students SET is_active = ? WHERE id = ?", (1 if active else 0, student_id))
    db.commit()
