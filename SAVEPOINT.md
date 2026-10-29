# SAVEPOINT — catatan jeda kerja

Tanggal: 2026-10-29
Branch: `dev-titisanku`
Commit: `d75ff66` — _savepoint: perbaikan navigasi back, privasi kartu, dan stabilitas layar_
Tag git: `savepoint/2026-10-29-navigasi-privasi`

Status: **aman untuk ditinggal.** Semua pekerjaan sudah di-commit, tag dibuat,
`tsc --noEmit` bersih (exit 0). Tidak ada perubahan yang menggantung.

---

## Cara melanjutkan (resume)

```powershell
# 1. pastikan working tree bersih
git status            # harus "nothing to commit" selain file yang di-ignore

# 2. pastikan di titik savepoint
git log --oneline -1  # harus muncul d75ff66

# 3. kalau lupa sudah sampai mana, lihat catatan tag
git show savepoint/2026-10-29-navigasi-privasi
```

Kalau ada pekerjaan baru yang ternyata ingin dibuang dan kembali ke titik ini:

```powershell
git reset --hard savepoint/2026-10-29-navigasi-privasi
```

Jalankan app:

```powershell
cd frontend
node ./node_modules/typescript/bin/tsc --noEmit   # cek tipe (harus exit 0)
npm start                                         # expo start
```

Backend: `backend/server.py` (FastAPI). Cek `.env` sebelum start.

---

## Yang selesai di savepoint ini (27 file)

### 1. Navigasi "back" yang aman
- Baru: `frontend/src/hooks/useGoBack.ts`
  → fallback ke route tertentu saat history kosong (deep link / refresh),
    supaya tidak muncul error "GO_BACK was not handled".
- Dipakai di hampir semua layar: add-first, add-relative, chat/new,
  chat/manage, chat/info, chat-sound, admin, subscription, trees, join,
  members, notifications, payment-history, privacy, themes, feedback,
  claim-branch.

### 2. Privasi kartu (per-field)
- `backend/server.py`: field `privacy` pada `PersonData`; penyaringan field
  saat dibaca. **Pemilik record (created_by), admin tree, dan superadmin
  selalu melihat semua.** Anggota lain hanya melihat field yang tidak
  disembunyikan.
- `frontend/app/person/[id].tsx`: UI toggle privasi.
- Form tambah orang ikut menyesuaikan.

### 3. Stabilitas Explorer / Tree
- `frontend/app/explorer/[id].tsx`: komponen `Section` dipindah ke module
  scope (sebelumnya dibuat di dalam render → remount & state hilang tiap
  render). Viewer foto: reset zoom + tombol close diperbaiki.
- `frontend/src/tree-context.tsx`: perbaikan fetch ganda saat mount,
  `pendingFocusId` hanya berlaku sekali.
- `frontend/app/(tabs)/index.tsx`: fokus dari chip dipisah (`chipFocusId`),
  tidak lagi berebut dengan `focusId`.

### 4. Chat & lain-lain
- `frontend/app/chat/manage/[roomId].tsx`: perbaikan alur kelola room.
- `frontend/src/api.ts`: tambah `muted?: boolean` di `ChatRoom`.
- `frontend/src/i18n.tsx`: hapus key `send` yang duplikat/tidak dipakai.

---

## Belum dikerjakan / catatan untuk nanti

- **Screenshot & snapshot browser jangan di-commit** (sudah masuk `.gitignore`):
  `mobile-*.png`, `preview-mobile-login.png`, `admin-superadmin-verified.png`,
  `helipod-home.yml`, `vars.yml` (dua file terakhir isinya snapshot halaman,
  bukan config).
- Belum ada test otomatis. Verifikasi saat ini hanya `tsc --noEmit`.
- `.env` (root) ada dan di-ignore — **jangan pernah di-commit**.
- Perlu dicek manual di HP/web setelah resume: alur privasi kartu (login
  sebagai anggota non-owner) dan navigasi back dari deep link.

---

## Kalau mau menghapus savepoint (setelah yakin)

```powershell
git tag -d savepoint/2026-10-29-navigasi-privasi
# commit tetap ada di branch; tidak ada yang hilang.
```
