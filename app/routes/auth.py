"""Login / logout khusus Admin (Ketua Kelas, Sekretaris, dan Wali Kelas)."""
from flask import Blueprint, g, redirect, render_template, request, url_for

from .. import security, timeutil
from ..db import get_db

bp = Blueprint("auth", __name__)

GENERIC_ERROR = "Nama akun, kata sandi, atau kunci akses admin tidak sesuai."


@bp.get("/")
def index():
    if g.user:
        return redirect(url_for("admin.overview"))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("admin.overview"))
    if request.method == "GET":
        return render_template("auth/login.html", full_name="", error=None)

    db = get_db()
    full_name = security.clean_name(request.form.get("full_name", ""))[:100]
    password = request.form.get("password", "")[:200]
    admin_key = (request.form.get("admin_key") or request.form.get("teacher_key") or "")[:200]
    key = security.name_key(full_name)
    ip = security.client_ip()
    role = "admin"

    if security.login_blocked(ip, key, role):
        return render_template(
            "auth/login.html",
            full_name=full_name,
            error="Terlalu banyak percobaan masuk. Tunggu 15 menit lalu coba lagi.",
        ), 429

    user = db.execute("SELECT * FROM users WHERE role = 'admin' AND name_key = ?", (key,)).fetchone()
    password_ok = security.verify_password(user["password_hash"] if user else None, password)
    key_ok = security.check_admin_key(admin_key)
    # Semua pemeriksaan dievaluasi sebelum keputusan, supaya waktu respons tidak membedakan penyebab gagal.
    ok = bool(user) and user["is_active"] == 1 and password_ok and key_ok

    security.record_login_attempt(ip, key, role, ok)
    if not ok:
        return render_template("auth/login.html", full_name=full_name, error=GENERIC_ERROR), 401

    security.start_session(user["id"])
    db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (timeutil.iso(timeutil.now()), user["id"]))
    db.commit()
    return redirect(url_for("admin.overview"))


@bp.post("/logout")
def logout():
    security.end_session()
    return redirect(url_for("auth.login"))
