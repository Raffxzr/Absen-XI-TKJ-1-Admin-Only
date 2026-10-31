"""Ganti kata sandi akun Admin (Ketua Kelas, Sekretaris, Wali Kelas)."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import security
from ..db import get_db

bp = Blueprint("account", __name__, url_prefix="/akun")


@bp.route("/password", methods=["GET", "POST"])
@security.login_required("admin")
def password():
    forced = bool(g.user["must_change_password"])
    if request.method == "GET":
        return render_template("account/password.html", forced=forced, errors={})

    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")
    errors = {}
    if not security.verify_password(g.user["password_hash"], current):
        errors["current_password"] = "Kata sandi saat ini tidak sesuai."
    problem = security.validate_new_password(new, g.user["full_name"])
    if problem:
        errors["new_password"] = problem
    elif new == current:
        errors["new_password"] = "Kata sandi baru harus berbeda dari kata sandi saat ini."
    if new != confirm:
        errors["confirm_password"] = "Konfirmasi kata sandi belum sama."
    if errors:
        return render_template("account/password.html", forced=forced, errors=errors), 422

    db = get_db()
    db.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
               (security.hash_password(new), g.user["id"]))
    db.commit()
    security.end_user_sessions(g.user["id"], keep_current=True)  # sesi di perangkat lain berakhir
    flash("Kata sandi berhasil diganti.", "success")
    return redirect(url_for("admin.overview"))
