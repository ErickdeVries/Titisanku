# TITISANKU — Play Store Readiness : MASTER CHECKLIST

> **Untuk agent berikutnya:** baca dokumen ini dulu. Ini sumber kebenaran tunggal status
> kesiapan rilis Play Store. Detail tiap isu ada di file lain di folder ini.
>
> Terakhir diperbarui: 2026-10-30 · Branch: `dev-titisanku`
> Play App ID: `4973586688448829102` · Package: `com.titisanku.app`
> Play Console login (browser MCP): Erick Devries / emmusic.indonesia@gmail.com

## Status Play Console saat ini (hasil cek live)
- Dashboard: **"Get ready to publish your app"** — belum selesai setup.
- **11 task App Content belum diisi** (privacy, sign-in, ads, content rating, target audience,
  data safety, government, financial, health, category/contact, store listing).
- **Internal testing: `No releases`** (belum ada build di-upload).
- **Closed testing: TERKUNCI** ("finish setting up your app" dulu).
- **Production: 0 tester opt-in**, butuh ≥12 tester / ≥14 hari closed test → baru apply.

> ⚠️ **JANGAN mengisi/mengunggah apa pun di Play Console** sampai blocker di bawah hijau.

## Blocker wajib beres sebelum upload build (URUTAN)
1. **[DONE — kode] Midtrans → Google Play Billing** (Payment Policy). Android kini memakai Play Billing;
   tinggal buat produk di Play Console + sambungkan service account → `PLAY_BILLING_SETUP.md`.
2. **[BLOCKER] Firebase config mismatch + `GOOGLE_WEB_CLIENT_ID` kosong** (login gagal). `REVIEW_AUDIT.md §4`.
3. **[BLOCKER] Akun demo reviewer** (login hanya Google). Lihat `DEMO_ACCOUNT.md`.
4. **[BLOCKER] UGC report/block/moderasi untuk chat**. `REVIEW_AUDIT.md §5`.
5. **[BLOCKER] Privacy policy URL + halaman hapus akun publik**. `DATA_SAFETY_PRIVACY.md`.

---

## ✅ SUDAH dikerjakan (oleh agent ini)
- [x] **Audit menyeluruh capability & risiko reject** → `REVIEW_AUDIT.md`.
- [x] **Lepas Emergent total**: komentar code (`integrations.py`, `server.py`, `firebase.ts`),
      hapus folder `.emergent/` (git rm + gitignore), update arsitektur `memory/PRD.md`.
      **Tidak ada lagi URL/OAuth Emergent aktif** — login via Firebase Google langsung.
- [x] **`.env.example` diselaraskan** ke project Firebase aktif `titisanku` + catatan wajib `GOOGLE_WEB_CLIENT_ID`.
      (⚠️ `.env` aktif TIDAK diubah — butuh keputusan user, lihat blocker #2.)
- [x] **Store listing copy** ID+EN (judul, short, full, kategori, kontak) → `STORE_LISTING.md`.
- [x] **Aset**: icon 512×512 + feature graphic 1024×500 → `docs/play-review/assets/` (`ASSETS.md`).
- [x] **Data safety form answers + privacy policy + halaman hapus akun** → `DATA_SAFETY_PRIVACY.md`.
- [x] **Spesifikasi akun demo** (endpoint `/auth/demo`, seed data, teks Sign-in details) → `DEMO_ACCOUNT.md`.
- [x] Dokumen ini (handoff).
- [x] **Integrasi Google Play Billing (Android)** — `frontend/src/billing.ts` (expo-iap) + verifikasi
      server `POST /payments/play/verify` (Play Developer API, acknowledge otomatis). Midtrans hanya
      dipakai di web (bukan produk Play). Panduan setup produk & service account: `PLAY_BILLING_SETUP.md`.
      Uji unit: `backend/tests/test_play_billing.py`.

## ⬜ BELUM — butuh keputusan user / kerja lanjutan
### A. Keputusan user dulu
- [ ] **Buat produk langganan di Play Console**: `titisanku_pro_yearly` & `titisanku_family_yearly`
      (base plan tahunan) lalu **grant akses service account** ke akun Play (lihat `PLAY_BILLING_SETUP.md`).
- [ ] **Pilih project Firebase final:** `titisanku` (env aktif) vs `kulproy-app` (google-services.json).
      Lalu sinkronkan `.env` + `google-services.json` + backend service account + isi `GOOGLE_WEB_CLIENT_ID`.
- [ ] **Buat akun demo**: jalankan implementasi `DEMO_ACCOUNT.md` (endpoint + tombol + seed).
- [ ] **Hosting** privacy policy + halaman hapus akun di `https://titisanku.helipod.app/*`.
- [ ] **Target audience**: 13+ (disarankan) agar tidak perlu Families Policy.

### B. Kerja kode
- [x] Integrasi Play Billing (frontend `src/billing.ts` + verifikasi server `/payments/play/verify`).
- [ ] Endpoint UGC: `POST /chat/report`, `POST /users/{id}/block` + UI + halaman kebijakan moderasi.
- [ ] Hapus `SCHEDULE_EXACT_ALARM` & `RECEIVE_BOOT_COMPLETED` bila tak esensial (`REVIEW_AUDIT.md §9`).
- [ ] Implement `POST /auth/demo` + tombol demo (`DEMO_ACCOUNT.md`).
- [ ] Perbaiki Firebase (setelah keputusan A) agar Google Sign-In jalan di build Android.
- [ ] **Buat `frontend/eas.json`** (BELUM ADA) — konfigurasi profil build `production` (AAB, `appVersionSource`,
      `versionCode`) untuk `eas build -p android --profile production`. Tanpa ini build AAB tidak jalan.
- [ ] Build AAB via EAS, uji login+semua fitur di internal testing.

### C. Isi Play Console (nanti, setelah build ok)
- [ ] Upload AAB ke **Internal testing** → uji di device.
- [ ] Isi 11 task App Content (pakai `DATA_SAFETY_PRIVACY.md` + `REVIEW_AUDIT.md`).
- [ ] Isi Store listing (copy `STORE_LISTING.md`, aset `assets/`, screenshot device).
- [ ] Buka **Closed testing** → undang ≥12 tester → jalankan **14 hari**.
- [ ] Apply production access.

---

## Catatan teknis penting (jangan diulang kesalahannya)
- **Auth:** backend `/auth/session` memverifikasi **Firebase ID token** → terbit `session_token`
  (7 hari). Tidak ada password di DB. Jangan kembali ke OAuth Emergent.
- **Backend URL:** `https://titisanku.helipod.app` (`EXPO_PUBLIC_BACKEND_URL`).
- **Pembayaran:** Android → Google Play Billing (`POST /payments/play/verify`, produk `titisanku_pro_yearly`/`titisanku_family_yearly`). Web → Midtrans (`POST /payments/snap`). Harga acuan `PLAN_PRICES = {pro:149000, family:199000}`.
  Fitur premium: kuota orang/editor (`PLAN_LIMITS`) + tema premium.
- **Premium themes** gating di frontend (`themes.tsx`) & superadmin (`emmusic.indonesia@gmail.com`).
- **Hapus akun** in-app sudah ada (`DELETE /account`, Settings).
- **Chat** = UGC tunggal di app; tidak ada report/block saat ini.
- **Plant expiry** dihitung lazy ("no cron needed") — tidak butuh cron Emergent (sudah dihapus).
- `.playwright-mcp/` di-gitignore (artefak screenshot). Folder `.emergent/` dilarang kembali.

## Peta file dokumen ini
```
docs/play-review/
├── PLAYLIST_CHECKLIST.md   ← (file ini) master status & handoff
├── REVIEW_AUDIT.md         ← inventaris capability + risiko reject (Midtrans, UGC, login, Firebase)
├── DEMO_ACCOUNT.md         ← spesifikasi akun demo reviewer
├── STORE_LISTING.md        ← copy store listing ID+EN + kategori/kontak
├── ASSETS.md               ← spesifikasi & status aset store listing
├── DATA_SAFETY_PRIVACY.md  ← jawaban Data safety + privacy policy + halaman hapus akun
└── assets/
    ├── icon-512.png
    └── feature-graphic-1024x500.png
```

## Riwayat perubahan dokumen
- 2026-10-30: audit awal, pelepasan Emergent, store listing, aset icon+feature graphic,
  data safety & privacy draft, spec akun demo, master checklist ini.
