-- Skema Absensi XI TKJ 1 (Mode Admin / Pengurus Kelas). Semua tanggal memakai teks ISO (WIB).

CREATE TABLE classes (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    school_name   TEXT NOT NULL,
    academic_year TEXT
);

-- Akun login khusus Admin (Ketua Kelas, Sekretaris, dan Wali Kelas).
-- Siswa tidak memiliki akun login mandiri.
CREATE TABLE users (
    id                   INTEGER PRIMARY KEY,
    role                 TEXT NOT NULL DEFAULT 'admin' CHECK (role = 'admin'),
    full_name            TEXT NOT NULL,
    name_key             TEXT NOT NULL,          -- nama ternormalisasi untuk login
    password_hash        TEXT NOT NULL,
    is_active            INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0,1)),
    created_at           TEXT NOT NULL,
    last_login_at        TEXT,
    UNIQUE (role, name_key)
);

-- Data master siswa kelas (tanpa akun login).
CREATE TABLE students (
    id         INTEGER PRIMARY KEY,
    class_id   INTEGER NOT NULL REFERENCES classes(id),
    full_name  TEXT NOT NULL,
    name_key   TEXT NOT NULL,
    roll_no    INTEGER,
    nis        TEXT UNIQUE,
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    UNIQUE (class_id, name_key)
);
CREATE INDEX idx_students_class ON students(class_id);
CREATE UNIQUE INDEX ux_students_roll ON students(class_id, roll_no) WHERE roll_no IS NOT NULL;

CREATE TABLE attendance_records (
    id           INTEGER PRIMARY KEY,
    student_id   INTEGER NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
    att_date     TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('H','I','S','A')),
    note         TEXT,
    submitted_at TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'admin' CHECK (source IN ('admin')),
    updated_at   TEXT,
    updated_by   INTEGER REFERENCES users(id),
    UNIQUE (student_id, att_date)               -- mencegah presensi ganda di level database
);
CREATE INDEX idx_att_date ON attendance_records(att_date);

CREATE TABLE attendance_corrections (
    id           INTEGER PRIMARY KEY,
    record_id    INTEGER NOT NULL REFERENCES attendance_records(id) ON DELETE RESTRICT,
    old_status   TEXT,
    new_status   TEXT NOT NULL CHECK (new_status IN ('H','I','S','A')),
    old_note     TEXT,
    new_note     TEXT,
    reason       TEXT NOT NULL,
    corrected_by INTEGER NOT NULL REFERENCES users(id),
    corrected_at TEXT NOT NULL
);
CREATE INDEX idx_corr_record ON attendance_corrections(record_id);

CREATE TABLE sessions (
    token_hash   TEXT PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX idx_sessions_user ON sessions(user_id);

CREATE TABLE login_attempts (
    id           INTEGER PRIMARY KEY,
    attempted_at TEXT NOT NULL,
    ip           TEXT NOT NULL,
    role         TEXT NOT NULL,
    name_key     TEXT NOT NULL,
    success      INTEGER NOT NULL CHECK (success IN (0,1))
);
CREATE INDEX idx_attempts_time ON login_attempts(attempted_at);
CREATE INDEX idx_attempts_ip ON login_attempts(ip, attempted_at);
CREATE INDEX idx_attempts_name ON login_attempts(name_key, attempted_at);

CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
