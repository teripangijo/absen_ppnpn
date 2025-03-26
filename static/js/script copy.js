document.addEventListener('DOMContentLoaded', () => {
    // --- Dapatkan Referensi Elemen DOM ---
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const context = canvas.getContext('2d', { willReadFrequently: true }); // willReadFrequently bisa optimasi
    const employeeSelect = document.getElementById('employee');
    const checkinBtn = document.getElementById('checkin-btn');
    const checkoutBtn = document.getElementById('checkout-btn');
    const statusDiv = document.getElementById('status');
    const lastAttendanceDiv = document.getElementById('last-attendance');
    const lastPhotoImg = document.getElementById('last-photo');
    const lastEmployeeNameSpan = document.getElementById('last-employee-name');
    const lastTimeSpan = document.getElementById('last-time');
    const lastTypeSpan = document.getElementById('last-type');
    const lastLocationCoordsSpan = document.getElementById('last-location-coords');
    const mapContainerDiv = document.getElementById('map-container');
    const mapDiv = document.getElementById('map');

    // --- Variabel Global State ---
    let stream = null; // Untuk menyimpan stream kamera
    let map = null; // Instance Leaflet Map
    let marker = null; // Instance Leaflet Marker
    const defaultZoomLevel = 16; // Zoom level default untuk peta

    // --- Fungsi Helper ---
    /**
     * Menampilkan pesan status di UI.
     * @param {string} message - Pesan yang akan ditampilkan.
     * @param {boolean} [isError=false] - Tandai jika ini pesan error.
     */
    function showStatus(message, isError = false) {
        console[isError ? 'error' : 'log'](message); // Log ke console juga
        statusDiv.textContent = message;
        if (isError) {
            statusDiv.classList.add('error'); // Tambah kelas CSS error
        } else {
            statusDiv.classList.remove('error'); // Hapus kelas CSS error
        }
    }

    /**
     * Mengaktifkan atau menonaktifkan tombol absensi.
     * @param {boolean} enable - True untuk mengaktifkan, false untuk menonaktifkan.
     */
    function setButtonsEnabled(enable) {
        // Hanya aktifkan jika ada pilihan pegawai
        const employeeSelected = employeeSelect && employeeSelect.value !== "";
        checkinBtn.disabled = !enable || !employeeSelected;
        checkoutBtn.disabled = !enable || !employeeSelected;
    }

    // --- Logika Inti ---

    /** 1. Mengakses dan Memulai Stream Kamera */
    async function startCamera() {
        showStatus('Menginisialisasi kamera...');
        setButtonsEnabled(false); // Nonaktifkan tombol saat inisialisasi
        try {
            // Hentikan stream lama jika ada (misal saat ganti kamera)
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
            }
            // Minta akses stream video dari kamera pengguna (depan)
            stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }, // Minta resolusi ideal
                audio: false
            });
            video.srcObject = stream;
            video.onloadedmetadata = () => {
                 video.play(); // Mulai mainkan video setelah metadata siap
                 // Set ukuran canvas sesuai video setelah play (lebih reliable)
                 canvas.width = video.videoWidth;
                 canvas.height = video.videoHeight;
                 showStatus('Kamera siap. Silakan pilih nama dan absen.');
                 setButtonsEnabled(true); // Aktifkan tombol setelah kamera siap
            };
        } catch (err) {
            console.error("Error accessing camera:", err);
            let message = `Error mengakses kamera: ${err.name} - ${err.message}.`;
            if (err.name === "NotAllowedError") {
                message = "Izin akses kamera ditolak. Mohon izinkan akses kamera di pengaturan browser.";
            } else if (err.name === "NotFoundError") {
                message = "Tidak ada kamera yang ditemukan di perangkat ini.";
            } else if (err.name === "NotReadableError") {
                 message = "Kamera sedang digunakan oleh aplikasi lain atau terjadi masalah hardware.";
            }
            showStatus(message, true);
            setButtonsEnabled(false); // Pastikan tombol nonaktif jika kamera gagal
        }
    }

    /** 2. Mendapatkan Lokasi Geografis Pengguna */
    function getCurrentLocation() {
        return new Promise((resolve) => {
            // Cek dukungan Geolocation API
            if (!navigator.geolocation) {
                showStatus('Geolocation tidak didukung oleh browser ini.', true);
                resolve({ latitude: null, longitude: null }); // Lanjutkan tanpa lokasi
                return;
            }

            showStatus('Mengambil data lokasi...');
            navigator.geolocation.getCurrentPosition(
                // --- Success Callback ---
                (position) => {
                    const coords = {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                        accuracy: position.coords.accuracy // Bisa disimpan jika perlu
                    };
                    showStatus(`Lokasi didapatkan (Akurasi: ${coords.accuracy?.toFixed(0)} m).`);
                    resolve(coords); // Kirim data koordinat
                },
                // --- Error Callback ---
                (error) => {
                    console.error("Error getting location:", error);
                    let errorMsg = 'Gagal mendapatkan lokasi.';
                    switch(error.code) {
                        case error.PERMISSION_DENIED: errorMsg = "Izin lokasi ditolak."; break;
                        case error.POSITION_UNAVAILABLE: errorMsg = "Informasi lokasi tidak tersedia."; break;
                        case error.TIMEOUT: errorMsg = "Waktu permintaan lokasi habis."; break;
                    }
                    showStatus(errorMsg + " Melanjutkan tanpa data lokasi.", true);
                    resolve({ latitude: null, longitude: null }); // Lanjutkan tanpa lokasi
                },
                // --- Options ---
                {
                    enableHighAccuracy: true, // Minta akurasi tinggi (jika tersedia)
                    timeout: 15000,           // Waktu tunggu maksimal 15 detik
                    maximumAge: 0             // Jangan gunakan cache lokasi lama
                }
            );
        });
    }

    /** 3. Mengambil Snapshot Foto dari Stream Video */
    function capturePhoto() {
        if (!video.srcObject || video.paused || video.videoWidth === 0) {
             showStatus('Kamera belum siap untuk mengambil foto.', true);
             return null; // Kembalikan null jika kamera tidak siap
        }
        showStatus('Mengambil foto...');
        // Pastikan dimensi canvas sesuai video saat ini
        if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
             canvas.width = video.videoWidth;
             canvas.height = video.videoHeight;
        }
        // Gambar frame video ke canvas
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        // Konversi canvas ke data URL (base64 encoded JPEG)
        // Kualitas 0.8 (80%) adalah kompromi bagus antara ukuran dan kualitas
        try {
            const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
            showStatus('Foto berhasil diambil.');
            return dataUrl; // String base64 diawali dengan "data:image/jpeg;base64,"
        } catch (e) {
            console.error("Error converting canvas to Data URL:", e);
            showStatus("Gagal mengkonversi gambar.", true);
            return null;
        }
    }

    /** 4. Mengirim Data Absensi ke Backend */
    async function sendAttendanceData(employeeId, type, location, photoBase64) {
        showStatus('Merekam data absensi...');
        setButtonsEnabled(false); // Nonaktifkan tombol selama pengiriman

        try {
            const response = await fetch('/record_attendance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    employee_id: employeeId,
                    type: type,
                    latitude: location.latitude,
                    longitude: location.longitude,
                    // Kirim hanya bagian base64-nya, tanpa "data:image/jpeg;base64,"
                    photo_base64: photoBase64.split(',')[1]
                }),
            });

            // Cek jika response TIDAK sukses (status code bukan 2xx)
            if (!response.ok) {
                let errorData = { message: `Server error: ${response.statusText} (${response.status})` };
                try {
                    // Coba parse body error jika ada (mungkin berisi pesan spesifik)
                    errorData = await response.json();
                } catch (e) { /* Abaikan jika body bukan JSON */ }
                throw new Error(errorData.message || `Gagal merekam absensi.`);
            }

            // Jika response sukses (status code 2xx)
            const result = await response.json(); // Parse data JSON dari backend
            showStatus(`Absensi ${type === 'check_in' ? 'masuk' : 'keluar'} berhasil direkam!`);
            displayLastAttendance(result); // Tampilkan hasil absensi terakhir

        } catch (error) {
            console.error('Error recording attendance:', error);
            showStatus(`Error: ${error.message}`, true);
            // Jangan tampilkan hasil jika error
            lastAttendanceDiv.style.display = 'none';
            mapContainerDiv.style.display = 'none';
        } finally {
            // Apapun hasilnya (sukses/gagal), aktifkan kembali tombol
            setButtonsEnabled(true);
        }
    }

    /** 5. Menampilkan Detail Absensi Terakhir (Termasuk Peta) */
    function displayLastAttendance(data) {
        // Sembunyikan jika tidak ada data valid atau foto
        if (!data || !data.photo_base64) {
            lastAttendanceDiv.style.display = 'none';
            mapContainerDiv.style.display = 'none';
            // Hapus map jika ada saat data tidak valid
            if (map) { map.remove(); map = null; marker = null; }
            return;
        }

        // Isi detail dasar
        lastPhotoImg.src = `data:image/jpeg;base64,${data.photo_base64}`;
        lastEmployeeNameSpan.textContent = data.employee_name || 'N/A';
        const timestamp = data.timestamp ? new Date(data.timestamp) : null;
        lastTimeSpan.textContent = timestamp ? timestamp.toLocaleString('id-ID', { dateStyle: 'full', timeStyle: 'long'}) : 'N/A';
        lastTypeSpan.textContent = data.type === 'check_in' ? 'Masuk' : (data.type === 'check_out' ? 'Keluar' : 'N/A');

        // Tampilkan div hasil utama
        lastAttendanceDiv.style.display = 'block';

        // --- Logika Peta Leaflet ---
        if (data.latitude != null && data.longitude != null) {
            const lat = data.latitude;
            const lon = data.longitude;
            const locationString = `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
            lastLocationCoordsSpan.textContent = locationString;

            // Tampilkan kontainer peta
            mapContainerDiv.style.display = 'block';

            const popupContent = `
                <b>${data.employee_name || 'Pegawai'}</b> (${data.type === 'check_in' ? 'Masuk' : 'Keluar'})<br>
                ${timestamp ? timestamp.toLocaleString('id-ID', { timeStyle: 'short'}) : '-'}<br>
                <a href="https://www.google.com/maps?q=${lat},${lon}" target="_blank" rel="noopener noreferrer">Lihat di Google Maps</a>
            `;

            // Inisialisasi peta JIKA belum ada
            if (!map) {
                console.log("Initializing Leaflet map...");
                try {
                    map = L.map(mapDiv).setView([lat, lon], defaultZoomLevel);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                        maxZoom: 19,
                        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    }).addTo(map);
                    marker = L.marker([lat, lon]).addTo(map)
                        .bindPopup(popupContent);
                } catch (e) {
                    console.error("Error initializing Leaflet map:", e);
                    mapContainerDiv.innerHTML = "<p style='color:red;'>Gagal memuat peta.</p>"; // Tampilkan pesan error di container
                    map = null; // Reset map state
                }
            } else { // JIKA peta sudah ada, update
                console.log("Updating existing map...");
                try {
                    map.setView([lat, lon], defaultZoomLevel);
                    marker.setLatLng([lat, lon])
                          .setPopupContent(popupContent);
                } catch (e) {
                     console.error("Error updating Leaflet map:", e);
                     // Mungkin tampilkan pesan error sementara
                }
            }

            // Pastikan ukuran peta valid setelah container visible (SANGAT PENTING)
            // Diberi sedikit timeout agar render DOM selesai
            setTimeout(() => {
                if (map) {
                     try {
                          map.invalidateSize();
                          // Buka popup setelah ukuran valid (opsional)
                          if (marker) marker.openPopup();
                     } catch (e) {
                          console.error("Error invalidating map size:", e);
                     }
                }
            }, 100); // Naikkan sedikit timeout jika masih bermasalah

        } else { // Jika tidak ada koordinat
            lastLocationCoordsSpan.textContent = 'Lokasi tidak tersedia';
            mapContainerDiv.style.display = 'none'; // Sembunyikan kontainer peta
            // Hapus map jika sebelumnya ada agar bersih
             if (map) {
                 try { map.remove(); } catch(e){} // Coba hapus, abaikan error jika sudah dihapus
                 map = null;
                 marker = null;
             }
        }
    }

    /** 6. Fungsi Utama Pengendali Proses Absensi */
    async function handleAttendance(type) {
        const selectedEmployeeId = employeeSelect.value;
        // Validasi pegawai dipilih
        if (!selectedEmployeeId) {
            showStatus('GAGAL: Silakan pilih nama pegawai terlebih dahulu.', true);
            employeeSelect.focus(); // Fokuskan ke dropdown
            return;
        }

        // Nonaktifkan tombol & sembunyikan hasil lama
        setButtonsEnabled(false);
        lastAttendanceDiv.style.display = 'none';
        mapContainerDiv.style.display = 'none';

        try {
            // 1. Dapatkan Lokasi (async)
            const location = await getCurrentLocation(); // Tunggu lokasi selesai

            // 2. Ambil Foto
            const photoBase64 = capturePhoto();
            if (!photoBase64) {
                // Pesan error sudah ditampilkan di capturePhoto, cukup hentikan proses
                setButtonsEnabled(true); // Aktifkan tombol lagi jika foto gagal
                return;
            }

            // 3. Kirim Data ke Backend (async)
            await sendAttendanceData(selectedEmployeeId, type, location, photoBase64);

        } catch (error) {
            // Tangani error tak terduga selama proses handleAttendance (meskipun jarang)
            console.error("Unexpected error during attendance process:", error);
            showStatus(`Proses absensi gagal total: ${error.message}`, true);
            setButtonsEnabled(true); // Aktifkan kembali tombol
        }
        // Tombol akan diaktifkan kembali di dalam 'finally' blok sendAttendanceData
    }

    // --- Event Listeners ---
    // Listener untuk tombol absen
    checkinBtn.addEventListener('click', () => handleAttendance('check_in'));
    checkoutBtn.addEventListener('click', () => handleAttendance('check_out'));

    // Listener untuk dropdown pegawai (agar tombol disable jika tidak ada yg dipilih)
    employeeSelect.addEventListener('change', () => {
        setButtonsEnabled(true); // Coba aktifkan tombol berdasarkan pilihan
    });


    // --- Inisialisasi Awal ---
    startCamera(); // Mulai akses kamera saat halaman dimuat
    setButtonsEnabled(false); // Awalnya nonaktifkan tombol sampai kamera siap & pegawai dipilih
});