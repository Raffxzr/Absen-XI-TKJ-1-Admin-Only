"""Akses database SQLite + runner migrasi sederhana (migrations/NNN_nama.sql)."""
import re
import sqlite3
from pathlib import Path

from flask import current_app, g

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def connect(path):
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def migrate(conn):
    """Terapkan migrasi yang belum dijalankan. Mengembalikan daftar berkas yang baru diterapkan."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = re.match(r"(\d+)", path.name).group(1)
        if version in done:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
        conn.commit()
        applied.append(path.name)
    return applied


def seed_class(conn, name, school_name, academic_year=None):
    row = conn.execute("SELECT id FROM classes WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO classes(name, school_name, academic_year) VALUES (?,?,?)",
                       (name, school_name, academic_year))
    conn.commit()
    return cur.lastrowid


def init_app(app):
    app.teardown_appcontext(close_db)
