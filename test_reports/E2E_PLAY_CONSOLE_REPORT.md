# Laporan E2E & Kesiapan Rilis Play Console — Titisanku

Tanggal: 2026-10-30
Lingkungan uji: **TERISOLASI PENUH dari produksi**
- Backend uji: `http://127.0.0.1:8002` (uvicorn, `server:app`)
- Database: **MongoDB lokal `mongodb://localhost:27017` → DB `titisanku_e2e`** (BUKAN Atlas produksi, BUKAN helipod)
- Frontend uji: Expo web `http://localhost:8082` dengan `EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:8002`
- Konfirmasi: bundle frontend uji **tidak** memuat `titisanku.helipod.app`; semua request API mengarah ke `127.0.0.1:8002`.

> Catatan: MongoDB Atlas (`titisanku.z8aslbr.mongodb.net` / DB `titisanku_atlas`), service pod helipod
> (`titisanku.helipod.app`) dan Play Console (draft) **TIDAK disentuh** oleh pengujian ini.

---

## 1. Hasil Backend (pytest)

Perintah: `python -m pytest backend/tests -q` (via `pytest.ini`: `-n 2 --dist loadscope`)
Env: `MONGO_URL=mongodb://localhost:27017`, `DB_NAME=titisanku_e2e`, `EXPO_*_URL=http://127.0.0.1:8002`

| Hasil | Jumlah |
|-------|--------|
| Lulus | **186** |
| Gagal | **0** |
| Skip | 1 (uji kuota storage; lulus terpisah dengan `STORAGE_LIMIT_FREE_MB=1` → **1 passed**) |

**Total efektif: 187/187 modul uji tercakup & lulus.**

Tes kuota storage (`TestClaimBranchQuota::test_claim_storage_over_quota_returns_402`) hanya di-skip
pada kuota default 500MB karena berkas uji ~1MB < kuota. Dijalankan ulang dengan
`STORAGE_LIMIT_FREE_MB=1` → **1 passed**. Jadi bukan cacat.

Catatan: pada run pertama muncul 3 ERROR di `test_admin_dashboard.py` akibat **data sisa** DB uji
(bentrok unique email). Setelah DB uji dibersihkan → **0 error**. Backend punya pengaman bawaan:
fixture `seeded` menolak/`skip` bila `MONGO_URL` bukan localhost (proteksi produksi).

---

## 2. Hasil E2E UI (Playwright, web)

Skrip: `frontend/e2e/run-e2e.mjs` (Playwright/Chromium headless).
Seed: `backend/tests/seed_e2e_local.py` (aman: menolak MONGO_URL non-lokal & DB produksi).

| # | Langkah | Status |
|---|---------|--------|
| A1 | App memuat & login otomatis via session token | ✅ |
| B1 | Semua request API diarahkan ke backend uji (8002), tidak ada ke helipod | ✅ |
| C1 | Layar pohon (home) tampil dengan data seed | ✅ |
| D1 | Tambah anggota baru (ibu) & tersimpan di DB | ✅ |
| E1 | Tab Chat terbuka tanpa error | ✅ |
| F1 | Settings menampilkan baris kunci (privasi/subscription/members/logout) | ✅ |
| G1 | Layar subscription menampilkan info kuota/plan | ✅ |
| H1 | Halaman privasi (kebijakan) terbuka | ✅ |
| H2 | Claim branch terbuka & form input nama cabang tampil | ✅ |
| H3 | Tab Search menampilkan input pencarian & bisa ketik | ✅ |
| H4 | Layar Members terbuka | ✅ |
| J1 | Login sebagai member (non-owner) berhasil | ✅ |
| I1 | Tidak ada JS error fatal di halaman | ✅ |

**E2E UI: 13/13 lulus, 0 gagal.**

Cakupan backend pytest juga sudah mencakup secara mendalam: privasi kartu per-field
(`test_card_privacy.py`), kuota storage berbasis byte, klaim cabang (scope descendants/children/whole
+ limit plan free), admin dashboard, datetime aware, otorisasi upgrade, dll.

Laporan log: `test_reports/e2e/latest.log`.

---

## 3. Type-check & Lint

- `npx tsc --noEmit` → **exit 0** (TypeScript bersih).
- `npx expo lint` → **11 error, 18 warning**. Semua 11 error berada di **satu file**:
  `frontend/app/(tabs)/index.tsx` (layar kanvas pohon), aturan React Compiler:
  - Baris 296–309: `tx.value = ...` / `scale.value = ...` pada **Reanimated SharedValue** di dalam
    gesture callback. Ini **false positive** — pola resmi Reanimated; bukan bug runtime.
  - Baris 327–332: baca/tulis `animRef.current` di dalam `useMemo` (mutasi ref saat render).
    Melanggar aturan React Compiler, tetapi berfungsi; tidak membuat JS error (E2E lulus).
  - **Sesuai instruksi**: file kanvas pohon keluarga sengaja **tidak diubah**. Tidak memblok build/EAS.

---

## 4. Kesiapan Rilis Play Console — Checklist

### 🔴 BLOCKER (wajib sebelum upload AAB / publish)

1. **`android.versionCode` belum diisi** (`app.json`). Google Play menolak upload tanpa versionCode
   naik monoton. Set misal `"android": { "versionCode": 1 }` (naikkan tiap rilis).
2. **Migrasi signing key**: belum ada keystore/upload key di repo. Untuk Play, gunakan
   **Play App Signing** (ekspor/enroll upload key). Tanpa ini upload AAB akan ditolak bila
   sebelumnya app di-upload dengan key lain.
3. **Kebijakan Privasi PUBLIK (URL)**: aplikasi hanya punya kebijakan in-app (`app/privacy.tsx`).
   Play Console **mewajibkan URL kebijakan privasi** yang dapat diakses publik untuk app yang
   mengumpulkan data pribadi (foto, nama, data keluarga, login Google). Sediakan halaman publik,
   mis. `https://titisanku.helipod.app/privacy`.
4. **Konfigurasi Firebase Android tidak konsisten (penting!)**:
   - Runtime `.env` → project **`titisanku`**, web app id `1:389393525285:...`
   - `frontend/google-services.json` → project **`kulproy-app`** (client `com.kulproy.app` &
     `com.titisanku.app`, app id `1:710949408785:...`)
   - Keduanya **project Firebase berbeda**. Build Android akan memakai project `kulproy-app`,
     sedangkan backend memverifikasi token dengan service account project `titisanku`.
     **Risiko**: Google Sign-In / FCM di Android gagal verifikasi di backend. Perlu disamakan:
     unduh ulang `google-services.json` dari project Firebase `titisanku` untuk package
     `com.titisanku.app` (atau konfirmasi project kanonik).

### 🟠 Penting (disarankan sebelum produksi)

5. **`eas.json` belum ada** — buat konfigurasi build Play (profil `production` → `app-bundle`).
6. **Kebijakan Data (Data safety form)** di Play Console: deklarasikan data yang dikumpulkan
   (nama, email, foto, dsb.), terenkripsi saat transit, bisa dihapus (app sudah punya
   `delete-account`).
7. **Content rating + target audience**: isi kuesioner rating & kelompok usia.
8. **Ikon & grafis store**: `icon.png` 1024×1024 (valid). Untuk listing Play perlu
   **ikon 512×512 PNG** + feature graphic 1024×500 + minimal 2 screenshot ponsel.
9. **Permission Android**: pastikan hanya permission yang dipakai (kamera, galeri, notifikasi)
   dan isi justifikasi di Play bila diminta (mis. CAMERA untuk scan QR undangan).
10. **`versionName`/`version`**: `1.0.0` wajar untuk rilis pertama; pastikan scheme/slug branded
    (saat ini `slug="frontend"`, `scheme="frontend"` — sebaiknya `titisanku` agar deep link rapi,
    tapi tidak wajib untuk Play).

### 🟢 Sudah baik

- TypeScript kompilasi bersih.
- Backend 187/187 & E2E 13/13 lulus terisolasi.
- Fitur inti (auth, pohon, tambah anggota, chat, privasi kartu, klaim cabang, kuota, subscription,
  hapus akun) berfungsi.
- Firebase Storage & Google Sign-In terkonfigurasi di sisi web/env.

---

## 5. Rekomendasi urutan langkah agar siap Play Console

1. Tetapkan **project Firebase kanonik** (sebaiknya `titisanku`) → unduh ulang
   `google-services.json` untuk `com.titisanku.app`, samakan dengan `.env`.
2. Tambah `android.versionCode` di `app.json`, buat `eas.json`, jalankan
   `eas build -p android --profile production` (AAB).
3. Enroll **Play App Signing**; simpan upload key dengan aman.
4. Publikasikan halaman **kebijakan privasi** di URL publik → isi di Play Console.
5. Lengkapi **Data safety**, content rating, target audience, aset store (ikon 512, feature graphic,
   screenshot).
6. Upload AAB ke jalur **Internal testing** → uji di perangkat → promote ke Closed/Production.

---

## 6. Berkas baru yang ditambahkan (tidak mengubah sumber aplikasi)

- `backend/tests/seed_e2e_local.py` — seed DB uji lokal (pengaman anti-produksi).
- `frontend/e2e/run-e2e.mjs` — skrip E2E Playwright.
- `test_reports/e2e/` & `test_reports/pytest/pytest_results_e2e.xml` — artefak laporan.

Tidak ada perubahan pada file kanvas pohon, auth, firebase, atau konfigurasi produksi.
