# Data Safety & Privacy Policy — Titisanku

> Bagian A = jawaban siap-isi untuk **Play Console → Data safety**.
> Bagian B = draft **privacy policy** publik.
> Bagian C = **halaman hapus akun** publik (wajib Play).

---

## A. Data Safety (jawaban form)

Ringkasan koleksi data berdasarkan kode (`server.py`: users, people, chat, notes, files, push):

| Kategori Play | Dikumpulkan? | Dibagikan? | Tujuan | Catatan |
|---------------|--------------|------------|--------|---------|
| **Personal info → Name** | Ya | Tidak | Fungsi app (profil & anggota keluarga) | nama user + nama orang di silsilah |
| **Personal info → Email address** | Ya | Tidak (kecuali Resend untuk kirim email undangan) | Fungsi app, akun | email login + undangan |
| **Personal info → Other (tanggal lahir anggota)** | Ya | Tidak | Fungsi app | ulang tahun & pengingat |
| **Photos and videos → Photos** | Ya | Tidak | Fungsi app | foto profil/galeri diunggah ke Firebase Storage |
| **Messages → In-app messages** | Ya | Tidak | Fungsi app | chat keluarga |
| **App activity → Other user-generated content** | Ya | Tidak | Fungsi app | catatan & lampiran |
| **Device/other IDs → Device or other IDs (push token)** | Ya | Tidak | Notifikasi | Expo push token |
| **App info & performance → Crash logs/Crash logs** | Tidak (kecuali diaktifkan) | — | — | tidak ada SDK analytics terlihat |
| **Location** | Tidak | — | — | tidak diminta |
| **Contacts/Phone** | Tidak | — | — | tidak ada izin kontak |
| **Financial info** | Ya (jika langganan aktif) | Prosesor (Midtrans/Play Billing) | Pembayaran | **setelah pindah ke Play Billing**, payment diproses Google (tidak "dikumpulkan" developer) |

**Jawaban kunci form:**
- Data dienkripsi saat transit? **Ya** (HTTPS).
- Pengguna dapat meminta data dihapus? **Ya** — in-app (Settings → Hapus Akun) + halaman web (Bagian C).
- Komitmen Play Families? **Tidak** (app ditargetkan 13+/umum, bukan anak).
- Latihan independen/penargetan iklan? **Tidak**.
- Data dibagikan ke pihak ketiga untuk iklan? **Tidak**.

**Sub-prosesor (sebutkan di privacy):**
- Firebase (Auth & Storage) — Google
- MongoDB (database)
- Resend (email undangan)
- Expo (push notification)
- Midtrans / Google Play Billing (pembayaran) — **setelah migrasi, pembayaran Android via Google Play**
- Hosting: `titisanku.helipod.app`

> ⚠️ Setelah pindah ke **Google Play Billing**, perbarui jawaban "Financial info" → "tidak dikumpulkan
> oleh developer; diproses oleh Google Play". Sebelum itu, Midtrans = data pembayaran dikumpulkan.

---

## B. Draft Privacy Policy (untuk hosting publik)

> Host di `https://titisanku.helipod.app/privacy` (halaman statis, HTML, bukan PDF, tanpa login,
> SSL valid). Isi tanggal "Terakhir diperbarui". Ganti kontak.

```
KEBIJAKAN PRIVASI TITISANKU
Terakhir diperbarui: [TANGGAL]

Titisanku ("kami") menghormati privasi Anda. Kebijakan ini menjelaskan bagaimana kami
mengumpulkan, menggunakan, dan melindungi data Anda saat menggunakan aplikasi Titisanku.

1. DATA YANG KAMI KUMPULKAN
   - Informasi akun: nama dan alamat email (melalui Google Sign-In / Firebase Auth).
   - Data silsilah: nama, hubungan keluarga, tanggal (termasuk tanggal lahir), catatan,
     dan foto/galeri yang Anda tambahkan.
   - Konten yang Anda buat: pesan chat keluarga, umpan balik.
   - Token perangkat untuk mengirim notifikasi push.
   - Data pembayaran: bila Anda berlangganan, pembayaran diproses oleh Google Play Billing
     (Android). Kami tidak menyimpan nomor kartu Anda.

2. CARA KAMI MENGGUNAKAN DATA
   - Menyediakan dan menjalankan fitur aplikasi (pohon keluarga, chat, pencarian, cadangan).
   - Mengirim notifikasi terkait akun, undangan, dan pengingat.
   - Meningkatkan kualitas aplikasi melalui umpan balik Anda.

3. BERBAGI DATA
   Kami tidak menjual data Anda. Kami hanya membagikan data kepada penyedia layanan yang
   diperlukan untuk menjalankan aplikasi:
   - Firebase (Google) — autentikasi & penyimpanan foto
   - Penyedia database (MongoDB)
   - Resend — pengiriman email undangan
   - Expo — notifikasi push
   - Google Play Billing — pembayaran (Android)

4. PENYIMPANAN & KEAMANAN
   Data dikirim melalui koneksi terenkripsi (HTTPS). Kami menyimpan data selama akun Anda aktif.

5. HAK ANDA
   - Mengakses dan memperbarui data melalui aplikasi.
   - Menghapus akun beserta data Anda kapan saja: melalui Pengaturan → Hapus Akun,
     atau melalui halaman [URL HAPUS AKUN].

6. DATA ANAK
   Aplikasi ini tidak ditujukan untuk anak di bawah 13 tahun.

7. PERUBAHAN
   Kami dapat memperbarui kebijakan ini. Perubahan akan ditampilkan di halaman ini.

8. KONTAK
   Email: emmusic.indonesia@gmail.com
```

---

## C. Halaman "Hapus Akun" publik (wajib Play)

> Google mewajibkan URL publik untuk permintaan hapus akun (di luar in-app), agar reviewer/user
> bisa memintanya tanpa memasang app. Host di `https://titisanku.helipod.app/delete-account`.

```
HAPUS AKUN TITISANKU

Anda dapat menghapus akun dan seluruh data Anda dari Titisanku.

Cara 1 — Dari aplikasi:
  1. Buka aplikasi Titisanku dan masuk.
  2. Buka Pengaturan → Hapus Akun → konfirmasi.

Cara 2 — Lewat web:
  Kirim email ke emmusic.indonesia@gmail.com dengan subjek "Hapus Akun Titisanku"
  dari alamat email yang terdaftar. Permintaan diproses dalam 30 hari.

Data yang dihapus: akun, profil, pohon keluarga yang Anda miliki, foto, catatan, dan pesan.
Data yang mungkin disimpan sementara: catatan transaksi pembayaran selama diwajibkan hukum.
```

---

## Checklist Data Safety / Privacy
- [ ] Host privacy policy di URL publik + tautkan di app (Settings) dan Play Console.
- [ ] Host halaman hapus akun di URL publik + tautkan di Play Console.
- [ ] Isi form Data safety sesuai tabel A.
- [ ] Setelah Play Billing: perbarui jawaban "Financial info".
- [ ] Pastikan teks in-app `privacy.tsx` sinkron dengan kebijakan hosted.
