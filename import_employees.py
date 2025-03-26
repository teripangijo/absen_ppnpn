import pandas as pd
import os
from sqlalchemy.orm import sessionmaker
from database import engine, Base, Employee # Impor model Employee

# --- Konfigurasi ---
EXCEL_FILE_PATH = 'daftar_pegawai.xlsx'  # Ganti jika nama file Excel berbeda
NAME_COLUMN_HEADER = 'Nama Pegawai'      # Sesuaikan dengan header kolom Nama di Excel Anda
POSITION_COLUMN_HEADER = 'Jabatan'       # Sesuaikan dengan header kolom Jabatan di Excel Anda

# Kategori posisi yang diizinkan (untuk validasi)
ALLOWED_POSITIONS = ["Pramu Kantor", "Petugas Keamanan Dalam", "Petugas Kesehatan", "Dokter", "Pengemudi", "Petugas Keamanan BMN"]

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def import_from_excel():
    """Membaca file Excel dan mengimpor/memperbarui nama & posisi pegawai ke database."""
    print(f"Mencoba membaca file Excel: {EXCEL_FILE_PATH}")

    if not os.path.exists(EXCEL_FILE_PATH):
        print(f"ERROR: File Excel '{EXCEL_FILE_PATH}' tidak ditemukan.")
        return

    db = SessionLocal()
    added_count = 0
    skipped_count = 0
    updated_count = 0
    # Ambil data pegawai yg sudah ada sebagai dictionary {nama: objek_employee}
    existing_employees = {emp.name: emp for emp in db.query(Employee).all()}
    print(f"Ditemukan {len(existing_employees)} pegawai di database sebelum import.")

    try:
        df = pd.read_excel(EXCEL_FILE_PATH)
        print(f"File Excel '{EXCEL_FILE_PATH}' berhasil dibaca.")

        # Validasi header kolom
        if NAME_COLUMN_HEADER not in df.columns:
            print(f"ERROR: Kolom '{NAME_COLUMN_HEADER}' tidak ditemukan.")
            return
        if POSITION_COLUMN_HEADER not in df.columns:
            print(f"ERROR: Kolom '{POSITION_COLUMN_HEADER}' tidak ditemukan.")
            return

        print(f"Memproses kolom '{NAME_COLUMN_HEADER}' dan '{POSITION_COLUMN_HEADER}'...")

        # Iterasi melalui baris DataFrame
        for index, row in df.iterrows():
            name = row[NAME_COLUMN_HEADER]
            position = row[POSITION_COLUMN_HEADER]

            # Bersihkan data
            name = str(name).strip() if pd.notna(name) else None
            position = str(position).strip() if pd.notna(position) else None

            # Validasi Nama
            if not name:
                print(f"- Melewati baris {index + 2}: Nama kosong.")
                skipped_count += 1
                continue

            # Validasi Posisi (Jabatan)
            if not position:
                 print(f"- Melewati baris {index + 2} ({name}): Jabatan kosong.")
                 skipped_count += 1
                 continue
            elif position not in ALLOWED_POSITIONS:
                print(f"- Melewati baris {index + 2} ({name}): Jabatan '{position}' tidak valid.")
                skipped_count += 1
                continue

            # Cek apakah pegawai sudah ada
            if name in existing_employees:
                employee = existing_employees[name]
                # Cek apakah posisi perlu diupdate
                if employee.position != position:
                    print(f"* Mengupdate Posisi: {name} ({employee.position} -> {position})")
                    employee.position = position
                    updated_count += 1
                    # Tandai sesi perlu di-commit (jika ada perubahan)
                    if employee not in db.dirty: db.add(employee) # Pastikan objek terdaftar untuk update
                else:
                    # print(f"- Melewati (Sudah Ada & Posisi Sama): {name}") # Opsi: jangan print jika sama
                    skipped_count += 1
            else: # Jika pegawai baru
                print(f"+ Menambahkan Pegawai: {name} ({position})")
                new_employee = Employee(name=name, position=position)
                db.add(new_employee)
                added_count += 1

        # Commit perubahan jika ada penambahan atau update
        if added_count > 0 or updated_count > 0:
            print(f"\nMenyimpan {added_count} penambahan dan {updated_count} update ke database...")
            db.commit()
            print("Perubahan berhasil disimpan.")
        else:
            print("\nTidak ada pegawai baru atau update posisi untuk disimpan.")

    except FileNotFoundError:
        print(f"ERROR: File Excel '{EXCEL_FILE_PATH}' tidak ditemukan.")
    except KeyError as e:
        print(f"ERROR: Kolom header '{e}' tidak ditemukan di file Excel.")
    except Exception as e:
        print(f"\nTerjadi error saat memproses: {e}")
        print("Rollback perubahan...")
        db.rollback()
    finally:
        db.close()
        print("\n--- Ringkasan Proses Import ---")
        print(f"Pegawai baru ditambahkan : {added_count}")
        print(f"Pegawai posisi diupdate  : {updated_count}")
        print(f"Baris dilewati (sudah ada/invalid/kosong): {skipped_count}")

if __name__ == "__main__":
    print("========================================")
    print("      SCRIPT IMPORT PEGAWAI DARI EXCEL")
    print("========================================")
    print("Memastikan tabel database ada/diperbarui...")
    # Pastikan tabel ada sebelum import
    Base.metadata.create_all(bind=engine)
    print("\nMemulai proses impor...")
    import_from_excel()
    print("\nProses impor selesai.")
    print("========================================")