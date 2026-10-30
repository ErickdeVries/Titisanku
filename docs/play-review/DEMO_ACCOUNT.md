# Akun Demo & Login Username/Password — SUDAH DIIMPLEMENTASIKAN ✅

> Status: **implemented & teruji** (2026-10-30). Login username/password + akun demo
> berfungsi di backend (`/auth/register`, `/auth/login`, `/auth/demo`). Data contoh
> "Keluarga Contoh" (8 orang, 11 relasi) otomatis dibuat sekali saat demo pertama dipanggil.

## Kredensial untuk Play Console → App Content → "Sign in details"

Isi ini di Play Console agar reviewer bisa masuk:

```
Isi instruksi login:
1. Buka aplikasi. Di halaman login, ketuk "Masuk sebagai akun demo".
   (atau pilih "Masuk" dengan username & password berikut)
2. Username: demo
3. Password: Titisanku#Demo2026
4. Anda akan masuk ke pohon "Keluarga Contoh" berisi data contoh
   (8 orang, 11 relasi, 4 generasi).
```

> `Titisanku#Demo2026` berasal dari `DEMO_PASSWORD` di `backend/.env`.
> Ganti nilainya kapan saja di server; akun demo dibuat saat pertama kali `/auth/demo` dipanggil.

## Ringkasan implementasi

### Backend (`backend/server.py`)
- `import bcrypt`; password di-hash **bcrypt (12 rounds)**, tidak pernah disimpan plaintext.
- `POST /auth/register` — `{username, password, name}`. Username 3–32 (huruf/angka/._),
  password ≥8. User pertama jadi `admin`, sisanya `viewer`. Email internal
  `<username>@user.titisanku.app` (identitas unik, bukan email nyata).
- `POST /auth/login` — `{username, password}` → verifikasi bcrypt → `session_token` (7 hari).
- `POST /auth/demo` — hanya aktif bila `DEMO_LOGIN_ENABLED=true`. Idempoten: membuat user
  `demo` + seed pohon "Keluarga Contoh" sekali, lalu login.
- `seed_demo_tree()` — 4 generasi: Sutrisno & Sri (kakek-nenek) → Budi + Ratna & Agus (paman)
  → Dewi & Rian → Aisyah. Memakai schema relasi asli (`person_id`, `related_person_id`,
  `relation_type`, `deleted_at`). Sudah diverifikasi `/tree` mengembalikan 8 people + 11 relations.

### Frontend
- `src/api.ts`: `loginWithPassword`, `registerWithPassword`, `demoLogin`.
- `src/auth.tsx`: `loginWithPassword`, `register`, `loginDemo` di context; restorasi sesi
  tidak lagi wajib Firebase (token lokal tetap dipulihkan bila Firebase tak aktif).
- `app/login.tsx`: form Username + Password, toggle **Masuk/Daftar**, tombol
  **"Masuk sebagai akun demo"** (muncul bila `EXPO_PUBLIC_ENABLE_DEMO_LOGIN=true`),
  plus tombol Google sebagai alternatif.
- `src/i18n.tsx`: key `login_username/password/name/submit/register_submit/to_register/to_login/demo/or` (ID+EN).

### Env
- `backend/.env`: `DEMO_LOGIN_ENABLED=true`, `DEMO_PASSWORD=Titisanku#Demo2026`.
- `frontend/.env`: `EXPO_PUBLIC_ENABLE_DEMO_LOGIN=true`.
- `.env.example` (backend & frontend) sudah diperbarui dengan komentar.

## Hasil uji (live server, MongoDB Atlas)
| Uji | Hasil |
|-----|-------|
| `POST /auth/register` (user baru) | ✅ token + user (role viewer) |
| `POST /auth/login` (kredensial benar) | ✅ token |
| `POST /auth/login` (password salah) | ✅ 401 |
| `POST /auth/demo` | ✅ user demo + pohon seed |
| `GET /tree` (token demo) | ✅ 8 people, 11 relations |

## Catatan keamanan
- Saat rilis final, **boleh tetap aktifkan** demo login (dibutuhkan reviewer). Bila ingin
  mematikan setelah review: set `DEMO_LOGIN_ENABLED=false` dan rebuild backend.
- Rate-limit login password sebaiknya ditambahkan di produksi (belum ada) — lihat REVIEW_AUDIT.
- Akun demo punya `demo: true` agar mudah dibersihkan (`username: "demo"`).
