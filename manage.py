#!/usr/bin/env python3
"""CLI administrasi: inisialisasi database, akun admin (Ketua Kelas, Sekretaris, Wali Kelas),
impor daftar siswa, reset sandi admin, dan aktif/nonaktif akun.

Contoh:
  python manage.py init-db
  python manage.py create-admin --name "Ketua Kelas XI TKJ 1"
  python manage.py create-admin --name "Sekretaris XI TKJ 1"
  python manage.py import-students data/daftar_siswa_XI_TKJ_1.md
"""
import argparse
import getpass
import re
import sys
from pathlib import Path

from app import create_app, db as dbmod, security, timeutil
from app.services import students as stu


def _app():
    return create_app()


def cmd_init_db(args):
    app = _app()
    conn = dbmod.connect(app.config["DATABASE"])
    applied = dbmod.migrate(conn)
    dbmod.seed_class(conn, app.config["CLASS_NAME"], app.config["SCHOOL_NAME"])
    conn.close()
    print("Migrasi diterapkan:", ", ".join(applied) if applied else "tidak ada (sudah terbaru)")
    print(f"Kelas: {app.config['CLASS_NAME']} — {app.config['SCHOOL_NAME']}")
    print(f"Database: {app.config['DATABASE']}")


def _read_password(args):
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Kata sandi: ")
    if first != getpass.getpass("Ulangi kata sandi: "):
        sys.exit("Kata sandi tidak sama.")
    return first


def cmd_create_admin(args):
    app = _app()
    with app.app_context():
        conn = dbmod.get_db()
        name = security.clean_name(args.name)
        if len(name) < 3:
            sys.exit("Nama akun terlalu pendek (minimal 3 karakter).")
        password = _read_password(args)
        problem = security.validate_new_password(password, name)
        if problem:
            sys.exit(problem)
        if conn.execute("SELECT 1 FROM users WHERE role='admin' AND name_key=?", (security.name_key(name),)).fetchone():
            sys.exit("Akun admin dengan nama itu sudah ada. Pakai `reset-password` untuk mengganti kata sandi.")
        conn.execute(
            "INSERT INTO users(role, full_name, name_key, password_hash, is_active, must_change_password, created_at) "
            "VALUES ('admin', ?, ?, ?, 1, 0, ?)",
            (name, security.name_key(name), security.hash_password(password), timeutil.iso(timeutil.now())))
        conn.commit()
        print(f"Akun admin dibuat: {name}")
        if not app.config["ADMIN_ACCESS_KEY"]:
            print("PERINGATAN: ADMIN_ACCESS_KEY belum diatur di .env, login admin belum bisa dipakai.")


def _parse_names(path):
    """Mendukung tabel markdown (| No | Nama |) maupun satu nama per baris. Mengembalikan [(no, nama)]."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or set(line) <= set("|-: "):
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2 and cells[0].isdigit():
                out.append((int(cells[0]), cells[1]))
        elif not re.match(r"^(no|nama)\b", line, re.I):
            out.append((None, line))
    return out


def cmd_import_students(args):
    app = _app()
    with app.app_context():
        conn = dbmod.get_db()
        klass = conn.execute("SELECT * FROM classes ORDER BY id LIMIT 1").fetchone()
        if not klass:
            sys.exit("Kelas belum ada. Jalankan `python manage.py init-db` dahulu.")
        entries = _parse_names(args.file)
        if not entries:
            sys.exit("Tidak ada nama yang terbaca dari berkas.")
        created, skipped = [], []
        for roll, name in entries:
            sid, errors = stu.create_student(conn, klass["id"], name, roll)
            if errors:
                skipped.append((name, "; ".join(errors.values())))
            else:
                created.append((roll, security.clean_name(name)))
        print(f"Diimpor: {len(created)} siswa | Dilewati: {len(skipped)}")
        for name, why in skipped:
            print(f"  - {name}: {why}")
        if created:
            print("Data siswa siap digunakan oleh Admin Kelas (Ketua Kelas / Sekretaris / Wali Kelas).")


def _admin_user(conn, name):
    row = conn.execute("SELECT * FROM users WHERE role='admin' AND name_key=?", (security.name_key(name),)).fetchone()
    if not row:
        sys.exit("Akun admin tidak ditemukan.")
    return row


def cmd_reset_password(args):
    app = _app()
    with app.app_context():
        conn = dbmod.get_db()
        user = _admin_user(conn, args.name)
        password = _read_password(args)
        problem = security.validate_new_password(password, user["full_name"])
        if problem:
            sys.exit(problem)
        conn.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?",
                     (security.hash_password(password), user["id"]))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        conn.commit()
        print(f"Kata sandi akun admin '{user['full_name']}' berhasil diperbarui.")


def cmd_set_active(args):
    app = _app()
    with app.app_context():
        conn = dbmod.get_db()
        if args.role == "siswa":
            row = conn.execute("SELECT * FROM students WHERE name_key=?", (security.name_key(args.name),)).fetchone()
            if not row:
                sys.exit("Data siswa tidak ditemukan.")
            stu.set_active(conn, row["id"], args.on)
            print(f"Data siswa {row['full_name']} {'diaktifkan' if args.on else 'dinonaktifkan'}.")
        else:
            user = _admin_user(conn, args.name)
            conn.execute("UPDATE users SET is_active=? WHERE id=?", (1 if args.on else 0, user["id"]))
            if not args.on:
                conn.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            conn.commit()
            print(f"Akun admin {user['full_name']} {'diaktifkan' if args.on else 'dinonaktifkan'}.")


def cmd_list_users(args):
    app = _app()
    with app.app_context():
        conn = dbmod.get_db()
        print("=== AKUN ADMIN ===")
        rows = conn.execute("SELECT role, full_name, is_active FROM users ORDER BY full_name").fetchall()
        if not rows:
            print("(Belum ada akun admin)")
        for r in rows:
            print(f"{r['role']:<6} {'aktif' if r['is_active'] else 'NONAKTIF':<9} {r['full_name']}")
        sc = stu.counts(conn)
        print(f"\n=== DATA SISWA ===\nTotal: {sc['total']} siswa ({sc['aktif']} aktif, {sc['nonaktif']} nonaktif)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="terapkan migrasi dan buat data kelas").set_defaults(fn=cmd_init_db)

    for alias in ("create-admin", "create-teacher"):
        t = sub.add_parser(alias, help="buat akun admin (Ketua Kelas, Sekretaris, atau Wali Kelas)")
        t.add_argument("--name", required=True)
        t.add_argument("--password-stdin", action="store_true", help="baca kata sandi dari stdin (non-interaktif)")
        t.set_defaults(fn=cmd_create_admin)

    i = sub.add_parser("import-students", help="impor daftar siswa dari tabel markdown / satu nama per baris")
    i.add_argument("file")
    i.set_defaults(fn=cmd_import_students)

    r = sub.add_parser("reset-password", help="reset kata sandi akun admin")
    r.add_argument("--role", choices=("admin", "guru"), default="admin", help="peran akun (bawaan: admin)")
    r.add_argument("--name", required=True)
    r.add_argument("--password-stdin", action="store_true")
    r.set_defaults(fn=cmd_reset_password)

    a = sub.add_parser("set-active", help="aktifkan/nonaktifkan akun admin atau data siswa")
    a.add_argument("--role", choices=("admin", "siswa"), default="admin")
    a.add_argument("--name", required=True)
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--on", action="store_true")
    g.add_argument("--off", action="store_true")
    a.set_defaults(fn=cmd_set_active)

    for alias in ("list-users", "list-admins"):
        sub.add_parser(alias, help="daftar akun admin dan ringkasan siswa").set_defaults(fn=cmd_list_users)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
