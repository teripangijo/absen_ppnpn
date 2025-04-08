// Pastikan semua kode berada dalam lingkup ini agar dijalankan setelah DOM siap
// dan setelah script library (Leaflet, Choices) dimuat (karena pakai defer)
document.addEventListener('DOMContentLoaded', () => {
    // --- Dapatkan Referensi Elemen DOM ---
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const context = canvas ? canvas.getContext('2d', { willReadFrequently: true }) : null;
    const employeeSelect = document.getElementById('employee'); // Elemen <select> asli
    const checkinBtn = document.getElementById('checkin-btn');
    const checkoutBtn = document.getElementById('checkout-btn');
    const statusDiv = document.getElementById('status');
    const lastAttendanceDiv = document.getElementById('last-attendance');
    const lastPhotoImg = document.getElementById('last-photo');
    const lastEmployeeNameSpan = document.getElementById('last-employee-name');
    // === TAMBAHKAN REFERENSI ELEMEN POSISI ===
    const lastEmployeePositionSpan = document.getElementById('last-employee-position');
    // === AKHIR TAMBAHAN REFERENSI ===
    const lastTimeSpan = document.getElementById('last-time');
    const lastTypeSpan = document.getElementById('last-type');
    const lastLocationCoordsSpan = document.getElementById('last-location-coords');
    const mapContainerDiv = document.getElementById('map-container');
    const mapDiv = document.getElementById('map');

    // === INISIALISASI CHOICES.JS ===
    let choicesInstance = null;
    if (employeeSelect && typeof Choices !== 'undefined') {
        try {
            choicesInstance = new Choices(employeeSelect, {
                searchEnabled: true,
                itemSelectText: '',
                placeholder: true,
                shouldSort: false,
                searchPlaceholderValue: "Ketik nama PPNPN...",
                noResultsText: 'Nama tidak ditemukan',
                noChoicesText: 'Tidak ada pilihan nama',
            });
            console.log("Choices.js initialized.");
        } catch (e) { console.error("Error initializing Choices.js:", e); }
    } else { console.warn("Choices.js library or select element not found."); }
    // === AKHIR INISIALISASI CHOICES.JS ===

    // --- Variabel Global State ---
    let stream = null;
    let map = null; // Instance Leaflet Map untuk halaman utama
    let marker = null; // Instance Leaflet Marker untuk halaman utama
    const defaultZoomLevel = 16;

    // --- Fungsi Helper ---
    function showStatus(message, isError = false) {
        if (!statusDiv) return;
        console[isError ? 'error' : 'log'](message);
        statusDiv.textContent = message;
        statusDiv.classList.toggle('error', isError);
    }

    function setButtonsEnabled(enable) {
        const employeeSelected = employeeSelect && employeeSelect.value !== "";
        if(checkinBtn) checkinBtn.disabled = !enable || !employeeSelected;
        if(checkoutBtn) checkoutBtn.disabled = !enable || !employeeSelected;
    }

    // --- Logika Inti ---

    /** 1. Mengakses dan Memulai Stream Kamera */
    async function startCamera() {
        // ... (Kode fungsi startCamera tetap sama) ...
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return showStatus("Error: Browser tidak mendukung akses kamera.", true);
        if (!video) return showStatus("Error: Elemen video tidak ditemukan.", true);
        if (!canvas || !context) return showStatus("Error: Elemen canvas/context tidak siap.", true);

        showStatus('Menginisialisasi kamera...');
        setButtonsEnabled(false);
        try {
            if (stream) stream.getTracks().forEach(track => track.stop());
            stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
                audio: false
            });
            video.srcObject = stream;
            await video.play();
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            showStatus('Kamera siap. Silakan pilih nama dan absen.');
            setButtonsEnabled(true);
        } catch (err) {
            console.error("Error accessing camera:", err);
            let message = `Error akses kamera: ${err.name}.`;
            if (err.name === "NotAllowedError") message = "Izin akses kamera ditolak.";
            else if (err.name === "NotFoundError") message = "Tidak ada kamera yang ditemukan.";
            else if (err.name === "NotReadableError") message = "Kamera mungkin sedang digunakan oleh aplikasi lain.";
            else if (err.name === "OverconstrainedError") message = "Resolusi kamera tidak didukung.";
            else if (err.name === "TypeError") message = "getUserMedia tidak didukung di konteks tidak aman (non-HTTPS).";
            showStatus(message, true);
            setButtonsEnabled(false);
        }
    }

    /** 2. Mendapatkan Lokasi Geografis Pengguna */
    function getCurrentLocation() {
        // ... (Kode fungsi getCurrentLocation tetap sama) ...
         return new Promise((resolve) => {
            if (!navigator.geolocation) {
                showStatus('Geolocation tidak didukung.', true);
                return resolve({ latitude: null, longitude: null });
            }
            showStatus('Mengambil data lokasi...');
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const coords = { latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy };
                    showStatus(`Lokasi didapatkan (Akurasi: ${coords.accuracy?.toFixed(0)} m).`);
                    resolve(coords);
                },
                (error) => {
                    console.error("Error getting location:", error);
                    let errorMsg = 'Gagal mendapatkan lokasi.';
                    switch (error.code) {
                        case error.PERMISSION_DENIED: errorMsg += " Izin akses lokasi ditolak."; break;
                        case error.POSITION_UNAVAILABLE: errorMsg += " Informasi lokasi tidak tersedia."; break;
                        case error.TIMEOUT: errorMsg += " Waktu permintaan lokasi habis."; break;
                        default: errorMsg += " Error tidak diketahui."; break;
                    }
                    showStatus(errorMsg + " Melanjutkan tanpa data lokasi.", true);
                    resolve({ latitude: null, longitude: null });
                },
                { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
            );
        });
    }

    /** 3. Mengambil Snapshot Foto dari Stream Video */
    function capturePhoto() {
        // ... (Kode fungsi capturePhoto tetap sama) ...
        if (!video.srcObject || video.paused || video.videoWidth === 0 || !context) {
             showStatus('Kamera/Canvas belum siap untuk mengambil foto.', true);
             return null;
        }
        showStatus('Mengambil foto...');
        if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
             canvas.width = video.videoWidth;
             canvas.height = video.videoHeight;
        }
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        try {
            return canvas.toDataURL('image/jpeg', 0.8);
        } catch (e) {
            console.error("Error converting canvas to Data URL:", e);
            showStatus("Gagal mengkonversi gambar.", true);
            return null;
        }
    }

    /** 4. Mengirim Data Absensi ke Backend */
    async function sendAttendanceData(employeeId, type, location, photoBase64) {
        // ... (Kode fungsi sendAttendanceData tetap sama) ...
        showStatus('Merekam data absensi...');
        setButtonsEnabled(false);
        try {
            const response = await fetch('/record_attendance', {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({
                     employee_id: employeeId, type: type,
                     latitude: location.latitude, longitude: location.longitude,
                     photo_base64: photoBase64.split(',')[1]
                 }),
            });
            const result = await response.json();

            if (!response.ok) {
                 throw new Error(result.message || `Server error: ${response.status}`);
            }

            showStatus(`Absensi ${type === 'check_in' ? 'masuk' : 'keluar'} berhasil direkam!`);
            if (typeof window.displayLastAttendance === 'function') {
                window.displayLastAttendance(result);
            }

        } catch (error) {
             console.error('Error recording attendance:', error);
             showStatus(`Error: ${error.message || 'Gagal terhubung ke server'}`, true);
             if(lastAttendanceDiv) lastAttendanceDiv.style.display = 'none';
             if(mapContainerDiv) mapContainerDiv.style.display = 'none';
        } finally {
            setButtonsEnabled(true);
        }
    }

    /** 5. Menampilkan Detail Absensi Terakhir (Termasuk Peta) */
    window.displayLastAttendance = function(data) {
        // Validasi elemen UI, tambahkan pengecekan untuk elemen posisi
        if (!lastAttendanceDiv || !lastPhotoImg || !lastEmployeeNameSpan || !lastEmployeePositionSpan || !lastTimeSpan || !lastTypeSpan || !lastLocationCoordsSpan || !mapContainerDiv || !mapDiv) {
            console.error("Satu atau lebih elemen UI untuk hasil absensi tidak ditemukan.");
            return;
        }

        // Tampilkan/Sembunyikan berdasarkan data
        const hasValidData = data && data.photo_base64;
        lastAttendanceDiv.style.display = hasValidData ? 'block' : 'none';
        mapContainerDiv.style.display = 'none'; // Sembunyikan peta dulu
        if (map) { try { map.remove(); } catch(e){} map = null; marker = null; } // Hapus map lama

        if (!hasValidData) return; // Stop jika tidak ada data

        // Isi detail dasar
        lastPhotoImg.src = `data:image/jpeg;base64,${data.photo_base64}`;
        lastEmployeeNameSpan.textContent = data.employee_name || 'N/A';
        // === ISI DATA POSISI ===
        lastEmployeePositionSpan.textContent = data.employee_position || '-';
        // === AKHIR ISI DATA POSISI ===
        const timestamp = data.timestamp ? new Date(data.timestamp) : null;
        lastTimeSpan.textContent = timestamp ? timestamp.toLocaleString('id-ID', { dateStyle: 'full', timeStyle: 'long'}) : 'N/A';
        lastTypeSpan.textContent = data.type === 'check_in' ? 'Masuk' : (data.type === 'check_out' ? 'Keluar' : 'N/A');

        // --- Logika Peta Leaflet untuk Halaman Utama ---
        const hasCoords = data.latitude != null && data.longitude != null;
        const leafletLoaded = typeof L !== 'undefined';
        lastLocationCoordsSpan.textContent = hasCoords ? `${data.latitude.toFixed(6)}, ${data.longitude.toFixed(6)}` : 'Lokasi tidak tersedia';

        if (hasCoords && leafletLoaded) {
            mapContainerDiv.style.display = 'block'; // Tampilkan kontainer peta
            const lat = data.latitude; const lon = data.longitude;
            // === UPDATE KONTEN POPUP PETA DENGAN POSISI ===
            const popupContent = `<b>${data.employee_name || 'Pegawai'} (${data.employee_position || 'N/A'})</b><br>${lastTypeSpan.textContent}: ${timestamp ? timestamp.toLocaleTimeString('id-ID') : '-'}`;
            // === AKHIR UPDATE POPUP ===

            try {
                // Inisialisasi peta jika belum ada
                map = L.map(mapDiv).setView([lat, lon], defaultZoomLevel);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OSM' }).addTo(map);
                marker = L.marker([lat, lon]).addTo(map).bindPopup(popupContent);

                // Invalidate size setelah visible
                setTimeout(() => {
                    if (map) map.invalidateSize();
                    if (marker) marker.openPopup(); // Buka popup
                }, 100); // Beri jeda agar map sempat render
            } catch (e) {
                 console.error("Error initializing/updating main page map:", e);
                 mapContainerDiv.innerHTML = "<p class='error'>Gagal memuat peta.</p>"; // Tampilkan pesan error di kontainer
                 map = null; marker = null;
            }
        } else if (hasCoords && !leafletLoaded) {
             console.warn("Leaflet library (L) not loaded, cannot display map.");
             mapContainerDiv.style.display = 'block'; // Tampilkan kontainer
             mapContainerDiv.innerHTML = "<p class='error'>Library peta tidak termuat.</p>"; // Tampilkan pesan error di kontainer
        }
        // Jika tidak ada coords, mapContainerDiv tetap 'none'
    } // <-- Akhir dari window.displayLastAttendance

    /** 6. Fungsi Utama Pengendali Proses Absensi (DIMODIFIKASI DENGAN KONFIRMASI) */
    async function handleAttendance(type) {
        const selectedEmployeeId = employeeSelect ? employeeSelect.value : null;
        if (!selectedEmployeeId) {
            showStatus('GAGAL: Silakan pilih nama PPNPN terlebih dahulu.', true);
            if (choicesInstance?.input?.element) choicesInstance.input.element.focus();
            else if (employeeSelect) employeeSelect.focus();
            return;
        }

        // === TAMBAHKAN KONFIRMASI ===
        const actionText = type === 'check_in' ? 'Masuk' : 'Keluar';
        const confirmation = confirm(`Anda yakin ingin melakukan Absen ${actionText} untuk pegawai terpilih?`);

        if (!confirmation) {
            showStatus("Absen dibatalkan oleh pengguna.");
            // Pastikan tombol kembali aktif jika dibatalkan sebelum proses dimulai
            setButtonsEnabled(true);
            return; // Hentikan proses jika pengguna memilih "Tidak" (Cancel)
        }
        // === AKHIR KONFIRMASI ===

        // Lanjutkan proses jika dikonfirmasi "Yakin" (OK)
        showStatus(`Memproses Absen ${actionText}...`); // Update status
        setButtonsEnabled(false);
        if (lastAttendanceDiv) lastAttendanceDiv.style.display = 'none';
        if (mapContainerDiv) mapContainerDiv.style.display = 'none';

        try {
            // 1. Dapatkan Lokasi (async)
            const location = await getCurrentLocation();
            if (location.latitude === null || location.longitude === null) {
                 showStatus('GAGAL: Tidak bisa mendapatkan lokasi Anda. Absensi dibatalkan.', true);
                 setButtonsEnabled(true);
                 return;
            }

            // 2. Validasi Radius Sisi Klien (jika ada)
            //if (!isNaN(allowedLatitude) && !isNaN(allowedLongitude) && !isNaN(allowedRadius)) {
            //    const distance = haversineDistance(allowedLatitude, allowedLongitude, location.latitude, location.longitude);
            //     console.log(`DEBUG KLIEN: Jarak terhitung: ${distance.toFixed(2)} meter`);
            //    if (distance > allowedRadius) {
            //        showStatus(`GAGAL: Lokasi Anda (${distance.toFixed(0)}m) di luar radius ${allowedRadius}m.`, true);
            //        setButtonsEnabled(true);
            //        return;
            //    } else {
            //         showStatus(`Lokasi valid (${distance.toFixed(0)}m). Mengambil foto...`); // Update status
            //    }
            //}

            // 3. Ambil Foto
            const photoBase64 = capturePhoto();
            if (!photoBase64) {
                setButtonsEnabled(true);
                return;
            }

            // 4. Kirim Data ke Backend (async)
            // Status akan diupdate lagi di dalam sendAttendanceData
            await sendAttendanceData(selectedEmployeeId, type, location, photoBase64);

        } catch (error) {
            console.error("Unexpected error during attendance process:", error);
            showStatus(`Proses absensi gagal: ${error.message || 'Error tidak diketahui'}`, true);
            setButtonsEnabled(true);
        }
        // Tombol akan di-enable lagi di finally block sendAttendanceData
    }

    // --- Event Listeners ---
    if(checkinBtn) checkinBtn.addEventListener('click', () => handleAttendance('check_in'));
    if(checkoutBtn) checkoutBtn.addEventListener('click', () => handleAttendance('check_out'));

    // Listener dropdown pegawai
    if(employeeSelect) {
        employeeSelect.addEventListener('change', () => {
            const selectedId = employeeSelect.value;
            setButtonsEnabled(stream != null && selectedId !== ""); // Enable jika nama dipilih DAN kamera siap

            // Reload halaman untuk memuat data absensi terakhir
            if (selectedId) {
                window.location.href = `/?employee_id=${selectedId}`;
            } else {
                 // Jika kembali ke "-- Pilih Nama --"
                 if(lastAttendanceDiv) lastAttendanceDiv.style.display = 'none';
                 if(mapContainerDiv) mapContainerDiv.style.display = 'none';
                 if(map) { try{ map.remove() } catch(e){} map = null; marker = null; }
                 window.location.href = '/'; // Kembali ke URL root
            }
        });
    }

    // --- Inisialisasi Awal ---
    startCamera(); // Mulai kamera saat halaman dimuat
    // Cek jika ada pegawai yang sudah terpilih saat load (dari reload)
    setButtonsEnabled(stream != null && employeeSelect?.value !== "");

}); // Akhir DOMContentLoaded
