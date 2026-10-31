"""Konfigurasi aplikasi. Semua rahasia dibaca dari environment variable (atau berkas .env),
tidak pernah ditulis di kode maupun dikirim ke browser."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path=None):
    """Pembaca .env sederhana (tanpa dependensi). Variabel yang sudah ada di environment tidak ditimpa."""
    path = Path(path) if path else BASE_DIR / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _flag(value, default):
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def build_config(overrides=None):
    overrides = dict(overrides or {})
    env = os.environ
    app_env = str(overrides.get("APP_ENV") or env.get("APP_ENV", "production")).lower()
    production = app_env == "production"

    secret = overrides.get("SECRET_KEY") or env.get("SECRET_KEY", "")
    if production and len(secret) < 32:
        raise RuntimeError(
            "SECRET_KEY wajib diisi (minimal 32 karakter) saat APP_ENV=production. "
            'Buat dengan: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    if not secret:  # mode development: kunci sementara, sesi hilang saat server restart
        secret = secrets.token_hex(32)

    admin_key = (
        overrides.get("ADMIN_ACCESS_KEY")
        if "ADMIN_ACCESS_KEY" in overrides
        else overrides.get("TEACHER_ACCESS_KEY")
        if "TEACHER_ACCESS_KEY" in overrides
        else (env.get("ADMIN_ACCESS_KEY") or env.get("TEACHER_ACCESS_KEY", ""))
    )

    cfg = {
        "APP_ENV": app_env,
        "SECRET_KEY": secret,
        # Kunci akses admin (Ketua Kelas, Sekretaris, Wali Kelas): dibaca dari server, tidak pernah dikirim ke klien.
        "ADMIN_ACCESS_KEY": admin_key,
        "DATABASE": env.get("DATABASE_PATH") or str(BASE_DIR / "instance" / "absensi.db"),
        "SESSION_COOKIE_NAME": "absensi_session",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": _flag(env.get("COOKIE_SECURE"), production),
        "TRUST_PROXY": _int("TRUST_PROXY", 0),
        "SESSION_IDLE_MINUTES": _int("SESSION_IDLE_MINUTES", 120),
        "SESSION_ABSOLUTE_HOURS": _int("SESSION_ABSOLUTE_HOURS", 12),
        "LOGIN_WINDOW_MINUTES": 15,
        "LOGIN_MAX_PER_IP": 20,
        "LOGIN_MAX_PER_IP_NAME": 5,
        "LOGIN_MAX_PER_ACCOUNT": 15,
        "MIN_PASSWORD_LENGTH": 8,
        "PASSWORD_HASH_METHOD": env.get("PASSWORD_HASH_METHOD", "scrypt"),
        "MAX_CONTENT_LENGTH": 64 * 1024,  # tidak ada unggah berkas
        "SCHOOL_NAME": env.get("SCHOOL_NAME", "SMKN 8 Kota Bekasi"),
        "CLASS_NAME": env.get("CLASS_NAME", "XI TKJ 1"),
        "NOW_FUNC": None,  # untuk pengujian: fungsi yang mengembalikan datetime WIB
        "TESTING": False,
    }
    cfg.update(overrides)
    if "TEACHER_ACCESS_KEY" in overrides and "ADMIN_ACCESS_KEY" not in overrides:
        cfg["ADMIN_ACCESS_KEY"] = overrides["TEACHER_ACCESS_KEY"]
    return cfg
