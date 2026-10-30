# Review Audit — Titisanku (Google Play)

> Tujuan: memperkecil potensi **reject** saat review Play Store dengan memetakan SEMUA
> capability aplikasi + kebijakan Play yang berpotensi dilanggar.
>
> Terakhir diperbarui: 2026-10-30 · App ID Play: `4973586688448829102` · Package: `com.titisanku.app`
> Branch: `dev-titisanku`

## Ringkasan cepat (Severity)

| # | Isu | Severity | Status | Blocker? |
|---|-----|----------|--------|----------|
| 1 | **Pembayaran digital via Midtrans** (bukan Google Play Billing) | 🟢 CRITICAL | **Kode beres** (Play Billing di Android); sisa setup Play Console | **YA** (sampai produk Play dibuat) |
| 2 | **Login hanya Google Sign-In** — reviewer tak bisa login tanpa akun demo | 🔴 CRITICAL | Perlu solusi | **YA** |
| 3 | **`EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID` kosong** + Firebase project mismatch | 🔴 CRITICAL | Belum diperbaiki | **YA** (login gagal) |
| 4 | **UGC chat/grup tanpa report/block/moderasi** | 🟠 HIGH | Belum ada fitur | **YA** (UGC policy) |
| 5 | Privacy policy URL belum ada | 🟠 HIGH | Perlu hosting | YA |
| 6 | Data safety form belum diisi | 🟠 HIGH | Perlu isi | YA |
| 7 | Content rating belum diisi | 🟠 HIGH | Perlu isi | YA |
| 8 | Target audience & konten anak belum ditetapkan | 🟡 MED | Perlu keputusan | Tidak |
| 9 | Izin `SCHEDULE_EXACT_ALARM` berlebihan (risiko policy) | 🟡 MED | Perlu review | Tidak |
| 10 | Akun baru → wajib closed test 12 tester/14 hari | 🟡 MED | Proses | Tidak (prosedural) |

---

## 1. Inventaris Capability Aplikasi

Sumber: `backend/server.py` (70 endpoint), `frontend/app/**`, `app.json`, `memory/PRD.md`.

### Fitur inti
- **Silsilah keluarga (family tree)**: kanvas interaktif zoom/pan, tambah orang 4 arah, relasi
  (parent/child/spouse/adopted/divorce), privacy per-kartu (`PUT /people/{id}/privacy`).
- **Multi-pohon (multi-tenant)**: buat pohon, klaim cabang (`claim-branch`), join request,
  peran anggota (admin/editor/viewer), invite via email (Resend) & invite-link.
- **Profil orang**: form multi-tab, foto (Firebase Storage), catatan (`notes`), file lampiran.
- **Pencarian** global & dalam pohon.
- **Chat & grup keluarga** (`/chat/*`): pesan teks, mute, typing, hapus pesan, leave.
- **Notifikasi**: in-app (`/notifications`) + push (`/register-push`, Expo Push).
- **Backup/restore JSON** (`/backup`, `/restore`).
- **Tema** (beberapa tema, sebagian premium) — lihat catatan gating.
- **Multi-bahasa** ID/EN.
- **Feedback** (`/feedback`) + **Admin panel** (`/admin/*`, superadmin).
- **Hapus akun** in-app (`DELETE /account`, tombol di Settings) ✅.

### Data & integrasi
- MongoDB (data pengguna, pohon, chat).
- **Firebase Auth** (Google Sign-In) + **Firebase Storage**.
- **Resend** (email undangan).
- **Expo Push** (notifikasi).
- **Google Play Billing** (langganan Android — `titisanku_pro_yearly`/`titisanku_family_yearly`).
- **Midtrans Snap** (langganan **web** saja) — lihat §2.

### Izin Android (`app.json`)
```
READ_MEDIA_IMAGES, RECEIVE_BOOT_COMPLETED, SCHEDULE_EXACT_ALARM, CAMERA
```
Plugin: `expo-camera` (scan QR undangan), `expo-image-picker` (foto), `expo-notifications`,
`expo-audio`, `expo-location` TIDAK ada (✅ tidak minta lokasi).

---

## 2. 🔴 CRITICAL — Pembayaran digital pakai Midtrans (Payment Policy)

**Temuan:** Langganan **PRO (Rp149.000)** dan **FAMILY (Rp199.000)** dijual sebagai produk
**digital dalam aplikasi** melalui **Midtrans Snap** (`POST /payments/snap`, redirect ke
`app.midtrans.com`, webhook `POST /payments/notification`). Fitur premium (kuota orang/editor,
tema premium) terbuka setelah bayar.

**Kenapa masalah:** Google Play **Payments Policy** mewajibkan pembelian **barang/jasa digital
yang dikonsumsi di dalam aplikasi** memakai **Google Play Billing**. Midtrans (payment gateway
pihak ketiga) untuk konten digital = **pelanggaran → reject / removal**.

**Opsi perbaikan (pilih salah satu):**
1. **Rekomendasi — pakai Google Play Billing** untuk PRO/FAMILY. Implementasi
   `react-native-iap` / `expo-in-app-purchases` (atau RevenueCat yang membungkus Play Billing),
   sinkron ke backend lewat **Play Developer Notifications (RTDN)** / server-side verification.
   Backend Midtrans dipertahankan hanya untuk platform lain (web) — **jangan dipakai di build Android**.
2. **Alternatif (lebih berat & tetap berisiko):** jika langganan dianggap "akses ke layanan
   keluarga lintas-platform"… **tidak disarankan**; Play tetap menganggap produk digital
   yang dibuka di app harus Play Billing.
3. **Sementara untuk closed test:** **sembunyikan** layar berlangganan/pembayaran di build
   yang direview (feature flag `BILLING=play` → tombol pakai Play Billing; fallback semua
   fitur gratis saat closed test) SEHINGGA tidak melanggar saat review. Catat di jawaban
   reviewer bila diminta.

**Aksi konkret (checklist teknis):**
- [x] Tentukan billing: **Play Billing** (dipilih).
- [x] Integrasi library Play Billing di frontend (`expo-iap`, `frontend/src/billing.ts`).
- [x] Endpoint backend verifikasi `purchaseToken` + `acknowledge` (`POST /payments/play/verify`, Play Developer API).
- [x] Jalur Midtrans hanya untuk web (`subscription.tsx`: `billingSupported ? Play : Midtrans`).
- [x] Update teks UI: "Langganan diproses oleh Google Play…" pada build Android.
- [ ] Buat produk `titisanku_pro_yearly`/`titisanku_family_yearly` di Play Console + grant service account (`PLAY_BILLING_SETUP.md`).
- [ ] Uji sandbox purchase di internal testing.

> ⚠️ Kode selesai. Yang tersisa hanya konfigurasi Play Console (produk + service account) lalu uji di internal testing.

> ⚠️ Ini **blocker #1**. Jangan upload build ke track mana pun sebelum ini beres.

---

## 3. 🔴 CRITICAL — Login hanya Google, reviewer tak bisa masuk

**Temuan:** Satu-satunya cara login = **Google Sign-In via Firebase** (`login.tsx` →
`signInWithGoogle`). Tidak ada email/password. Backend `/auth/session` menukar **Firebase ID
token** → `session_token` aplikasi.

**Masalah:**
- Reviewer Play **tidak boleh** memberi akun Google pribadi; juga tidak bisa "membuat akun baru"
  bila syaratnya Google account + verifikasi.
- Sesuai kebijakan "Sign in details / App access", bila app butuh login, developer **wajib**
  memberi **kredensial uji** atau membuat bagian app bisa diakses tanpa login.

**Solusi (lihat `DEMO_ACCOUNT.md` untuk detail implementasi):**
- Tambah **"Masuk dengan akun demo"** (email/password khusus review) ATAU **magic-login** untuk
  email demo yang tercatat di `SUPERADMIN_EMAILS`/`DEMO_EMAILS`, seed data contoh.
- Isi **Sign in details** di Play Console: Yes → beri email/password demo + langkah yang jelas.
- Pastikan akun demo punya **pohon contoh terisi** agar reviewer langsung melihat nilai app.

> ⚠️ **Blocker #2** + berkaitan dengan #4 (login gagal karena webClientId kosong).

---

## 4. 🔴 CRITICAL — Firebase config mismatch (login akan gagal di build)

| Sumber | Project ID | Project Number | App ID |
|--------|-----------|----------------|--------|
| `frontend/.env` (aktif) | `titisanku` | `389393525285` | `1:389393525285:web:...` |
| `frontend/google-services.json` | `kulproy-app` | `710949408785` | android `...:b82cd1a6` (titisanku.app) |
| `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID` | **KOSONG** | — | — |

**Konsekuensi:** Google Sign-In native butuh `webClientId` **dan** `google-services.json` yang
merujuk **project yang SAMA** dengan `EXPO_PUBLIC_FIREBASE_*`. Saat ini tidak sinkron →
**login gagal total di build Android**, bahkan sebelum soal demo account.

**Aksi:**
- [ ] Putuskan **satu** project Firebase final (disarankan `kulproy-app` karena
      `google-services.json` sudah memuat `com.titisanku.app`, ATAU buat `google-services.json`
      baru untuk project `titisanku`).
- [ ] Samakan `EXPO_PUBLIC_FIREBASE_PROJECT_ID/AUTH_DOMAIN/STORAGE_BUCKET/APP_ID` dengan project terpilih.
- [ ] Isi `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID` (Firebase Console → Authentication → Google → Web client ID).
- [ ] Backend `.env` `FIREBASE_PROJECT_ID` + service account harus **project yang sama**.
- [ ] Build ulang & uji login di internal testing sebelum review.

> ⚠️ **Blocker #3.** `.env` aktif TIDAK diubah oleh agent (berisi kredensial riil) — butuh keputusan user.

---

## 5. 🟠 — UGC: Chat & Grup tanpa Report/Block/Moderasi

**Temuan:** Ada chat 1:1 & grup keluarga (teks), tapi **tidak ada** endpoint/UI untuk
**melaporkan konten**, **memblokir pengguna**, atau **moderasi**. Semua endpoint `/chat/*`
tidak punya `report|block|abuse`.

**Kebijakan Play (UGC):** App yang menampilkan/mentransfer konten buatan pengguna **wajib**:
1. Mekanisme **melaporkan** konten/pengguna.
2. Mekanisme **memblokir** pengguna.
3. Syarat & kebijakan moderasi (termasuk tindakan terhadap pelanggaran).
4. Untuk app yang boleh diakses anak: mitigasi tambahan.

**Aksi:**
- [ ] Tambah `POST /chat/report` (laporan pesan/pengguna) + UI "Laporkan".
- [ ] Tambah `POST /users/{id}/block` + UI "Blokir" & sembunyikan pesan pengguna terblokir.
- [ ] Tambah halaman **Kebijakan Konten & Moderasi** (bisa di `privacy.tsx` atau EULA).
- [ ] Pertimbangkan auto-filter kata kasar & rate-limit.
- [ ] Catat prosedur moderasi di jawaban reviewer.

> ⚠️ **Blocker #4** jika chat tetap ada di build yang direview. (Alternatif sementara: sembunyikan chat
> pada build closed test, tapi ini mengurangi fitur unggulan — lebih baik implementasi report/block.)

---

## 6. 🟠 — Privacy Policy belum ada URL

- Halaman in-app `privacy.tsx` **bukan** URL publik (Play butuh **URL** publik, SSL, tanpa login).
- **Aksi:** hosting halaman privacy di domain publik (mis. `https://titisanku.helipod.app/privacy`
  atau GitHub Pages/Notion publik), isi lengkap (lihat `DATA_SAFETY_PRIVACY.md`), lalu masukkan
  URL ke Play Console **dan** tautan di dalam app (Settings → Kebijakan Privasi).

---

## 7. 🟠 — Data safety form

- Wajib diisi: data yang dikumpulkan (nama, email, foto, kontak?, riwayat chat), tujuan,
  enkripsi, opsi hapus. **Belum diisi.**
- **Aksi:** ikuti `DATA_SAFETY_PRIVACY.md` (jawaban siap pakai).

---

## 8. 🟠 — Content Rating & Target Audience

- Fitur chat = interaksi antarpengguna → **Content Rating** harus dideklarasikan (kemungkinan
  minimal "Everyone 13+" / rating sesuai kuesioner). **Belum diisi.**
- Tanpa konten dewasa/judi/alkohol. **Aksi:** isi kuesioner IARC dengan benar
  (akui ada UGC & chat), tetapkan target usia (disarankan **13+**, bukan anak-anak, agar tidak
  perlu compliance Families Policy ekstra).

---

## 9. 🟡 — Izin `SCHEDULE_EXACT_ALARM` & `RECEIVE_BOOT_COMPLETED`

- Dipakai untuk reminder ulang tahun/notifikasi terjadwal. Google membatasi `SCHEDULE_EXACT_ALARM`
  (hanya untuk app yang benar-benar butuh presisi). Untuk reminder ulang tahun, **`USE_EXACT_ALARM`
  atau alarm presisi tidak diperlukan** → gunakan `expo-notifications` scheduled (inexact) / WorkManager.
- **Aksi:** hapus `SCHEDULE_EXACT_ALARM` & `RECEIVE_BOOT_COMPLETED` bila tidak esensial
  (kurangi risiko policy + review). Uji bahwa reminder tetap jalan.

---

## 10. 🟡 — Akun developer baru: wajib Closed Testing

- Dashboard: **"To start a closed test, finish setting up your app"**; Production minta
  **≥12 tester opt-in selama ≥14 hari** sebelum apply production.
- **Aksi (proses, bukan kode):** selesaikan semua App Content → buka Closed testing → undang ≥12
  tester → jalankan 14 hari → baru apply production.

---

## Fitur lain yang WAJIB dicatat di jawaban reviewer
- **Hapus akun**: tersedia in-app (Settings → Hapus Akun) ✅ + wajib sediakan **URL permintaan hapus akun**
  (googPlay minta selain in-app juga web) → host halaman kecil "Hapus Akun".
- **Foto & kamera**: hanya untuk foto profil/galeri & scan QR undangan. Tidak ada tracking.
- **Tidak ada**: lokasi, kontak (phone), iklan, anak-anak, judi, alkohol, kesehatan.
- **Chat**: sebutkan report/block setelah diimplementasi.

## Referensi kebijakan
- Payments: https://support.google.com/googleplay/android-developer/answer/9858738
- UGC: https://support.google.com/googleplay/android-developer/answer/9876937
- Data safety: https://support.google.com/googleplay/android-developer/answer/10787469
- App access/Sign-in: https://support.google.com/googleplay/android-developer/answer/9859455
- Account deletion: https://support.google.com/googleplay/android-developer/answer/13327111
