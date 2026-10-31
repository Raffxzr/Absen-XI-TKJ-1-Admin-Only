# Sistem Presensi Siswa

Sistem Presensi Siswa adalah aplikasi berbasis web (Python) untuk mengelola data siswa, mencatat kehadiran harian, serta menghasilkan laporan presensi secara otomatis (harian, mingguan, dan bulanan).

## 🚀 Fitur Utama

*   **Autentikasi & Akun:** Sistem login aman untuk admin dan pengguna.
*   **Manajemen Siswa:** Tambah, edit, hapus, dan lihat detail data siswa.
*   **Pencatatan Presensi:** Input kehadiran siswa secara efisien.
*   **Laporan Komprehensif:** Pembuatan laporan kehadiran harian, mingguan, dan bulanan.
*   **Pengaturan Sistem:** Konfigurasi aplikasi dan data.

## 🛠️ Teknologi yang Digunakan

*   **Backend:** Python (Framework Web seperti Flask)
*   **Database:** SQL (dikelola via `app/db.py` & folder `migrations/`)
*   **Frontend:** HTML, CSS, JavaScript (Jinja2 Templates)

## 📦 Prasyarat

Pastikan Anda sudah menginstal:
*   [Python 3.10+](https://www.python.org/downloads/)
*   `pip`

## ⚙️ Cara Instalasi & Menjalankan Aplikasi

1. **Clone repositori**
   ```bash
   # Masuk ke direktori projek
   cd nama-folder-proyek
   ```

2. **Buat Virtual Environment**
   ```bash
   python -m venv venv
   
   # Aktifkan virtual environment (Windows):
   venv\Scripts\activate
   # Aktifkan virtual environment (Mac/Linux):
   source venv/bin/activate
   ```

3. **Instal dependensi**
   ```bash
   pip install -r requirements.txt
   ```

4. **Konfigurasi Environment**
   Salin file `.env.example` menjadi `.env` dan sesuaikan konfigurasinya jika diperlukan.
   ```bash
   cp .env.example .env
   ```

5. **Inisialisasi Database**
   Impor atau jalankan script SQL yang ada di `migrations/001_init.sql` untuk membuat struktur tabel database.

6. **Jalankan Aplikasi**
   Anda bisa menjalankan aplikasi menggunakan file `manage.py` atau `wsgi.py`.
   ```bash
   python manage.py
   ```
   Aplikasi biasanya akan berjalan di `http://127.0.0.1:5000/`.

## 📁 Struktur Proyek Utama

*   `app/`: Berisi kode sumber utama aplikasi (routes, services, templates, static, dll).
*   `data/`: Penyimpanan data statis atau file pendukung (seperti daftar siswa Markdown).
*   `migrations/`: Berisi skrip SQL untuk skema database.
*   `manage.py` & `wsgi.py`: Entry point untuk menjalankan dan mengelola aplikasi.
