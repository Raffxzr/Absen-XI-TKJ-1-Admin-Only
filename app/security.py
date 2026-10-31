"""Autentikasi admin, sesi sisi-server, CSRF, pembatasan login, dan otorisasi."""
import hashlib
import hmac
import secrets
import unicodedata
from datetime import timedelta
from functools import wraps

from flask import abort, current_app, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import timeutil
from .db import get_db

ROLES = ("admin",)
ROLE_HOME = {"admin": "admin.overview"}
_PW_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"  # tanpa karakter mirip (0/O, 1/l/I)
_COMMON = {"12345678", "123456789", "1234567890", "password", "password1", "qwertyui", "11111111", "abcd1234"}
_dummy_hash = None


# ---------------------------------------------------------------- nama & password
def clean_name(value):
    return " ".join(unicodedata.normalize("NFKC", value or "").split())


def name_key(value):
    return clean_name(value).casefold()


def hash_password(password):
    return generate_password_hash(password, method=current_app.config["PASSWORD_HASH_METHOD"])


def verify_password(stored_hash, password):
    """Selalu menjalankan satu verifikasi hash, termasuk ketika pengguna tidak ada
    (mengurangi perbedaan waktu respons yang bisa membocorkan keberadaan akun)."""
    global _dummy_hash
    if stored_hash is None:
        if _dummy_hash is None:
            _dummy_hash = hash_password(secrets.token_urlsafe(16))
        check_password_hash(_dummy_hash, password)
        return False
    return check_password_hash(stored_hash, password)


def generate_temp_password(length=10):
    return "".join(secrets.choice(_PW_ALPHABET) for _ in range(length))


def validate_new_password(password, full_name=""):
    minimum = current_app.config["MIN_PASSWORD_LENGTH"]
    if len(password) < minimum:
        return f"Kata sandi minimal {minimum} karakter."
    if len(password) > 128:
        return "Kata sandi terlalu panjang (maksimal 128 karakter)."
    if password.casefold() in _COMMON or len(set(password)) < 4:
        return "Kata sandi terlalu mudah ditebak. Gunakan kombinasi yang lebih unik."
    if full_name and password.casefold() == clean_name(full_name).casefold():
        return "Kata sandi tidak boleh sama dengan nama lengkap."
    return None


def check_admin_key(candidate):
    expected = current_app.config.get("ADMIN_ACCESS_KEY") or current_app.config.get("TEACHER_ACCESS_KEY") or ""
    if not expected:
        current_app.logger.warning("ADMIN_ACCESS_KEY belum diatur; login admin dinonaktifkan.")
        return False
    return hmac.compare_digest((candidate or "").encode("utf-8"), expected.encode("utf-8"))


# Alias kompatibilitas
check_teacher_key = check_admin_key


# ---------------------------------------------------------------- CSRF
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def _csrf_ok():
    expected = session.get("csrf", "")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    return bool(expected) and hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


# ---------------------------------------------------------------- sesi sisi-server
def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def start_session(user_id):
    """Buat sesi baru. Sesi dan token CSRF lama dibuang (mencegah session fixation)."""
    db = get_db()
    now = timeutil.now()
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions(token_hash, user_id, created_at, last_seen_at) VALUES (?,?,?,?)",
               (_digest(token), user_id, timeutil.iso(now), timeutil.iso(now)))
    db.execute("DELETE FROM sessions WHERE created_at < ?",
               (timeutil.iso(now - timedelta(hours=current_app.config["SESSION_ABSOLUTE_HOURS"])),))
    db.commit()
    session.clear()
    session["sid"] = token
    session["csrf"] = secrets.token_urlsafe(32)


def end_session():
    token = session.get("sid")
    if token:
        db = get_db()
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(token),))
        db.commit()
    session.clear()


def end_user_sessions(user_id, keep_current=False):
    db = get_db()
    if keep_current and session.get("sid"):
        db.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user_id, _digest(session["sid"])))
    else:
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.commit()


def _load_user():
    g.user = None
    token = session.get("sid")
    if not token:
        return
    db = get_db()
    row = db.execute(
        """SELECT s.created_at AS s_created, s.last_seen_at AS s_seen, u.*
             FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?""",
        (_digest(token),)).fetchone()
    now = timeutil.now()
    cfg = current_app.config
    valid = row is not None and row["is_active"] == 1 and row["role"] == "admin"
    if valid:
        created = timeutil.parse_iso(row["s_created"])
        seen = timeutil.parse_iso(row["s_seen"])
        if now - created > timedelta(hours=cfg["SESSION_ABSOLUTE_HOURS"]) or \
           now - seen > timedelta(minutes=cfg["SESSION_IDLE_MINUTES"]):
            valid = False
    if not valid:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(token),))
        db.commit()
        session.pop("sid", None)
        return
    if now - seen > timedelta(minutes=1):
        db.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (timeutil.iso(now), _digest(token)))
        db.commit()
    g.user = row


# ---------------------------------------------------------------- pembatasan percobaan login
def client_ip():
    return (request.remote_addr or "unknown")[:64]


def login_blocked(ip, key, role="admin"):
    cfg = current_app.config
    db = get_db()
    since = timeutil.iso(timeutil.now() - timedelta(minutes=cfg["LOGIN_WINDOW_MINUTES"]))

    def failures(where, args):
        return db.execute(f"SELECT COUNT(*) FROM login_attempts WHERE success = 0 AND attempted_at >= ? AND {where}",
                          (since, *args)).fetchone()[0]

    return (failures("ip = ?", (ip,)) >= cfg["LOGIN_MAX_PER_IP"]
            or failures("ip = ? AND name_key = ? AND role = ?", (ip, key, role)) >= cfg["LOGIN_MAX_PER_IP_NAME"]
            or failures("name_key = ? AND role = ?", (key, role)) >= cfg["LOGIN_MAX_PER_ACCOUNT"])


def record_login_attempt(ip, key, role, success):
    db = get_db()
    now = timeutil.now()
    db.execute("INSERT INTO login_attempts(attempted_at, ip, role, name_key, success) VALUES (?,?,?,?,?)",
               (timeutil.iso(now), ip, role, key[:100], 1 if success else 0))
    if success:  # login berhasil: hapus kegagalan sebelumnya dari perangkat yang sama
        db.execute("DELETE FROM login_attempts WHERE success = 0 AND ip = ? AND name_key = ? AND role = ?",
                   (ip, key[:100], role))
    db.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (timeutil.iso(now - timedelta(days=2)),))
    db.commit()


# ---------------------------------------------------------------- dekorator otorisasi
def login_required(role="admin"):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("auth.login"))
            if role and g.user["role"] != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------- hook aplikasi
def init_app(app):
    @app.before_request
    def _guard():
        _load_user()
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _csrf_ok():
            abort(400, description="Formulir sudah kedaluwarsa atau tidak valid. Muat ulang halaman lalu coba lagi.")
        if (g.user is not None and g.user["must_change_password"]
                and request.endpoint not in ("account.password", "auth.logout", "static")):
            return redirect(url_for("account.password"))

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                                "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        if current_app.config["SESSION_COOKIE_SECURE"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"  # halaman berisi data tidak boleh di-cache
        return resp

    app.jinja_env.globals["csrf_token"] = csrf_token
