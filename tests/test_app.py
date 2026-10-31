"""Uji otomatis aplikasi Absensi Kelas XI TKJ 1 (Mode Admin / Pengurus Kelas).
Jalankan: python -m unittest discover -s tests -t . -v"""
import io
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openpyxl import load_workbook

from app import create_app, db as dbmod, security
from app.services import settings as settings_svc
from app.services import students as stu

WIB = timezone(timedelta(hours=7))
ADMIN_KEY = "kunci-admin-RAHASIA-4821"
ADMIN = ("Ketua Kelas XI TKJ 1", "Sandi-Admin-Uji-9")
STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.clock = {"now": datetime(2026, 10, 26, 6, 45, tzinfo=WIB)}  # Senin 26 Okt 2026 06:45 WIB
        self.app = create_app({
            "APP_ENV": "testing",
            "TESTING": True,
            "SECRET_KEY": "x" * 40,
            "DATABASE": os.path.join(self.tmp, "t.db"),
            "ADMIN_ACCESS_KEY": ADMIN_KEY,
            "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000",
            "SESSION_COOKIE_SECURE": False,
            "NOW_FUNC": lambda: self.clock["now"],
        })
        conn = dbmod.connect(self.app.config["DATABASE"])
        dbmod.migrate(conn)
        self.class_id = dbmod.seed_class(conn, "XI TKJ 1", "SMKN 8 Kota Bekasi")
        conn.close()
        self.student_ids = {}
        with self.app.app_context():
            db = dbmod.get_db()
            db.execute(
                "INSERT INTO users(role, full_name, name_key, password_hash, is_active, must_change_password, created_at) "
                "VALUES ('admin', ?, ?, ?, 1, 0, '2026-01-01T00:00:00+07:00')",
                (ADMIN[0], security.name_key(ADMIN[0]), security.hash_password(ADMIN[1])),
            )
            db.commit()
            for i, name in enumerate(["AATIF KHOIRUDDIN AMIN", "ALMIRA REGINA PUTRI", "BARAKA RAMADHANI"], start=1):
                sid, err = stu.create_student(db, self.class_id, name, i)
                self.assertFalse(err)
                self.student_ids[name] = sid
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def token(self, client=None):
        client = client or self.client
        with client.session_transaction() as s:
            if "csrf" not in s:
                s["csrf"] = "t" * 43
            return s["csrf"]

    def post(self, url, data=None, client=None, **kw):
        client = client or self.client
        data = dict(data or {})
        data["csrf_token"] = self.token(client)
        return client.post(url, data=data, **kw)

    def login_admin(self, name=ADMIN[0], password=ADMIN[1], key=ADMIN_KEY, client=None):
        client = client or self.client
        client.get("/login")
        data = {"full_name": name, "password": password}
        if key is not None:
            data["admin_key"] = key
        return self.post("/login", data, client=client)

    def count(self, sql, args=()):
        with self.app.app_context():
            return dbmod.get_db().execute(sql, args).fetchone()[0]

    def new_client(self):
        return self.app.test_client()


class AuthTests(Base):
    def test_admin_login_and_password_change(self):
        r = self.login_admin(name="ketua  kelas xi tkj 1")  # huruf kecil + spasi ganda tetap cocok
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/", r.headers["Location"])
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        # ganti sandi
        r = self.post("/akun/password", {"current_password": ADMIN[1], "new_password": "12345678", "confirm_password": "12345678"})
        self.assertEqual(r.status_code, 422)
        r = self.post("/akun/password", {"current_password": ADMIN[1], "new_password": "Sandi-Admin-Baru-88", "confirm_password": "Sandi-Admin-Baru-88"})
        self.assertEqual(r.status_code, 302)

    def test_student_portal_and_student_login_removed(self):
        """Akses akun siswa telah dihapus sepenuhnya."""
        login_html = self.client.get("/login").get_data(as_text=True)
        self.assertNotIn("role-tabs", login_html)
        for path in ("/siswa", "/siswa/", "/siswa/presensi", "/siswa/riwayat"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_login_page_texts_logo_and_dark_theme_toggle(self):
        """Memastikan logo kelas, tombol switch tema gelap, dan teks halaman login sesuai spesifikasi."""
        login_html = self.client.get("/login").get_data(as_text=True)
        self.assertIn("logo-kelas.png", login_html)
        self.assertIn("data-theme-toggle", login_html)
        self.assertIn("Khusus pengurus yang ditunjuk (Ketua Kelas dan Sekretaris)", login_html)
        self.assertIn("Masukkan akun admin yang terdaftar", login_html)
        self.assertNotIn("h-admin_key", login_html)
        self.assertIn("Lupa kata sandi atau kunci akses? Hubungi admin web.", login_html)
        self.assertTrue((STATIC_DIR / "img" / "logo-kelas.png").is_file())

    def test_invalid_credentials_generic_message(self):
        wrong_pw = self.login_admin(password="salah-123")
        unknown = self.login_admin(name="AKUN TIDAK ADA", password="salah-123", client=self.new_client())
        wrong_key = self.login_admin(key="kunci-salah", client=self.new_client())
        for resp in (wrong_pw, unknown, wrong_key):
            self.assertEqual(resp.status_code, 401)
            self.assertIn("Nama akun, kata sandi, atau kunci akses admin tidak sesuai.", resp.get_data(as_text=True))

    def test_admin_key_disabled_when_unconfigured(self):
        self.app.config["ADMIN_ACCESS_KEY"] = ""
        self.assertEqual(self.login_admin(key="").status_code, 401)

    def test_admin_key_never_exposed_to_client(self):
        bodies = [self.client.get("/login").get_data(as_text=True)]
        for f in STATIC_DIR.rglob("*"):
            if f.is_file() and f.suffix in (".css", ".js", ".svg"):
                bodies.append(f.read_text(encoding="utf-8", errors="ignore"))
        self.login_admin()
        for path in ("/admin/", "/admin/presensi", "/admin/siswa", "/admin/laporan/mingguan", "/admin/pengaturan"):
            bodies.append(self.client.get(path).get_data(as_text=True))
        for b in bodies:
            self.assertNotIn(ADMIN_KEY, b)

    def test_csrf_required_on_post(self):
        r = self.client.post("/login", data={"full_name": ADMIN[0], "password": ADMIN[1], "admin_key": ADMIN_KEY})
        self.assertEqual(r.status_code, 400)
        self.login_admin()
        r = self.client.post("/logout", data={})
        self.assertEqual(r.status_code, 400)

    def test_login_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.login_admin(password="salah-salah-1").status_code, 401)
        r = self.login_admin()
        self.assertEqual(r.status_code, 429)
        self.clock["now"] += timedelta(minutes=16)
        self.assertEqual(self.login_admin().status_code, 302)

    def test_logout_and_idle_timeout(self):
        self.login_admin()
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.clock["now"] += timedelta(minutes=121)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_security_headers_and_production_secret(self):
        r = self.client.get("/login")
        csp = r.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp)
        with self.assertRaises(RuntimeError):
            create_app({"APP_ENV": "production", "SECRET_KEY": "pendek"})


class CspRegressionTests(unittest.TestCase):
    def test_templates_have_no_inline_style_or_handlers(self):
        tpl = Path(__file__).resolve().parent.parent / "app" / "templates"
        for f in tpl.rglob("*.html"):
            text = f.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"\sstyle\s*=", f.name)
            self.assertNotRegex(text, r"\son[a-z]+\s*=\s*[\"']", f.name)
            self.assertNotRegex(text, r"<script(?![^>]*\bsrc=)", f.name)
            self.assertNotRegex(text, r"<style", f.name)
            self.assertNotRegex(text, r"https?://(?!www\.w3\.org)", f.name)


class AdminWorkflowTests(Base):
    ADMIN_PATHS = [
        "/admin/",
        "/admin/presensi",
        "/admin/siswa",
        "/admin/siswa/baru",
        "/admin/siswa/1",
        "/admin/presensi/koreksi?siswa=1",
        "/admin/laporan/harian",
        "/admin/laporan/mingguan",
        "/admin/laporan/bulanan",
        "/admin/pengaturan",
    ]

    def test_anonymous_redirected_to_login(self):
        for p in self.ADMIN_PATHS + ["/akun/password"]:
            r = self.client.get(p)
            self.assertEqual(r.status_code, 302, p)
            self.assertIn("/login", r.headers["Location"])

    def test_all_admin_pages_render(self):
        self.login_admin()
        for p in self.ADMIN_PATHS + ["/admin/laporan", "/admin/siswa?q=aatif&status=aktif", "/admin/presensi?status=belum"]:
            r = self.client.get(p, follow_redirects=True)
            self.assertEqual(r.status_code, 200, p)

    def test_mark_all_present_then_edit_absent_students(self):
        """Alur utama: Klik tombol cepat 'Tandai Semua Hadir', lalu ubah status siswa yang tidak masuk."""
        self.login_admin()
        # 1. Tekan tombol cepat Tandai Semua Hadir
        r = self.post("/admin/presensi/tandai-semua-hadir", {"tanggal": "2026-10-26"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.count("SELECT COUNT(*) FROM attendance_records WHERE status='H' AND att_date='2026-10-26'"), 3)

        # 2. Ubah cepat status siswa yang tidak masuk (ALMIRA -> Sakit, BARAKA -> Izin)
        almira_id = self.student_ids["ALMIRA REGINA PUTRI"]
        baraka_id = self.student_ids["BARAKA RAMADHANI"]

        r1 = self.post("/admin/presensi/ubah-cepat", {
            "siswa": almira_id,
            "tanggal": "2026-10-26",
            "status": "S",
            "note": "Demam tinggi",
        })
        self.assertEqual(r1.status_code, 302)

        r2 = self.post("/admin/presensi/ubah-cepat", {
            "siswa": baraka_id,
            "tanggal": "2026-10-26",
            "status": "I",
            "note": "Izin acara keluarga",
        })
        self.assertEqual(r2.status_code, 302)

        # Pastikan status tersimpan dengan benar (1 Hadir, 1 Sakit, 1 Izin) dan tercatat di riwayat perubahan
        self.assertEqual(self.count("SELECT COUNT(*) FROM attendance_records WHERE status='H'"), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM attendance_records WHERE status='S'"), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM attendance_records WHERE status='I'"), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM attendance_corrections"), 2)

        # 3. Menekan Tandai Semua Hadir lagi tidak menimpa siswa yang sudah dicatat Sakit/Izin
        self.post("/admin/presensi/tandai-semua-hadir", {"tanggal": "2026-10-26"})
        self.assertEqual(self.count("SELECT COUNT(*) FROM attendance_records WHERE status='S'"), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM attendance_records WHERE status='I'"), 1)

    def test_weekly_report_and_exports(self):
        """Uji rekap mingguan (Senin-Minggu) beserta ekspor CSV dan Excel (.xlsx)."""
        self.login_admin()
        aatif_id = self.student_ids["AATIF KHOIRUDDIN AMIN"]
        almira_id = self.student_ids["ALMIRA REGINA PUTRI"]

        # Senin 26 Okt 2026: Semua hadir lalu Almira diubah Sakit
        self.post("/admin/presensi/tandai-semua-hadir", {"tanggal": "2026-10-26"})
        self.post("/admin/presensi/ubah-cepat", {"siswa": almira_id, "tanggal": "2026-10-26", "status": "S", "note": "Flu"})

        # Selasa 27 Okt 2026: Majukan waktu ke Selasa, login kembali, tandai semua hadir lalu Aatif diubah Izin
        self.clock["now"] = datetime(2026, 10, 27, 7, 0, tzinfo=WIB)
        self.login_admin()
        self.post("/admin/presensi/tandai-semua-hadir", {"tanggal": "2026-10-27"})
        self.post("/admin/presensi/ubah-cepat", {"siswa": aatif_id, "tanggal": "2026-10-27", "status": "I", "note": "=HYPERLINK(\"http://x\")"})

        # Buka halaman laporan mingguan
        html = self.client.get("/admin/laporan/mingguan?minggu=2026-10-27").get_data(as_text=True)
        self.assertIn("26 Okt – 1 Nov 2026", html)
        self.assertRegex(html, r"Hari efektif</dt><dd>2</dd>")

        # Ekspor CSV mingguan
        csv_resp = self.client.get("/admin/laporan/mingguan?minggu=2026-10-26&unduh=csv")
        self.assertEqual(csv_resp.status_code, 200)
        csv_text = csv_resp.get_data(as_text=True)
        self.assertIn("AATIF KHOIRUDDIN AMIN,H,I,,,,1,1,0,0,0,50.0", csv_text)
        self.assertIn("ALMIRA REGINA PUTRI,S,H,,,,1,0,1,0,0,50.0", csv_text)
        self.assertIn("BARAKA RAMADHANI,H,H,,,,2,0,0,0,0,100.0", csv_text)

        # Ekspor XLSX mingguan
        xlsx_resp = self.client.get("/admin/laporan/mingguan?minggu=2026-10-26&unduh=xlsx")
        self.assertEqual(xlsx_resp.status_code, 200)
        wb = load_workbook(io.BytesIO(xlsx_resp.data))
        self.assertEqual(len(wb.sheetnames), 2)
        rows = {r[1].value: [c.value for c in r] for r in wb.worksheets[0].iter_rows(min_row=2)}
        self.assertEqual(rows["BARAKA RAMADHANI"][2], 2)  # 2 Hadir
        self.assertEqual(rows["BARAKA RAMADHANI"][7], 100.0)  # 100%

    def test_student_crud_without_passwords(self):
        self.login_admin()
        r = self.post("/admin/siswa/baru", {"full_name": "SITI NURHALIZA", "roll_no": "", "nis": "12345"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.count("SELECT COUNT(*) FROM students"), 4)
        self.assertEqual(self.count("SELECT COUNT(*) FROM users"), 1)  # tidak menambah baris di tabel users!

        # Nama ganda ditolak
        r = self.post("/admin/siswa/baru", {"full_name": "siti  nurhaliza"})
        self.assertEqual(r.status_code, 422)

    def test_detailed_correction_and_mark_alpa(self):
        self.login_admin()
        sid = self.student_ids["AATIF KHOIRUDDIN AMIN"]
        r = self.post("/admin/presensi/koreksi", {
            "siswa": sid,
            "tanggal": "2026-10-26",
            "status": "I",
            "note": "Lomba LKS",
            "reason": "Surat dispensasi sekolah",
        })
        self.assertEqual(r.status_code, 302)
        # Tandai sisa siswa sebagai Alpa
        r2 = self.post("/admin/presensi/tandai-alpa", {"tanggal": "2026-10-26"})
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(self.count("SELECT COUNT(*) FROM attendance_records WHERE status='A'"), 2)


if __name__ == "__main__":
    unittest.main()
