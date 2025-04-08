import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, LargeBinary, Text, Boolean, true
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from datetime import datetime

# Tentukan path absolut untuk file database
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'attendance.db')
DATABASE_URL = f'sqlite:///{DATABASE_PATH}'

# Buat engine SQLAlchemy
# check_same_thread=False direkomendasikan untuk SQLite dengan Flask/web apps
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Buat session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Buat base class untuk model deklaratif
Base = declarative_base()

# --- Model Database ---
class Employee(Base):
    """Model untuk tabel data pegawai."""
    __tablename__ = 'employees'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True) # Nama pegawai, unik
    position = Column(String, nullable=True)                       # Posisi/Jabatan
    is_active = Column(Boolean, default=True, nullable=False, server_default=true(), index=True)

    attendances = relationship("Attendance", back_populates="employee", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Employee(id={self.id}, name='{self.name}', position='{self.position}')>"


class Attendance(Base):
    """Model untuk tabel data absensi."""
    __tablename__ = 'attendance'
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id'), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    type = Column(String, nullable=False) # 'check_in' atau 'check_out'
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # --- PERUBAHAN DI SINI: Buat foto opsional ---
    photo_blob = Column(LargeBinary, nullable=True) # <-- Diubah menjadi nullable=True
    # --------------------------------------------

    employee = relationship("Employee", back_populates="attendances")

    def __repr__(self):
        return f"<Attendance(id={self.id}, employee_id={self.employee_id}, type='{self.type}', timestamp='{self.timestamp}')>"

# === TAMBAHKAN MODEL AUDIT LOG ===
class AuditLog(Base):
    """Model untuk mencatat log perubahan data oleh admin."""
    __tablename__ = 'audit_log'
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now) # Waktu log dibuat
    user = Column(String, nullable=True) # Username admin yang melakukan aksi (dari Basic Auth)
    action = Column(String, nullable=False) # CREATE, UPDATE, DELETE
    record_type = Column(String, nullable=False) # Nama tabel/model yang diubah (misal: 'Attendance')
    record_id = Column(Integer, nullable=True) # ID record yang terpengaruh
    details = Column(Text, nullable=True) # Deskripsi perubahan

    def __repr__(self):
        return f"<AuditLog(id={self.id}, user='{self.user}', action='{self.action}', record='{self.record_type}:{self.record_id}')>"
# === AKHIR TAMBAHAN MODEL AUDIT LOG ===


# --- Fungsi Database Lainnya ---
def init_db():
    """Membuat/Memperbarui semua tabel dalam metadata (termasuk audit_log)."""
    try:
        print("Attempting to create/update database tables (including audit_log)...")
        Base.metadata.create_all(bind=engine)
        print("Database tables check/creation complete.")
    except Exception as e:
        print(f"Error creating/updating database tables: {e}")

def get_db():
    """Fungsi generator untuk mendapatkan session database."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Fungsi add_initial_employees (opsional, tidak relevan jika pakai import)
def add_initial_employees():
    # ... (tidak terpakai ...
    pass

# Blok if __name__ == "__main__": bisa dikomentari atau dihapus
# jika init_db dipanggil dari app.py atau script import
# if __name__ == "__main__":
#     print("Running database setup...")
#     init_db()
#     print("Database setup finished.")
