# SAVEPOINT — catatan jeda kerja

Tanggal: 2026-11 (savepoint ketiga, setelah migrasi SSD)
Branch: `main` (sinkron dengan `origin/main`)
Commit: `ef3d48e` — _feat(play-review): Sign in with Apple, Apple IAP, moderasi UGC, ZIP backup_
Commit sebelumnya: `b4918e2` — _docs(play-review): tandai UGC report/block/moderasi selesai_

Status: **aman untuk ditinggal.** Working tree bersih, semua pekerjaan sudah
di-commit dan di-push. `tsc --noEmit` exit 0, `py_compile` exit 0.

> **PENTING setelah migrasi SSD:** `frontend/node_modules` hilang. Jalankan
> `npm ci` di folder `frontend` sebelum `tsc` / `expo start`. npm tidak ada di
> PATH — pakai `C:\nvm4w\nodejs\npm.cmd`.
> Tes backend yang memanggil HTTP butuh uvicorn di port 8001; tanpa itu hasilnya
> `ConnectionRefused` (bukan bug kode). `test_moderation.py` tidak butuh uvicorn,
> hanya MongoDB.

> Savepoint lama (branch `dev-titisanku`) sudah tidak relevan — commit `f2f7723`
> dan tag `savepoint/2026-10-29-kuota-storage-otorisasi-upgrade` tidak ada di
> riwayat `main`. Catatan di bawah dipertahankan sebagai arsip.

> Savepoint sebelumnya masih ada: tag `savepoint/2026-10-29-navigasi-privasi`
> (commit `d75ff66`). Riwayat singkat: `d75ff66` → `f087e72` (docs) →
> `c7f53b1` (kuota byte + tes claim-branch) → `f2f7723` (savepoint ini).

---

## Cara melanjutkan (resume)

```powershell
# 1. pastikan working tree bersih
git status            # harus "nothing to commit" selain file yang di-ignore

# 2. pastikan di titik savepoint
git log --oneline -1  # harus muncul ef3d48e

# 3. kalau lupa sudah sampai mana, lihat catatan tag
git show savepoint/2026-10-29-kuota-storage-otorisasi-upgrade
```

Kalau ada pekerjaan baru yang ternyata ingin dibuang dan kembali ke titik ini:

```powershell
git reset --hard ef3d48e
```

Jalankan app (setelah `npm ci` karena node_modules hilang saat migrasi SSD):

```powershell
cd frontend
npm ci                                            # sekali saja
& C:\nvm4w\nodejs\npx.cmd tsc --noEmit            # cek tipe (harus exit 0)
npm start                                         # expo start
```

Backend: `backend/server.py` (FastAPI). Cek `.env` sebelum start.

Tes backend (pytest, pakai `pytest-xdist`):

```powershell
cd backend
pytest -q                    # atau: pytest -q -n auto --dist loadscope
```

---

## Yang selesai di savepoint ini (12 file)

### 1. Kuota penyimpanan berbasis byte (lanjutan `c7f53b1`)
- `frontend/src/utils/format.ts` (baru): `formatBytes()` — aturannya
  **sama persis** dengan `fmt_size` di backend (<1 GB → MB, ≥1 GB → 1 desimal,
  koma sebagai pemisah desimal). Kalau keduanya berbeda, pengguna bisa melihat
  "500 MB" padahal server sudah menolak karena kuota habis.
- `frontend/src/api.ts`: tipe `storage_used`, `storage_limit` pada
  `plan_limits`.
- `frontend/app/subscription.tsx`: menampilkan pemakaian/kuota storage memakai
  `formatBytes`.

### 2. Fix crash datetime aware vs naive (`backend/server.py`)
- `plan_limits()`: `expires_at` dinormalkan lewat `_aware()` sebelum
  dibandingkan dengan `now_utc()`.
  **Kenapa penting:** motor mengembalikan datetime **naive** (UTC); membandingkan
  naive dengan aware melempar `TypeError` → `GET /trees` crash **500** begitu ada
  pohon berbayar — tepat pada pelanggan yang sudah membayar.

### 3. `POST /trees` konsisten dengan `GET /trees`
- Respons `create_tree` kini menyertakan `plan_limits` hasil `plan_limits(...)`,
  `limit` dari `limits["people"]`, plus `storage_used` / `storage_limit`.
  Tujuannya: klien bisa memakai payload ini langsung tanpa fetch ulang.

### 4. Otorisasi di periksa SEBELUM validasi (`upgrade_tree`)
- `body: Optional[UpgradeInput] = None` + cek `is_superadmin()` lebih dulu.
  Sebelumnya body wajib membuat FastAPI membalas **422** sebelum handler jalan,
  sehingga non-member menerima 422 (bocor info validasi) alih-alih **403**.

### 5. Perbaikan tes (xdist)
- `backend/tests/conftest.py`: penyesuaian fixture bersama.
- `test_chat_rooms.py`, `test_multitenant.py`: fixture scope diubah
  `module` → `class`, dan seluruh alur disatukan ke satu kelas supaya
  `--dist loadscope` menjalankan satu alur di satu worker. Dengan scope `module`
  dulu, fixture dieksekusi ulang di worker lain sehingga id room/group yang
  disimpan di state hilang.
- `test_plans.py`: penulisan ulang besar (upgrade diuji lewat webhook
  tersimulasi, bukan jalur gratis).
- `test_join_flow.py`: asersi `path`/`url` hasil upload disesuaikan.
- `test_payments_midtrans.py`, `test_push_notifications_inbox.py`: penyesuaian
  kecil.
- `test_keturunanku_api.py`: **dihapus** (sudah tercakup tes lain).

---

## Belum dikerjakan / catatan untuk nanti

### Status Play Store / App Store review (per savepoint ini)

Sudah selesai di kode (belum diuji runtime):
- **Sign in with Apple** — wajib App Store Guideline 4.8.
- **Apple IAP + restore pembelian** — wajib review App Store.
- **Moderasi UGC** (blokir, lapor, antrean admin) — blocker #4 di
  `docs/play-review/REVIEW_AUDIT.md`, sudah ditandai selesai.
- Ekspor/impor ZIP (data + foto), guard superadmin, privasi diperluas.

Sudah terverifikasi runtime:
- **`backend/tests/test_moderation.py` — 7 passed** (dijalankan dengan MongoDB
  via Docker). Ini bukti runtime untuk blocker UGC, bukan lagi "skip".
  Cara ulang:
  `docker start titisanku-mongo-test` (atau `docker run -d --name
  titisanku-mongo-test -p 27017:27017 mongo:7`), lalu
  `python -m pytest tests/test_moderation.py -q`. Setelah selesai:
  `docker stop titisanku-mongo-test`.

Belum terverifikasi (harus ditutup sebelum submit):
- Sign in with Apple & Apple IAP belum diuji di device/simulator iOS.
- `verify_apple_jws` belum diuji dengan JWS asli dari Apple.
- Env `APPLE_*` (key ID, issuer ID, bundle ID, root cert) belum dikonfirmasi
  terpasang di server deploy.

Sisa pekerjaan Play Console:
- Isi privacy policy URL, Data Safety form, content rating.
- Siapkan halaman Kebijakan Konten & Moderasi publik untuk reviewer.
- Tulis prosedur moderasi (SLA tinjauan laporan) di jawaban reviewer.
- Opsional: auto-filter kata kasar & rate-limit kirim pesan.

### Catatan lama (arsip)

- **Screenshot & snapshot browser jangan di-commit** (sudah masuk `.gitignore`):
  `mobile-*.png`, `preview-mobile-login.png`, `admin-superadmin-verified.png`,
  `helipod-home.yml`, `vars.yml`.
- `.env` (root) ada dan di-ignore — **jangan pernah di-commit**.
- Perlu dicek manual setelah resume: alur privasi kartu sebagai anggota
  non-owner, navigasi back dari deep link, dan tampilan kuota storage di layar
  subscription pada akun yang sudah mendekati batas.
- Tes backend belum dijalankan penuh di savepoint ini (butuh MongoDB +
  backend hidup). Yang sudah diverifikasi: `tsc --noEmit` dan `py_compile`.

---

## Kalau mau menghapus savepoint (setelah yakin)

```powershell
git tag -d savepoint/2026-10-29-kuota-storage-otorisasi-upgrade
# commit tetap ada di branch; tidak ada yang hilang.
```
