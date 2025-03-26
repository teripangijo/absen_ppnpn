import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from datetime import datetime

# Dapatkan path absolut ke direktori tempat script ini berada
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'attendance.db')
DATABASE_URI = f'sqlite:///{DATABASE_PATH}'

# Buat engine database
# echo=False agar tidak menampilkan query SQL di console (set True untuk debug)
engine = create_engine(DATABASE_URI, echo=False)

# Buat session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class untuk model deklaratif
Base = declarative_base()

# --- Model Database ---
class Employee(Base):
    """Model untuk tabel data pegawai."""
    __tablename__ = 'employees'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)

    # Relationship: Satu pegawai bisa memiliki banyak record absensi
    attendances = relationship("Attendance", back_populates="employee", cascade="all, delete-orphan")

class Attendance(Base):
    """Model untuk tabel data absensi."""
    __tablename__ = 'attendance'
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id'), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    type = Column(String, nullable=False) # 'check_in' or 'check_out'
    latitude = Column(Float, nullable=True) # Bisa null jika lokasi tidak didapat
    longitude = Column(Float, nullable=True) # Bisa null jika lokasi tidak didapat
    photo_blob = Column(LargeBinary, nullable=False) # Menyimpan data biner foto

    # Relationship: Setiap record absensi milik satu pegawai
    employee = relationship("Employee", back_populates="attendances")

# --- Fungsi Inisialisasi Database ---
def init_db():
    """Membuat semua tabel dalam metadata jika belum ada."""
    try:
        print("Attempting to create database tables...")
        Base.metadata.create_all(bind=engine)
        print("Database tables check/creation complete.")
    except Exception as e:
        print(f"Error creating database tables: {e}")


def get_db():
    """
    Dependency function untuk mendapatkan session database per request.
    Menggunakan 'yield' untuk memastikan session ditutup setelah request selesai.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def add_initial_employees():
    """Menambahkan beberapa data pegawai awal jika tabel pegawai kosong."""
    db = next(get_db()) # Dapatkan session
    try:
        # Cek apakah sudah ada pegawai
        if db.query(Employee).count() == 0:
            print("Adding initial employees...")
            initial_employees = [
                Employee(name="Budi Santoso"),
                Employee(name="Citra Lestari"),
                Employee(name="Andi Wijaya"),
                Employee(name="Dewi Anggraini"),
            ]
            db.add_all(initial_employees)
            db.commit()
            print(f"{len(initial_employees)} initial employees added.")
        else:
            print("Initial employees already exist or table is populated.")
    except Exception as e:
        print(f"Error adding initial employees: {e}")
        db.rollback() # Rollback jika terjadi error
    finally:
        db.close()

# Blok ini akan dijalankan jika script database.py dieksekusi langsung
if __name__ == "__main__":
    print("Running database setup...")
    init_db()
    add_initial_employees()
    print("Database setup finished.")