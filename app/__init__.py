"""Aplikasi Absensi Kelas XI TKJ 1 — SMKN 8 Kota Bekasi (Mode Admin / Pengurus Kelas)."""
from pathlib import Path

from flask import Flask, g, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db as dbmod
from . import security, timeutil
from .config import build_config, load_dotenv
from .icons import ICONS
from .services.attendance import STATUS_ORDER, STATUSES


def create_app(test_config=None):
    if test_config is None:
        load_dotenv()
    app = Flask(__name__)
    app.config.from_mapping(build_config(test_config))

    n = app.config["TRUST_PROXY"]
    if n:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    dbmod.init_app(app)
    security.init_app(app)

    from .routes import account, admin, auth
    for module in (auth, account, admin):
        app.register_blueprint(module.bp)

    app.jinja_env.globals.update(ICONS=ICONS, STATUS_LABELS=STATUSES, STATUS_ORDER=STATUS_ORDER,
                                 fmt_long=timeutil.fmt_long)
    app.jinja_env.filters.update(
        tgl=timeutil.fmt_long, tgl_pendek=timeutil.fmt_short, hari_bulan=timeutil.fmt_day_month,
        jam=timeutil.fmt_time, waktu=timeutil.fmt_datetime)

    @app.context_processor
    def _inject():
        klass = None
        if g.get("user") is not None or request.endpoint in ("auth.login",):
            klass = dbmod.get_db().execute("SELECT * FROM classes ORDER BY id LIMIT 1").fetchone()
        return {"current_user": g.get("user"), "klass": klass, "now_wib": timeutil.now()}

    def _error(code, title, message):
        return render_template("errors/error.html", code=code, title=title, message=message), code

    @app.errorhandler(400)
    def _400(e):
        return _error(400, "Permintaan tidak valid", getattr(e, "description", None) or "Permintaan tidak dapat diproses.")

    @app.errorhandler(403)
    def _403(e):
        return _error(403, "Akses ditolak", "Akun Anda tidak memiliki izin untuk membuka halaman ini.")

    @app.errorhandler(404)
    def _404(e):
        return _error(404, "Halaman tidak ditemukan", "Alamat yang Anda buka tidak tersedia.")

    @app.errorhandler(405)
    def _405(e):
        return _error(405, "Metode tidak diizinkan", "Permintaan ini tidak didukung untuk alamat tersebut.")

    @app.errorhandler(413)
    def _413(e):
        return _error(413, "Permintaan terlalu besar", "Data yang dikirim melebihi batas.")

    @app.errorhandler(500)
    def _500(e):
        return _error(500, "Terjadi kesalahan", "Terjadi kesalahan pada server. Coba lagi beberapa saat.")

    return app
