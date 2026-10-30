/**
 * Format ukuran byte menjadi teks ringkas untuk UI (mis. "500 MB", "10,0 GB").
 *
 * Dipakai bersamaan dengan kuota penyimpanan berbasis byte dari backend
 * (`storage_used` / `storage_limit`). Aturannya sengaja dibuat SAMA PERSIS
 * dengan `fmt_size` di backend: di bawah 1 GB dibulatkan ke MB, 1 GB ke atas
 * memakai satu desimal. Kalau keduanya berbeda, pengguna bisa melihat "500 MB"
 * padahal server sudah menolak karena kuota habis.
 *
 * Koma dipakai sebagai pemisah desimal (format Indonesia).
 */
const MB = 1024 * 1024;
const GB = 1024 * MB;

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || Number.isNaN(bytes)) return "—";
  if (bytes <= 0) return "0 MB";
  if (bytes >= GB) return `${(bytes / GB).toFixed(1).replace(".", ",")} GB`;
  return `${Math.round(bytes / MB)} MB`;
}
