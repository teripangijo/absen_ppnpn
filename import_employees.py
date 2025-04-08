# import_employees.py
import pandas as pd
import os
from sqlalchemy.orm import sessionmaker
# Impor model Employee dan fungsi/engine dari database.py
from database import engine, Base, Employee, init_db

# --- Konfigurasi (Tetap sama) ---
EXCEL_FILE_PATH = 'daftar_pegawai.xlsx'
NAME_COLUMN_HEADER = 'Nama Pegawai'
POSITION_COLUMN_HEADER = 'Jabatan'
ALLOWED_POSITIONS = ["Pramu Kantor", "Petugas Keamanan Dalam", "Petugas Kesehatan", "Pengemudi", "Dokter", "Petugas Kesehatan BMN"] # Sesuaikan dengan list lengkap Anda

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def import_or_update_employees():
    """Impor, update posisi, dan nonaktifkan pegawai berdasarkan Excel."""
    print(f"Membaca file Excel: {EXCEL_FILE_PATH}")
    if not os.path.exists(EXCEL_FILE_PATH):
        print(f"ERROR: File Excel '{EXCEL_FILE_PATH}' tidak ditemukan.")
        return

    db = SessionLocal()
    added_count = 0
    updated_pos_count = 0
    reactivated_count = 0
    deactivated_count = 0
    skipped_invalid_count = 0

    try:
        df = pd.read_excel(EXCEL_FILE_PATH)
        if NAME_COLUMN_HEADER not in df.columns or POSITION_COLUMN_HEADER not in df.columns:
            print(f"ERROR: Pastikan kolom '{NAME_COLUMN_HEADER}' dan '{POSITION_COLUMN_HEADER}' ada di Excel.")
            return

        # 1. Dapatkan data valid dari Excel (nama sebagai key)
        excel_employees = {}
        for index, row in df.iterrows():
            name = str(row[NAME_COLUMN_HEADER]).strip() if pd.notna(row[NAME_COLUMN_HEADER]) else None
            position = str(row[POSITION_COLUMN_HEADER]).strip() if pd.notna(row[POSITION_COLUMN_HEADER]) else None

            if not name or not position:
                print(f"- Melewati baris {index + 2} Excel: Nama atau Jabatan kosong.")
                skipped_invalid_count += 1
                continue
            if position not in ALLOWED_POSITIONS:
                print(f"- Melewati baris {index + 2} Excel ({name}): Jabatan '{position}' tidak valid.")
                skipped_invalid_count += 1
                continue

            # Jika nama duplikat di Excel, gunakan yang terakhir
            excel_employees[name] = position

        print(f"Ditemukan {len(excel_employees)} data pegawai valid di Excel.")

        # 2. Dapatkan data pegawai dari DB (nama sebagai key)
        db_employees = {emp.name: emp for emp in db.query(Employee).all()}
        print(f"Ditemukan {len(db_employees)} pegawai di Database.")

        # 3. Proses Tambah/Update/Reaktivasi
        for name, position in excel_employees.items():
            if name in db_employees:
                # Pegawai sudah ada di DB
                employee = db_employees[name]
                needs_update = False
                # Update posisi jika berbeda
                if employee.position != position:
                    print(f"* Mengupdate Posisi: {name} ({employee.position} -> {position})")
                    employee.position = position
                    needs_update = True
                # Aktifkan kembali jika sebelumnya nonaktif
                if not employee.is_active:
                    print(f"* Mengaktifkan Kembali: {name}")
                    employee.is_active = True
                    reactivated_count += 1
                    needs_update = True

                if needs_update:
                     updated_pos_count += 1 # Hitung sebagai update jika posisi berubah atau reaktivasi
                     if employee not in db.dirty: db.add(employee) # Pastikan terdaftar untuk update
                # Hapus dari dict agar tahu mana yg perlu dinonaktifkan nanti
                del db_employees[name]
            else:
                # Pegawai baru
                print(f"+ Menambahkan Pegawai: {name} ({position})")
                new_employee = Employee(name=name, position=position, is_active=True)
                db.add(new_employee)
                added_count += 1

        # 4. Proses Nonaktifkan Pegawai
        # Pegawai yang tersisa di db_employees adalah yang tidak ada di Excel
        for name_to_deactivate, employee_to_deactivate in db_employees.items():
            if employee_to_deactivate.is_active: # Hanya nonaktifkan yang masih aktif
                print(f"- Menonaktifkan Pegawai (tidak ada di Excel): {name_to_deactivate}")
                employee_to_deactivate.is_active = False
                deactivated_count += 1
                if employee_to_deactivate not in db.dirty: db.add(employee_to_deactivate)

        # 5. Commit Perubahan
        if db.new or db.dirty: # Cek jika ada penambahan atau perubahan
            print("\nMenyimpan perubahan ke database...")
            db.commit()
            print("Perubahan berhasil disimpan.")
        else:
            print("\nTidak ada perubahan data pegawai di database.")

    except Exception as e:
        print(f"\nTerjadi error: {e}")
        print("Rollback perubahan...")
        db.rollback()
    finally:
        db.close()
        print("\n--- Ringkasan Proses Import/Update ---")
        print(f"Pegawai baru ditambahkan : {added_count}")
        print(f"Posisi pegawai diupdate  : {updated_pos_count}") # Termasuk reaktivasi
        print(f"Pegawai diaktifkan kembali: {reactivated_count}")
        print(f"Pegawai dinonaktifkan   : {deactivated_count}")
        print(f"Baris Excel dilewati    : {skipped_invalid_count}")

if __name__ == "__main__":
    print("==============================================")
    print(" SCRIPT IMPORT/UPDATE PEGAWAI DARI EXCEL")
    print("==============================================")
    print("Memastikan tabel database ada/diperbarui...")
    init_db() # Panggil init_db untuk buat tabel jika belum ada
    print("\nMemulai proses import/update...")
    import_or_update_employees() # Ganti nama fungsi yg dipanggil
    print("\nProses import/update selesai.")
    print("==============================================")
