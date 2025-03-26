import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from datetime import datetime

# Tentukan path absolut untuk file database
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'attendance.db')
DATABASE_URL = f'sqlite:///{DATABASE_PATH}'

# Buat engine SQLAlchemy
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}) # check_same_thread False untuk SQLite

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
    position = Column(String, nullable=True)                       # <-- KOLOM BARU: Posisi/Jabatan

    # Relationship ke Attendance (jika pegawai dihapus, absensinya juga terhapus)
    attendances = relationship("Attendance", back_populates="employee", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Employee(id={self.id}, name='{self.name}', position='{self.position}')>"


class Attendance(Base):
    """Model untuk tabel data absensi."""
    __tablename__ = 'attendance'
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id'), nullable=False, index=True) # Foreign key ke Employee
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True) # Waktu absensi
    type = Column(String, nullable=False) # 'check_in' atau 'check_out'
    latitude = Column(Float, nullable=True) # Koordinat Latitude
    longitude = Column(Float, nullable=True) # Koordinat Longitude
    photo_blob = Column(LargeBinary, nullable=False) # Data biner foto

    # Relationship ke Employee
    employee = relationship("Employee", back_populates="attendances")

    def __repr__(self):
        return f"<Attendance(id={self.id}, employee_id={self.employee_id}, type='{self.type}', timestamp='{self.timestamp}')>"

# --- Fungsi Database Lainnya ---
def init_db():
    """Membuat semua tabel dalam metadata jika belum ada.
       Akan mencoba menambahkan kolom baru jika model berubah.
    """
    try:
        print("Attempting to create/update database tables...")
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

# Fungsi ini tidak lagi relevan jika menggunakan import,
# tapi bisa disimpan sebagai referensi atau dihapus.
def add_initial_employees():
    db = next(get_db())
    try:
        if db.query(Employee).count() == 0:
            print("Adding initial employees (DEPRECATED - use import script)...")
            # initial_employees = [...] # Data lama
            # for emp_name in initial_employees:
            #     db.add(Employee(name=emp_name, position=None)) # Position akan NULL
            # db.commit()
    except Exception as e:
        print(f"Error adding initial employees: {e}")
        db.rollback()
    finally:
        db.close()

# Blok untuk menjalankan inisialisasi saat script dipanggil langsung
# Sebaiknya init_db dipanggil dari app.py atau script import
# if __name__ == "__main__":
#     print("Running database setup (only creates tables if needed)...")
#     init_db()
#     print("Database setup finished.")
#     print("(Use import_employees.py to add employees from Excel)")