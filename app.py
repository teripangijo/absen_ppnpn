from flask import Flask, render_template, request, jsonify, send_file, Response, flash, redirect, url_for, session as flask_session
from flask_basicauth import BasicAuth
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import init_db, get_db, Employee, Attendance # Impor model dan fungsi DB
from datetime import datetime
import pandas as pd
import io
import base64
import os

app = Flask(__name__)

# --- Konfigurasi ---
# Secret key untuk flash messages dan session (jika digunakan)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'ganti-dengan-kunci-rahasia-yang-kuat')

# Konfigurasi Basic Auth untuk export/recap
# Ganti username dan password ini!
# Sebaiknya gunakan environment variables di production
app.config['BASIC_AUTH_USERNAME'] = os.environ.get('APP_USERNAME', 'admin')
app.config['BASIC_AUTH_PASSWORD'] = os.environ.get('APP_PASSWORD', 'admin123')
app.config['BASIC_AUTH_FORCE'] = False # Wajibkan auth untuk route yg didekorasi

basic_auth = BasicAuth(app)

# Inisialisasi Database (buat tabel jika belum ada) saat aplikasi start
try:
    init_db()
except Exception as e:
    print(f"FATAL: Failed to initialize database on startup: {e}")
    # Di production, mungkin ingin exit atau log error serius

# --- Decorator untuk mewajibkan Basic Auth ---
def require_basic_auth(f):
    """Decorator untuk endpoint yang memerlukan Basic Auth."""
    return basic_auth.required(f)

# --- Routes ---
@app.route('/')
def index():
    """Menampilkan halaman utama absensi."""
    db: Session = next(get_db())
    employees = []
    last_attendance_data = None
    selected_employee_id = request.args.get('employee_id', type=int)
    error_message = None # Inisialisasi error_message

    print(f"DEBUG: Menerima employee_id dari URL: {selected_employee_id}")

    try:
        # Ambil ID dan Nama untuk dropdown
        employees = db.query(Employee.id, Employee.name).order_by(Employee.name).all()

        if selected_employee_id:
            # Ambil absensi terakhir
            last_att = db.query(Attendance)\
                .filter(Attendance.employee_id == selected_employee_id)\
                .order_by(desc(Attendance.timestamp))\
                .first()

            if last_att:
                # Ambil data pegawai LENGKAP (termasuk posisi)
                employee = db.get(Employee, selected_employee_id) # Gunakan db.get

                if employee:
                    last_attendance_data = {
                        "id": last_att.id, # Tambahkan ID absensi jika perlu
                        "employee_id": last_att.employee_id,
                        "employee_name": employee.name,
                        "employee_position": employee.position, # <-- TAMBAHKAN POSISI DI SINI
                        "timestamp": last_att.timestamp.isoformat(),
                        "type": last_att.type,
                        "latitude": last_att.latitude,
                        "longitude": last_att.longitude,
                        "photo_base64": base64.b64encode(last_att.photo_blob).decode('utf-8') if last_att.photo_blob else None
                    }
                    # DEBUG Posisi
                    print(f"Warning: Employee dengan ID {selected_employee_id} tidak ditemukan.")
                     # Jika employee tidak ditemukan, pastikan last_attendance_data tidak dikirim atau kosong
                else:
                     print(f"Warning: Employee with ID {selected_employee_id} not found for last attendance.")
                     # Mungkin set nama default jika employee tidak ditemukan?
                     # last_attendance_data['employee_name'] = "Nama Tidak Ditemukan"
                     # last_attendance_data['employee_position'] = "-"


    except Exception as e:
        print(f"Error fetching employees or last attendance: {e}")
        flash("Gagal memuat data pegawai atau absensi terakhir.", "danger")
        error_message = "Gagal memuat data. Coba lagi nanti." # Set pesan error
    finally:
        db.close()

    return render_template(
        'index.html',
        employees=employees,
        error=error_message, # Kirim error_message ke template
        last_attendance_data=last_attendance_data,
        selected_employee_id=selected_employee_id
    )


@app.route('/record_attendance', methods=['POST'])
def record_attendance():
    """Menerima dan menyimpan data absensi."""
    db: Session = next(get_db())
    data = request.json
    employee_id = data.get('employee_id')
    attendance_type = data.get('type')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    photo_base64 = data.get('photo_base64') # Terima hanya base64 string

    # Validasi Input Sederhana
    if not all([employee_id, attendance_type, photo_base64]):
        return jsonify({"message": "Data tidak lengkap (employee_id, type, photo_base64 wajib ada)."}), 400
    if attendance_type not in ['check_in', 'check_out']:
        return jsonify({"message": "Tipe absensi tidak valid (harus 'check_in' atau 'check_out')."}), 400

    try:
        employee = db.query(Employee).get(employee_id)
        if not employee:
            return jsonify({"message": f"Pegawai dengan ID {employee_id} tidak ditemukan."}), 404

        # Decode foto dari base64
        try:
            photo_blob = base64.b64decode(photo_base64)
        except (base64.binascii.Error, TypeError) as decode_error:
            print(f"Error decoding base64: {decode_error}")
            return jsonify({"message": "Format foto base64 tidak valid."}), 400

        # Buat objek Attendance baru
        new_attendance = Attendance(
            employee_id=employee_id,
            timestamp=datetime.now(), # Gunakan waktu server
            type=attendance_type,
            latitude=latitude,
            longitude=longitude,
            photo_blob=photo_blob
        )

        db.add(new_attendance)
        db.commit()
        db.refresh(new_attendance) # Refresh untuk mendapatkan ID dan timestamp default

        # Siapkan data untuk dikirim balik ke frontend (termasuk nama pegawai)
        response_data = {
            "message": "Absensi berhasil direkam",
            "id": new_attendance.id,
            "employee_id": new_attendance.employee_id,
            "employee_name": employee.name, # Kirim nama pegawai
            "employee_position": employee.position if employee else '-',
            "timestamp": new_attendance.timestamp.isoformat(), # Format ISO untuk JS
            "type": new_attendance.type,
            "latitude": new_attendance.latitude,
            "longitude": new_attendance.longitude,
            "photo_base64": photo_base64 # Kirim balik base64 yg diterima
        }
        return jsonify(response_data), 201 # 201 Created

    except Exception as e:
        db.rollback()
        print(f"Error recording attendance: {e}")
        # Hindari mengirim detail error internal ke client
        return jsonify({"message": f"Terjadi kesalahan internal saat merekam absensi."}), 500
    finally:
        db.close()


@app.route('/get_attendance_photo/<int:attendance_id>')
def get_attendance_photo(attendance_id):
    """Mengirim data gambar absensi berdasarkan ID."""
    db: Session = next(get_db())
    try:
        attendance = db.get(Attendance, attendance_id) #db.query(Attendance).get(attendance_id)
        if attendance and attendance.photo_blob:
            return Response(attendance.photo_blob, mimetype='image/jpeg')
        else:
            return "Foto tidak ditemukan", 404
    except Exception as e:
        print(f"Error fetching photo for attendance ID {attendance_id}: {e}")
        return "Gagal mengambil foto", 500
    finally:
        db.close()


@app.route('/recap')
@require_basic_auth
def recap():
    """Menampilkan halaman rekap absensi semua pegawai (memerlukan auth)."""
    db: Session = next(get_db())
    recap_data = []
    try:
        # Query data termasuk posisi pegawai
        attendance_list = db.query(
                Attendance.id,
                Employee.name,
                Employee.position, # <-- AMBIL POSISI
                Attendance.timestamp,
                Attendance.type,
                Attendance.latitude,
                Attendance.longitude
            )\
            .join(Employee, Attendance.employee_id == Employee.id)\
            .order_by(desc(Attendance.timestamp))\
            .all()

        # Masukkan posisi ke dictionary
        for att_id, employee_name, employee_position, timestamp, att_type, lat, lon in attendance_list:
            recap_data.append({
                'id': att_id,
                'name': employee_name,
                'position': employee_position, # <-- TAMBAHKAN POSISI KE DATA
                'timestamp': timestamp,
                'type': att_type,
                'latitude': lat,
                'longitude': lon,
                'photo_url': url_for('get_attendance_photo', attendance_id=att_id)
            })
    except Exception as e:
        print(f"Error fetching attendance recap: {e}")
        flash("Gagal memuat rekap absensi.", "danger")
    finally:
        db.close()
    return render_template('recap.html', recap_data=recap_data)


@app.route('/export_excel')
#@require_basic_auth
def export_excel():
    """Membuat dan mengirim file Excel berisi rekap absensi (memerlukan auth)."""
    db: Session = next(get_db())
    try:
        # Query data termasuk posisi
        attendance_list = db.query(
                Attendance.id, Employee.name, Employee.position, # <-- AMBIL POSISI
                Attendance.timestamp, Attendance.type,
                Attendance.latitude, Attendance.longitude
            )\
            .join(Employee, Attendance.employee_id == Employee.id)\
            .order_by(desc(Attendance.timestamp))\
            .all()

        # Sesuaikan nama kolom untuk DataFrame
        df = pd.DataFrame(attendance_list, columns=[
            'ID Absen', 'Nama Pegawai', 'Posisi', # <-- NAMA KOLOM UNTUK EXCEL
            'Waktu', 'Tipe', 'Latitude', 'Longitude'
        ])

        # Format kolom Waktu agar mudah dibaca di Excel
        if not df.empty:
            df['Waktu'] = pd.to_datetime(df['Waktu']).dt.strftime('%Y-%m-%d %H:%M:%S')
            df['Tipe'] = df['Tipe'].apply(lambda x: 'Masuk' if x == 'check_in' else ('Keluar' if x == 'check_out' else x))
            df['URL Foto'] = df['ID Absen'].apply(lambda id_abs: url_for('get_attendance_photo', attendance_id=id_abs, _external=True))
        else:
            # Tambahkan kolom URL Foto meskipun DataFrame kosong agar header konsisten
            df['URL Foto'] = pd.Series(dtype='object')


        output = io.BytesIO()
        # Gunakan openpyxl untuk .xlsx
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
             df.to_excel(writer, sheet_name='Rekap Absensi', index=False)

        output.seek(0)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rekap_absensi_{timestamp_str}.xlsx"

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"Error exporting Excel: {e}")
        flash("Gagal mengekspor data ke Excel.", "danger")
        return redirect(url_for('recap'))
    finally:
        db.close()

if __name__ == '__main__':
    # Gunakan host='0.0.0.0' agar bisa diakses dari jaringan lokal
    # debug=True hanya untuk development, jangan gunakan di production
    # Gunakan SSL jika diakses via HTTPS
    # context = ('cert.pem', 'key.pem') # Ganti dengan path sertifikat SSL Anda
    app.run(host='0.0.0.0', port=5000, debug=True, ssl_context='adhoc') # Hapus ssl_context jika tidak pakai HTTPS
    # app.run(host='0.0.0.0', port=5000, debug=False, ssl_context=context) # Contoh dengan HTTPS