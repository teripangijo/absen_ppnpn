import os
import io
import base64
from datetime import datetime, timedelta, date, time
from functools import wraps # Untuk decorator auth

from flask import (Flask, render_template, request, jsonify, Response,
                   flash, redirect, url_for, send_file, get_flashed_messages) # <-- Tambahkan get_flashed_messages
# Jika pakai session Flask (misal untuk flash), perlu secret_key
# from flask import session as flask_session
from flask_basicauth import BasicAuth
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

# Impor model dan fungsi DB dari database.py
# Pastikan AuditLog sudah ada di database.py
from database import init_db, get_db, Employee, Attendance, AuditLog

import pandas as pd

# --- Konfigurasi Aplikasi Flask ---
app = Flask(__name__)
# Secret key SANGAT PENTING untuk flash messages
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'ganti-dengan-kunci-rahasia-yang-kuat-dan-acak')

# --- Konfigurasi Basic Authentication ---
# Ambil dari environment variables atau set default (GANTI DEFAULT!)
app.config['BASIC_AUTH_USERNAME'] = os.environ.get('APP_USERNAME', 'admin')
app.config['BASIC_AUTH_PASSWORD'] = os.environ.get('APP_PASSWORD', 'admin123')
app.config['BASIC_AUTH_FORCE'] = False # Penting: False agar hanya route terdekorasi yg diproteksi

basic_auth = BasicAuth(app)

# --- Inisialisasi Database ---
try:
    with app.app_context():
        init_db()
except Exception as e:
    print(f"FATAL: Failed to initialize database on startup: {e}")

# --- Decorator untuk mewajibkan Basic Auth ---
def require_basic_auth(f):
    """Decorator untuk endpoint yang memerlukan Basic Auth."""
    return basic_auth.required(f)

# --- Routes Aplikasi Utama ---
@app.route('/')
def index():
    """Menampilkan halaman utama absensi dengan dropdown pegawai."""
    db: Session = next(get_db())
    employees = []
    last_attendance_data = None
    selected_employee_id = request.args.get('employee_id', type=int)
    error_message = None

    try:
        employees = db.query(Employee.id, Employee.name).order_by(Employee.name).all()

        if selected_employee_id:
            last_att = db.query(Attendance)\
                .filter(Attendance.employee_id == selected_employee_id)\
                .order_by(desc(Attendance.timestamp))\
                .first()

            if last_att:
                # === PERBAIKAN LegacyAPIWarning ===
                employee = db.get(Employee, selected_employee_id)
                # =================================

                if employee:
                    last_attendance_data = {
                        "id": last_att.id,
                        "employee_id": last_att.employee_id,
                        "employee_name": employee.name,
                        "employee_position": employee.position,
                        "timestamp": last_att.timestamp.isoformat(),
                        "type": last_att.type,
                        "latitude": last_att.latitude,
                        "longitude": last_att.longitude,
                        "photo_base64": base64.b64encode(last_att.photo_blob).decode('utf-8') if last_att.photo_blob else None
                    }
                    # Debug print (opsional)
                    # print(f"DEBUG: Data for {employee.name}: {last_attendance_data}")
                else:
                    # === PERBAIKAN Logika Warning ===
                     print(f"Warning: Employee with ID {selected_employee_id} not found although attendance record exists.")
                     # Kirim data absensi, tapi beri info nama/posisi tidak ada
                     last_attendance_data = {
                        "id": last_att.id, "employee_id": last_att.employee_id,
                        "employee_name": "[Pegawai Dihapus?]", "employee_position": "-",
                        # ... sisa data absensi ...
                        "timestamp": last_att.timestamp.isoformat(), "type": last_att.type,
                        "latitude": last_att.latitude, "longitude": last_att.longitude,
                        "photo_base64": base64.b64encode(last_att.photo_blob).decode('utf-8') if last_att.photo_blob else None
                     }
                     # =============================

    except Exception as e:
        print(f"Error fetching employees or last attendance: {e}")
        flash("Gagal memuat data pegawai atau absensi terakhir.", "danger")
        error_message = "Gagal memuat data. Coba lagi nanti."
    finally:
        db.close()

    return render_template(
        'index.html',
        employees=employees,
        error=error_message,
        last_attendance_data=last_attendance_data,
        selected_employee_id=selected_employee_id
    )


@app.route('/record_attendance', methods=['POST'])
def record_attendance():
    """Menerima dan menyimpan data absensi, dengan validasi sekali sehari."""
    if not request.is_json: return jsonify({"message": "Request harus JSON."}), 400
    data = request.json
    if not data: return jsonify({"message": "Request body JSON kosong."}), 400

    employee_id = data.get('employee_id')
    attendance_type = data.get('type') # 'check_in' or 'check_out'
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    photo_base64 = data.get('photo_base64')

    # Validasi Input Dasar
    if not all([employee_id, attendance_type, photo_base64]):
        return jsonify({"message": "Data tidak lengkap (ID, type, foto wajib)."}), 400
    if attendance_type not in ['check_in', 'check_out']:
        return jsonify({"message": "Tipe absensi tidak valid."}), 400

    db: Session = next(get_db())
    try:
        # Cek apakah pegawai valid
        employee = db.get(Employee, int(employee_id))
        if not employee:
            # Tutup sesi sebelum return
            db.close()
            return jsonify({"message": f"Pegawai ID {employee_id} tidak ditemukan."}), 404

        # === VALIDASI ABSEN SEKALI SEHARI ===
        today = date.today() # Dapatkan tanggal hari ini
        start_of_day = datetime.combine(today, time.min) # Awal hari (00:00:00)
        end_of_day = datetime.combine(today, time.max)   # Akhir hari (23:59:59...)

        # Query untuk mencari record dengan tipe dan pegawai yg sama di hari ini
        existing_record = db.query(Attendance).filter(
            Attendance.employee_id == employee_id,
            Attendance.type == attendance_type,
            Attendance.timestamp >= start_of_day,
            Attendance.timestamp <= end_of_day
        ).first()

        if existing_record:
            action_text = "Masuk" if attendance_type == 'check_in' else "Keluar"
            time_str = existing_record.timestamp.strftime('%H:%M:%S')
            message = f"Anda sudah melakukan Absen {action_text} hari ini pada pukul {time_str}. Absen hanya bisa dilakukan sekali per tipe per hari."
            db.close() # Tutup sesi sebelum return
            return jsonify({"message": message}), 409 # 409 Conflict cocok untuk ini
        # === AKHIR VALIDASI ABSEN SEKALI SEHARI ===

        # === Validasi Radius (jika masih digunakan) ===
        if latitude is not None and longitude is not None:
            # ... (Kode validasi radius tetap sama seperti sebelumnya) ...
            # Jika GAGAL validasi radius: db.close(); return jsonify(...), 403
             distance = haversine_distance(ALLOWED_LATITUDE, ALLOWED_LONGITUDE, latitude, longitude)
             if distance > ALLOWED_RADIUS_METERS:
                 db.close()
                 return jsonify({
                     "message": f"Lokasi Anda ({distance:.0f}m) di luar radius {ALLOWED_RADIUS_METERS}m."
                 }), 403 # 403 Forbidden
        else:
            db.close()
            return jsonify({"message": "Gagal mendapatkan data lokasi Anda."}), 400
        # === Akhir Validasi Radius ===

        # --- Lanjutkan jika semua validasi lolos ---
        try:
            photo_blob = base64.b64decode(photo_base64)
        except Exception as e:
            db.close()
            return jsonify({"message": f"Format foto base64 tidak valid: {e}"}), 400

        new_attendance = Attendance(
            employee_id=employee_id, timestamp=datetime.now(), type=attendance_type,
            latitude=latitude, longitude=longitude, photo_blob=photo_blob
        )
        db.add(new_attendance)
        db.commit()
        db.refresh(new_attendance)

        # Siapkan respons JSON sukses
        response_data = {
            "message": "Absensi berhasil direkam", "id": new_attendance.id,
            "employee_id": new_attendance.employee_id, "employee_name": employee.name,
            "employee_position": employee.position or '-',
            "timestamp": new_attendance.timestamp.isoformat(), "type": new_attendance.type,
            "latitude": new_attendance.latitude, "longitude": new_attendance.longitude,
            "photo_base64": photo_base64
        }
        return jsonify(response_data), 201

    except Exception as e:
        db.rollback()
        print(f"Error recording attendance: {e}")
        return jsonify({"message": "Terjadi kesalahan server saat merekam absensi."}), 500
    finally:
        # Pastikan sesi ditutup di blok finally utama juga
        if db.is_active:
             db.close()


@app.route('/get_attendance_photo/<int:attendance_id>')
def get_attendance_photo(attendance_id):
    """Mengirim data gambar absensi berdasarkan ID."""
    db: Session = next(get_db())
    try:
        attendance = db.get(Attendance, attendance_id) # Sudah benar pakai db.get
        if attendance and attendance.photo_blob:
            return Response(attendance.photo_blob, mimetype='image/jpeg')
        else:
            return "Foto tidak ditemukan", 404
    except Exception as e:
        print(f"Error fetching photo for attendance ID {attendance_id}: {e}")
        return "Gagal mengambil foto", 500
    finally:
        db.close()

# --- Routes Manajemen (Super Admin) ---

@app.route('/manage')
@require_basic_auth
def manage_attendance():
    # ... (Kode route ini tetap sama seperti sebelumnya) ...
    db: Session = next(get_db())
    manage_data = []
    employee_list = []
    name_filter = request.args.get('name', '')
    start_date_str = request.args.get('start', '')
    end_date_str = request.args.get('end', '')
    try:
        employee_list = db.query(Employee.name).order_by(Employee.name).distinct().all()
        employee_names = [name[0] for name in employee_list]
        query = db.query(
                Attendance.id, Employee.name, Employee.position, Attendance.timestamp,
                Attendance.type, Attendance.latitude, Attendance.longitude, Attendance.photo_blob
            ).join(Employee, Attendance.employee_id == Employee.id)
        start_date, end_date = None, None
        if name_filter: query = query.filter(Employee.name == name_filter)
        if start_date_str:
            try: start_date = datetime.strptime(start_date_str, '%Y-%m-%d'); query = query.filter(Attendance.timestamp >= start_date)
            except ValueError: flash("Format tanggal mulai tidak valid (YYYY-MM-DD).", "danger")
        if end_date_str:
            try: end_date = datetime.strptime(end_date_str, '%Y-%m-%d'); query = query.filter(Attendance.timestamp < end_date + timedelta(days=1))
            except ValueError: flash("Format tanggal akhir tidak valid (YYYY-MM-DD).", "danger")
        filtered_attendance = query.order_by(desc(Attendance.timestamp)).all()
        for att_id, emp_name, emp_pos, ts, att_type, lat, lon, photo_exists in filtered_attendance:
            manage_data.append({
                'id': att_id, 'name': emp_name, 'position': emp_pos or '-',
                'timestamp': ts, 'type': att_type, 'latitude': lat, 'longitude': lon,
                'photo_url': url_for('get_attendance_photo', attendance_id=att_id) if photo_exists else None
            })
    except Exception as e: print(f"Error manage: {e}"); flash("Gagal memuat data manajemen.", "danger")
    finally: db.close()
    return render_template('manage_attendance.html', attendance_data=manage_data,
                           employee_names=employee_names, current_filters={'name': name_filter, 'start': start_date_str, 'end': end_date_str})


@app.route('/manage/delete/<int:attendance_id>', methods=['POST'])
@require_basic_auth
def delete_attendance(attendance_id):
    # ... (Kode route ini tetap sama seperti sebelumnya) ...
    db: Session = next(get_db())
    name_filter = request.form.get('name_filter', '')
    start_date_str = request.form.get('start_date_filter', '')
    end_date_str = request.form.get('end_date_filter', '')
    try:
        att = db.get(Attendance, attendance_id)
        if att:
            emp = db.get(Employee, att.employee_id) # Ambil objek employee
            emp_name = emp.name if emp else "[ID Pegawai Tidak Ditemukan]"
            log_details = f"Menghapus absensi '{att.type}' oleh '{emp_name}' ({att.employee_id}) @ {att.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            log = AuditLog(user=request.authorization.username, action="DELETE", record_type="Attendance", record_id=attendance_id, details=log_details)
            db.add(log)
            db.delete(att)
            db.commit()
            flash(f"Data absensi ID {attendance_id} berhasil dihapus.", "success")
        else: flash(f"Data absensi ID {attendance_id} tidak ditemukan.", "warning")
    except Exception as e: db.rollback(); print(f"Error deleting {attendance_id}: {e}"); flash("Gagal menghapus data.", "danger")
    finally: db.close()
    return redirect(url_for('manage_attendance', name=name_filter, start=start_date_str, end=end_date_str))


@app.route('/manage/add', methods=['GET', 'POST'])
@require_basic_auth
def add_attendance():
    """Menampilkan form & memproses penambahan data absensi baru (manual, tanpa foto)."""
    if request.method == 'POST':
        db: Session = next(get_db())
        employees_for_form = [] # Definisikan di luar try-except agar bisa diakses di except
        try:
            employee_id = request.form.get('employee_id', type=int)
            attendance_type = request.form.get('attendance_type')
            timestamp_str = request.form.get('timestamp_str')
            latitude_str = request.form.get('latitude')
            longitude_str = request.form.get('longitude')

            # Validasi
            if not employee_id or not attendance_type or not timestamp_str:
                flash("Pegawai, Tipe Absensi, dan Waktu wajib diisi.", "danger")
                raise ValueError("Input wajib tidak lengkap")

            if attendance_type not in ['check_in', 'check_out']:
                 flash("Tipe absensi tidak valid.", "danger")
                 raise ValueError("Tipe absensi tidak valid")

            try:
                try: timestamp = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S')
                except ValueError: timestamp = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash("Format Waktu tidak valid (gunakan YYYY-MM-DDTHH:MM atau YYYY-MM-DDTHH:MM:SS).", "danger")
                raise ValueError("Format waktu salah")

            latitude = float(latitude_str) if latitude_str and latitude_str.strip() else None # Handle string kosong
            longitude = float(longitude_str) if longitude_str and longitude_str.strip() else None # Handle string kosong

            employee = db.get(Employee, employee_id)
            if not employee:
                 flash(f"Pegawai dengan ID {employee_id} tidak ditemukan.", "danger")
                 raise ValueError("Pegawai tidak ditemukan")

            new_attendance = Attendance(
                employee_id=employee_id, timestamp=timestamp, type=attendance_type,
                latitude=latitude, longitude=longitude, photo_blob=None # Foto None
            )
            db.add(new_attendance)
            db.flush()

            log_details = f"Menambahkan absensi '{attendance_type}' untuk '{employee.name}' ({employee_id}) @ {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            log = AuditLog(user=request.authorization.username, action="CREATE", record_type="Attendance", record_id=new_attendance.id, details=log_details)
            db.add(log)

            db.commit()
            flash("Data absensi baru berhasil ditambahkan.", "success")
            db.close()
            return redirect(url_for('manage_attendance'))

        # === BLOK EXCEPT YANG DIPERBAIKI ===
        except ValueError as ve: # Tangkap error validasi spesifik
            # Flash message sudah diatur di blok validasi sebelumnya saat raise
            # Jadi tidak perlu flash lagi di sini, kecuali jika raise tanpa flash
            db.rollback()
            db.close()
            # Perlu query ulang employees untuk render ulang form
            db_get = next(get_db())
            try:
                 employees_for_form = db_get.query(Employee.id, Employee.name).order_by(Employee.name).all()
            except Exception as query_e:
                 print(f"Error fetching employees after validation error: {query_e}")
            finally:
                 db_get.close()
            # Kembalikan ke form dengan status 400 Bad Request
            return render_template('add_attendance.html', employees=employees_for_form), 400

        except Exception as e: # Tangkap error umum lainnya
            db.rollback()
            print(f"Error adding attendance: {e}")
            # Selalu flash pesan error internal di sini
            flash(f"Gagal menambahkan data absensi baru: Terjadi error internal.", "danger")
            db.close()
            # Render ulang form dengan pesan error, perlu query employees lagi
            db_get: Session = next(get_db())
            try:
                 employees_for_form = db_get.query(Employee.id, Employee.name).order_by(Employee.name).all()
            except Exception as query_e:
                 print(f"Error fetching employees after general error: {query_e}")
            finally:
                 db_get.close()
            # Kembalikan ke form dengan status 500 Internal Server Error
            return render_template('add_attendance.html', employees=employees_for_form), 500
        # === AKHIR BLOK EXCEPT YANG DIPERBAIKI ===

    else: # Metode GET
        db_get: Session = next(get_db())
        employees_for_form = []
        try:
            employees_for_form = db_get.query(Employee.id, Employee.name).order_by(Employee.name).all()
        except Exception as e:
            print(f"Error fetching employees for add form: {e}")
            flash("Gagal memuat daftar pegawai.", "danger")
        finally:
            db_get.close()
        return render_template('add_attendance.html', employees=employees_for_form)


@app.route('/manage/edit/<int:attendance_id>', methods=['GET', 'POST'])
@require_basic_auth
def edit_attendance(attendance_id):
    """Menampilkan form & memproses update data absensi."""
    db: Session = next(get_db()) # Buka sesi di awal untuk GET dan POST

    # Ambil data absensi yg mau diedit
    attendance_to_edit = db.get(Attendance, attendance_id)
    if not attendance_to_edit:
        flash(f"Data absensi ID {attendance_id} tidak ditemukan.", "warning")
        db.close()
        return redirect(url_for('manage_attendance'))

    if request.method == 'POST':
        try:
            old_data_str = f"PegawaiID:{attendance_to_edit.employee_id}, Waktu:{attendance_to_edit.timestamp.strftime('%Y-%m-%dT%H:%M:%S')}, Tipe:{attendance_to_edit.type}, Lat:{attendance_to_edit.latitude}, Lon:{attendance_to_edit.longitude}"
            new_employee_id = request.form.get('employee_id', type=int)
            new_attendance_type = request.form.get('attendance_type')
            new_timestamp_str = request.form.get('timestamp_str')
            new_latitude_str = request.form.get('latitude')
            new_longitude_str = request.form.get('longitude')

            # Validasi (mirip Add)
            if not new_employee_id or not new_attendance_type or not new_timestamp_str: raise ValueError("Input wajib (Pegawai, Tipe, Waktu) tidak lengkap")
            if new_attendance_type not in ['check_in', 'check_out']: raise ValueError("Tipe absensi tidak valid")
            try:
                try: new_timestamp = datetime.strptime(new_timestamp_str, '%Y-%m-%dT%H:%M:%S')
                except ValueError: new_timestamp = datetime.strptime(new_timestamp_str, '%Y-%m-%dT%H:%M')
            except ValueError: raise ValueError("Format waktu salah")
            new_latitude = float(new_latitude_str) if new_latitude_str and new_latitude_str.strip() else None
            new_longitude = float(new_longitude_str) if new_longitude_str and new_longitude_str.strip() else None
            employee_check = db.get(Employee, new_employee_id)
            if not employee_check: raise ValueError("Pegawai ID baru tidak ditemukan")

            # Cek perubahan & buat log
            changes_list = []
            if attendance_to_edit.employee_id != new_employee_id: changes_list.append(f"Pegawai ID: {attendance_to_edit.employee_id} -> {new_employee_id}")
            if attendance_to_edit.timestamp != new_timestamp: changes_list.append(f"Waktu: {attendance_to_edit.timestamp.strftime('%Y-%m-%d %H:%M:%S')} -> {new_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            if attendance_to_edit.type != new_attendance_type: changes_list.append(f"Tipe: {attendance_to_edit.type} -> {new_attendance_type}")
            # Perlu perbandingan yg hati-hati untuk float/None
            old_lat = attendance_to_edit.latitude
            old_lon = attendance_to_edit.longitude
            if (old_lat is None and new_latitude is not None) or \
               (old_lat is not None and new_latitude is None) or \
               (old_lat is not None and new_latitude is not None and abs(old_lat - new_latitude) > 1e-9): # Toleransi float
                   changes_list.append(f"Lat: {old_lat} -> {new_latitude}")
            if (old_lon is None and new_longitude is not None) or \
               (old_lon is not None and new_longitude is None) or \
               (old_lon is not None and new_longitude is not None and abs(old_lon - new_longitude) > 1e-9):
                   changes_list.append(f"Lon: {old_lon} -> {new_longitude}")


            if changes_list:
                attendance_to_edit.employee_id = new_employee_id
                attendance_to_edit.timestamp = new_timestamp
                attendance_to_edit.type = new_attendance_type
                attendance_to_edit.latitude = new_latitude
                attendance_to_edit.longitude = new_longitude

                log_details = f"Mengubah data absensi ID {attendance_id}: {'; '.join(changes_list)}. Data lama: ({old_data_str})"
                log = AuditLog(user=request.authorization.username, action="UPDATE", record_type="Attendance", record_id=attendance_id, details=log_details)
                db.add(log)
                db.commit()
                flash("Data absensi berhasil diperbarui.", "success")
            else:
                 flash("Tidak ada perubahan data yang disimpan.", "info")

            db.close()
            return redirect(url_for('manage_attendance'))

        except ValueError as ve:
            flash(str(ve), "danger")
            db.rollback(); db.close() # Rollback dan tutup sesi
            # Query ulang employees untuk render ulang form
            db_get = next(get_db()); employees = db_get.query(Employee.id, Employee.name).order_by(Employee.name).all(); db_get.close()
            # Perlu objek attendance_to_edit lagi (bisa didapat dari awal atau query lagi)
            db_get2 = next(get_db()); attendance_to_edit_render = db_get2.get(Attendance, attendance_id); db_get2.close()
            return render_template('edit_attendance.html', attendance=attendance_to_edit_render, employees=employees), 400

        except Exception as e:
            db.rollback(); db.close() # Rollback dan tutup sesi
            print(f"Error editing attendance {attendance_id}: {e}")
            flash("Gagal memperbarui data absensi karena error internal.", "danger")
            db_get = next(get_db()); employees = db_get.query(Employee.id, Employee.name).order_by(Employee.name).all(); db_get.close()
            db_get2 = next(get_db()); attendance_to_edit_render = db_get2.get(Attendance, attendance_id); db_get2.close()
            return render_template('edit_attendance.html', attendance=attendance_to_edit_render, employees=employees), 500

    else: # Metode GET
        employees = []
        try:
            employees = db.query(Employee.id, Employee.name).order_by(Employee.name).all()
        except Exception as e:
            print(f"Error fetching employees for edit form: {e}")
            flash("Gagal memuat daftar pegawai.", "danger")
        finally:
            db.close() # Tutup sesi setelah query untuk GET
        return render_template('edit_attendance.html', attendance=attendance_to_edit, employees=employees)


@app.route('/export_filtered_excel')
@require_basic_auth # <-- Pastikan decorator aktif
def export_filtered_excel():
    # ... (Kode export tetap sama seperti sebelumnya) ...
    db: Session = next(get_db())
    name_filter = request.args.get('name', '')
    start_date_str = request.args.get('start', '')
    end_date_str = request.args.get('end', '')
    try:
        query = db.query(
                Attendance.id, Employee.name, Employee.position, Attendance.timestamp,
                Attendance.type, Attendance.latitude, Attendance.longitude
            ).join(Employee, Attendance.employee_id == Employee.id)
        if name_filter: query = query.filter(Employee.name == name_filter)
        if start_date_str:
            try: query = query.filter(Attendance.timestamp >= datetime.strptime(start_date_str, '%Y-%m-%d'))
            except ValueError: pass
        if end_date_str:
            try: query = query.filter(Attendance.timestamp < datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1))
            except ValueError: pass
        filtered_list = query.order_by(desc(Attendance.timestamp)).all()
        df = pd.DataFrame(filtered_list, columns=[
            'ID Absen', 'Nama Pegawai', 'Posisi', 'Waktu', 'Tipe', 'Latitude', 'Longitude'
        ])
        if not df.empty:
            df['Waktu'] = pd.to_datetime(df['Waktu']).dt.strftime('%Y-%m-%d %H:%M:%S')
            df['Tipe'] = df['Tipe'].apply(lambda x: 'Masuk' if x == 'check_in' else ('Keluar' if x == 'check_out' else x))
            # Ambil data foto dalam loop terpisah untuk menghindari N+1 jika memungkinkan
            photo_urls = {}
            att_ids = df['ID Absen'].tolist()
            if att_ids:
                photos_q = db.query(Attendance.id, Attendance.photo_blob).filter(Attendance.id.in_(att_ids)).all()
                photo_urls = {att_id: url_for('get_attendance_photo', attendance_id=att_id, _external=True) for att_id, blob in photos_q if blob}
            df['URL Foto'] = df['ID Absen'].map(photo_urls).fillna('') # Gunakan map untuk efisiensi

        else: df['URL Foto'] = pd.Series(dtype='object')
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, sheet_name='Rekap Absensi Filtered', index=False)
        output.seek(0)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rekap_absensi_filtered_{timestamp_str}.xlsx"
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=filename)
    except Exception as e: print(f"Error exporting: {e}"); flash("Gagal export Excel.", "danger"); return redirect(url_for('manage_attendance', name=name_filter, start=start_date_str, end=end_date_str))
    finally: db.close()


if __name__ == '__main__':
    # Jalankan dengan HTTPS Adhoc untuk development & mobile testing
    print("Starting Flask development server with adhoc SSL (HTTPS)...")
    ssl_context = 'adhoc'
    try: import cryptography
    except ImportError:
        print("WARNING: cryptography library not found, running in HTTP mode."); ssl_context = None
    app.run(host='0.0.0.0', port=5000, debug=True, ssl_context=ssl_context)
