# Aset Store Listing — Titisanku

> Lokasi hasil: `docs/play-review/assets/`
> Yang sudah dibuat agent ada di kolom Status ✅; sisanya perlu device/gambar manual.

## Spesifikasi wajib Play

| Aset | Ukuran | Format | Wajib? | Status |
|------|--------|--------|--------|--------|
| App icon (hi-res) | 512×512 px | PNG 32-bit | ✅ Wajib | ✅ `assets/icon-512.png` |
| Feature graphic | 1024×500 px | PNG/JPEG | ✅ Wajib | ✅ `assets/feature-graphic-1024x500.png` |
| Phone screenshots | min 2 (saran 4–8), 320–3840 px sisi, rasio 16:9/9:16 | PNG/JPEG | ✅ Wajib min 2 | ⬜ Perlu device |
| 7" tablet screenshots | opsional (disarankan) | PNG | Opsional | ⬜ |
| 10" tablet screenshots | opsional (disarankan) | PNG | Opsional | ⬜ |
| Promo video | YouTube URL | — | Opsional | ⬜ |

## Aset sudah dibuat ✅

### 1. `icon-512.png` (512×512)
- Di-resize bicubic dari `frontend/assets/images/icon.png` (1024).
- Latar: logo Titisanku (sesuai `adaptive-icon` bg `#12275C`).
- **Catatan:** Play membulatkan sudut otomatis; pastikan logo punya padding aman (sudah, karena icon asli
  sudah full-bleed flat).

### 2. `feature-graphic-1024x500.png`
- Latar navy gradient `#12275C → #1E3A73`.
- Emblem emas (tree of life) di kiri + judul "Titisanku / Silsilah Keluarga" + tagline
  "Setiap nama layak dikenang." + sub-tagline.
- Font Poppins (dari `frontend/assets/fonts`) — konsisten dengan app.
- Sudah aman: teks utama berada di area tengah (Play menimpa sebagian tepi dengan overlay tombol "Instal").

## Screenshot — rencana (perlu device)

Ambil di **device fisik** (Play menolak screenshot simulasi bila ada status bar palsu). Urutan naratif:

1. **Pohon keluarga** — kanvas interaktif, banyak node. Caption: "Pohon keluarga interaktif".
2. **Detail orang** — foto + form multi-tab. Caption: "Simpan foto & kenangan".
3. **Tambah relasi** — tombol 4 arah. Caption: "Bangun silsilah bersama".
4. **Pencarian** — hasil pencarian. Caption: "Temukan siapa pun dengan cepat".
5. **Chat keluarga** — daftar pesan. Caption: "Ngobrol dengan keluarga".
6. **Backup/PDF** — dialog export. Caption: "Cadangkan & ekspor".

**Panduan gaya screenshot:**
- Gunakan akun demo berisi data contoh ("Keluarga Contoh") agar tidak memuat data pribadi nyata.
- Ukuran: 1080×1920 (HP) atau 1440×2560. Rasio 9:16.
- Tambah bingkai perangkat + caption bawah (opsional, konsisten dengan warna brand `#12275C` & emas `#D4AF37`).
- Hindari menampilkan email/ponsel asli anggota keluarga — gunakan data fiktif.

## Langkah memperbarui aset nanti
- Regenerate feature graphic: script PowerShell memakai `System.Drawing` + `PrivateFontCollection`
  (Poppins dari repo). Contoh ada di riwayat kerja (agent berikutnya bisa melihat pola:
  load `Poppins-Bold.ttf` → `LinearGradientBrush` navy → `DrawImage` emblem → `DrawString` judul).

## Checklist aset
- [x] icon 512×512
- [x] feature graphic 1024×500
- [ ] 4–8 screenshot HP (device, akun demo, data fiktif)
- [ ] (opsional) screenshot tablet
- [ ] (opsional) promo video YouTube
