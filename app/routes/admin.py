"""Dashboard Admin / Pengurus Kelas (Ketua Kelas, Sekretaris, dan Wali Kelas).
Setiap rute dilindungi login_required('admin') di sisi server."""
import re
from datetime import date, timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import security, timeutil
from ..db import get_db
from ..services import attendance as att
from ..services import reports
from ..services import settings as settings_svc
from ..services import students as stu

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _class_row(db):
    return db.execute("SELECT * FROM classes ORDER BY id LIMIT 1").fetchone()


def _date_arg(name="tanggal"):
    return timeutil.parse_date_arg(request.args.get(name) or request.form.get(name), timeutil.today())


def _export(payload):
    data, mime, filename = payload
    return Response(data, mimetype=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _student_or_404(db, student_id):
    row = stu.get_student(db, student_id)
    if row is None:
        abort(404)
    return row


# ------------------------------------------------------------------ ringkasan
@bp.get("/")
@security.login_required("admin")
def overview():
    db = get_db()
    now = timeutil.now()
    d = _date_arg()
    settings = settings_svc.load(db)
    rows = att.day_overview(db, d)
    return render_template(
        "admin/overview.html",
        d=d,
        is_today=d == now.date(),
        is_future=d > now.date(),
        rows=rows,
        stats=att.day_stats(rows),
        window=settings_svc.window_state(settings, now),
        students=stu.counts(db),
        prev_day=d.fromordinal(d.toordinal() - 1),
        next_day=d.fromordinal(d.toordinal() + 1),
    )


# ------------------------------------------------------------------ siswa
@bp.get("/siswa")
@security.login_required("admin")
def students():
    db = get_db()
    q = (request.args.get("q") or "").strip()[:100]
    status = request.args.get("status", "semua")
    if status not in ("semua", "aktif", "nonaktif"):
        status = "semua"
    return render_template(
        "admin/siswa_list.html",
        rows=stu.list_students(db, q, status),
        q=q,
        status=status,
        counts=stu.counts(db),
    )


@bp.route("/siswa/baru", methods=["GET", "POST"])
@security.login_required("admin")
def student_new():
    db = get_db()
    if request.method == "GET":
        return render_template("admin/siswa_form.html", mode="baru", form={}, errors={}, student=None)
    form = {k: request.form.get(k, "") for k in ("full_name", "roll_no", "nis")}
    sid, errors = stu.create_student(db, _class_row(db)["id"], **form)
    if errors:
        return render_template("admin/siswa_form.html", mode="baru", form=form, errors=errors, student=None), 422
    student = stu.get_student(db, sid)
    flash(f"Siswa {student['full_name']} berhasil ditambahkan.", "success")
    return redirect(url_for("admin.students"))


@bp.get("/siswa/<int:student_id>")
@security.login_required("admin")
def student_detail(student_id):
    db = get_db()
    student = _student_or_404(db, student_id)
    today = timeutil.today()
    year, month = timeutil.parse_month_arg(request.args.get("bulan"), today)
    start, end = timeutil.month_range(year, month)
    history = att.student_history(db, student_id, start, end)
    if request.args.get("unduh") in ("csv", "xlsx"):
        return _export(reports.student_export(student, history, request.args["unduh"]))
    py, pm = timeutil.shift_month(year, month, -1)
    ny, nm = timeutil.shift_month(year, month, 1)
    return render_template(
        "admin/siswa_detail.html",
        student=student,
        history=history,
        year=year,
        month=month,
        label=timeutil.month_label(year, month),
        summary=att.student_month_summary(db, student_id, year, month),
        corrections=att.corrections_for_student(db, student_id),
        prev=f"{py}-{pm:02d}",
        next=None if (ny, nm) > (today.year, today.month) else f"{ny}-{nm:02d}",
    )


@bp.route("/siswa/<int:student_id>/edit", methods=["GET", "POST"])
@security.login_required("admin")
def student_edit(student_id):
    db = get_db()
    student = _student_or_404(db, student_id)
    if request.method == "GET":
        form = {"full_name": student["full_name"], "roll_no": student["roll_no"] or "", "nis": student["nis"] or ""}
        return render_template("admin/siswa_form.html", mode="edit", form=form, errors={}, student=student)
    form = {k: request.form.get(k, "") for k in ("full_name", "roll_no", "nis")}
    errors = stu.update_student(db, student_id, **form)
    if errors:
        return render_template("admin/siswa_form.html", mode="edit", form=form, errors=errors, student=student), 422
    flash("Data siswa diperbarui.", "success")
    return redirect(url_for("admin.student_detail", student_id=student_id))


@bp.post("/siswa/<int:student_id>/aktif")
@security.login_required("admin")
def student_toggle(student_id):
    db = get_db()
    student = _student_or_404(db, student_id)
    active = request.form.get("aktif") == "1"
    stu.set_active(db, student_id, active)
    flash(f"Data siswa {student['full_name']} {'diaktifkan' if active else 'dinonaktifkan'}.", "success")
    return redirect(
        request.referrer
        if request.referrer and request.referrer.startswith(request.host_url)
        else url_for("admin.students")
    )


# ------------------------------------------------------------------ presensi
@bp.get("/presensi")
@security.login_required("admin")
def attendance_list():
    db = get_db()
    now = timeutil.now()
    d = _date_arg()
    q = (request.args.get("q") or "").strip()[:100]
    status = request.args.get("status", "")
    if status not in ("H", "I", "S", "A", "belum"):
        status = ""
    settings = settings_svc.load(db)
    all_rows = att.day_overview(db, d)
    filtered_rows = att.day_overview(db, d, q or None, status or None) if (q or status) else all_rows
    return render_template(
        "admin/presensi.html",
        d=d,
        q=q,
        status=status,
        rows=filtered_rows,
        stats=att.day_stats(all_rows),
        window=settings_svc.window_state(settings, now),
        is_future=d > now.date(),
    )


@bp.post("/presensi/tandai-semua-hadir")
@security.login_required("admin")
def mark_all_present():
    db = get_db()
    now = timeutil.now()
    d = timeutil.parse_date_arg(request.form.get("tanggal"), now.date())
    ok, count, message = att.mark_all_present(db, d, g.user["id"], now)
    flash(message, "success" if ok and count > 0 else ("info" if ok else "error"))
    return redirect(url_for("admin.attendance_list", tanggal=d.isoformat()))


@bp.post("/presensi/ubah-cepat")
@security.login_required("admin")
def quick_update():
    db = get_db()
    now = timeutil.now()
    try:
        student_id = int(request.form.get("siswa", ""))
    except ValueError:
        abort(404)
    _student_or_404(db, student_id)
    d = timeutil.parse_date_arg(request.form.get("tanggal"), now.date())
    new_status = request.form.get("status", "")
    new_note = request.form.get("note", "")
    ok, message = att.quick_set_status(db, student_id, d, new_status, new_note, g.user["id"], now)
    flash(message, "success" if ok else "error")
    q = (request.form.get("q") or "").strip()[:100]
    filter_status = (request.form.get("filter_status") or "").strip()
    params = {"tanggal": d.isoformat()}
    if q:
        params["q"] = q
    if filter_status in ("H", "I", "S", "A", "belum"):
        params["status"] = filter_status
    return redirect(url_for("admin.attendance_list", **params))


@bp.route("/presensi/koreksi", methods=["GET", "POST"])
@security.login_required("admin")
def correct():
    db = get_db()
    now = timeutil.now()
    src = request.form if request.method == "POST" else request.args
    try:
        student_id = int(src.get("siswa", ""))
    except ValueError:
        abort(404)
    student = _student_or_404(db, student_id)
    d = timeutil.parse_date_arg(src.get("tanggal"), now.date())
    record = att.get_record(db, student_id, d)
    history = (
        db.execute(
            """SELECT c.*, u.full_name AS by_name FROM attendance_corrections c JOIN users u ON u.id = c.corrected_by
                WHERE c.record_id = ? ORDER BY c.corrected_at DESC, c.id DESC""",
            (record["id"],),
        ).fetchall()
        if record
        else []
    )
    form = {
        "status": record["status"] if record else "",
        "note": (record["note"] or "") if record else "",
        "reason": "",
    }
    if request.method == "POST":
        form = {
            "status": request.form.get("status", ""),
            "note": request.form.get("note", ""),
            "reason": request.form.get("reason", ""),
        }
        ok, message = att.correct_record(
            db, student_id, d, form["status"], form["note"], form["reason"], g.user["id"], now
        )
        if ok:
            flash(f"{message} ({student['full_name']}, {timeutil.fmt_short(d)})", "success")
            return redirect(url_for("admin.attendance_list", tanggal=d.isoformat()))
        return render_template(
            "admin/koreksi.html", student=student, d=d, record=record, history=history, form=form, error=message
        ), 422
    return render_template(
        "admin/koreksi.html", student=student, d=d, record=record, history=history, form=form, error=None
    )


@bp.post("/presensi/tandai-alpa")
@security.login_required("admin")
def mark_alpa():
    db = get_db()
    d = timeutil.parse_date_arg(request.form.get("tanggal"), timeutil.today())
    count, message = att.mark_missing_alpa(db, d, g.user["id"], settings_svc.load(db), timeutil.now())
    flash(message, "success" if count else "info")
    return redirect(url_for("admin.attendance_list", tanggal=d.isoformat()))


# ------------------------------------------------------------------ laporan (harian, mingguan, bulanan)
@bp.get("/laporan")
@security.login_required("admin")
def reports_index():
    return redirect(url_for("admin.report_daily"))


@bp.get("/laporan/harian")
@security.login_required("admin")
def report_daily():
    db = get_db()
    d = _date_arg()
    rows = att.day_overview(db, d)
    if request.args.get("unduh") in ("csv", "xlsx"):
        return _export(reports.daily_export(rows, d, request.args["unduh"]))
    return render_template(
        "admin/laporan_harian.html",
        d=d,
        rows=rows,
        stats=att.day_stats(rows),
        klass=_class_row(db),
        printed_at=timeutil.now(),
    )


@bp.get("/laporan/mingguan")
@security.login_required("admin")
def report_weekly():
    db = get_db()
    today = timeutil.today()
    raw = request.args.get("minggu") or request.args.get("tanggal")
    monday = timeutil.parse_week_arg(raw, today)
    report = att.week_report(db, monday)
    if request.args.get("unduh") in ("csv", "xlsx"):
        return _export(reports.weekly_export(report, request.args["unduh"]))
    prev_monday = monday - timedelta(days=7)
    next_monday = monday + timedelta(days=7)
    current_monday, _ = timeutil.week_range(today)
    return render_template(
        "admin/laporan_mingguan.html",
        report=report,
        minggu=monday.isoformat(),
        label=report["label"],
        prev=prev_monday.isoformat(),
        next=None if next_monday > current_monday else next_monday.isoformat(),
        klass=_class_row(db),
        printed_at=timeutil.now(),
    )


@bp.get("/laporan/bulanan")
@security.login_required("admin")
def report_monthly():
    db = get_db()
    today = timeutil.today()
    year, month = timeutil.parse_month_arg(request.args.get("bulan"), today)
    report = att.month_report(db, year, month)
    if request.args.get("unduh") in ("csv", "xlsx"):
        return _export(reports.monthly_export(report, request.args["unduh"]))
    py, pm = timeutil.shift_month(year, month, -1)
    ny, nm = timeutil.shift_month(year, month, 1)
    return render_template(
        "admin/laporan_bulanan.html",
        report=report,
        label=timeutil.month_label(year, month),
        bulan=f"{year}-{month:02d}",
        prev=f"{py}-{pm:02d}",
        next=None if (ny, nm) > (today.year, today.month) else f"{ny}-{nm:02d}",
        klass=_class_row(db),
        printed_at=timeutil.now(),
    )


# ------------------------------------------------------------------ pengaturan
@bp.route("/pengaturan", methods=["GET", "POST"])
@security.login_required("admin")
def settings():
    db = get_db()
    klass = _class_row(db)
    if request.method == "GET":
        return render_template(
            "admin/pengaturan.html", s=settings_svc.load(db), errors=[], year=klass["academic_year"] or ""
        )
    clean, errors = settings_svc.validate_form(request.form)
    year = (request.form.get("academic_year") or "").strip()
    if year and not re.fullmatch(r"\d{4}/\d{4}", year):
        errors.append("Tahun ajaran harus berformat 2026/2027, atau kosongkan.")
    if errors:
        merged = settings_svc.load(db)
        merged.update({k: request.form.get(k, "") for k in merged if k in request.form})
        return render_template("admin/pengaturan.html", s=merged, errors=errors, year=year), 422
    settings_svc.save(db, clean)
    db.execute("UPDATE classes SET academic_year = ? WHERE id = ?", (year or None, klass["id"]))
    db.commit()
    flash("Pengaturan disimpan.", "success")
    return redirect(url_for("admin.settings"))
