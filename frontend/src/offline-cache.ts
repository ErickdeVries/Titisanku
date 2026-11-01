import AsyncStorage from "@react-native-async-storage/async-storage";
import type { Query, QueryClient } from "@tanstack/react-query";

/**
 * Cache data di HP supaya pohon & profil orang tetap terbuka saat sinyal jelek
 * atau saat aplikasi dibuka ulang (hemat kuota juga).
 *
 * Yang disimpan hanya data yang boleh dibaca berulang dan tidak sensitif
 * terhadap waktu: `["tree"]` dan `["person", id]`. Saat aplikasi dibuka,
 * data cache dipakai sebagai tampilan awal, lalu React Query tetap mengambil
 * versi terbaru dari server di latar belakang.
 */
const PREFIX = "rq-cache:v1:";

type CacheEntry = { key: readonly unknown[]; data: unknown; at: number };

export function isCacheableKey(key: readonly unknown[]): boolean {
  return key[0] === "tree" || key[0] === "person";
}

function storageKey(key: readonly unknown[]): string {
  return PREFIX + JSON.stringify(key);
}

/** Muat isi cache ke QueryClient. Aman dipanggil berkali-kali. */
export async function hydrateQueryCache(qc: QueryClient): Promise<void> {
  try {
    const keys = (await AsyncStorage.getAllKeys()).filter((k) => k.startsWith(PREFIX));
    if (!keys.length) return;
    const pairs = await AsyncStorage.multiGet(keys);
    for (const [, raw] of pairs) {
      if (!raw) continue;
      try {
        const entry = JSON.parse(raw) as CacheEntry;
        if (!Array.isArray(entry.key) || entry.data == null) continue;
        // updatedAt = waktu data diambil: tetap dianggap basi (stale) sehingga
        // server selalu dicek ulang, tapi UI sudah punya sesuatu untuk digambar.
        qc.setQueryData(entry.key, entry.data, { updatedAt: entry.at });
      } catch {
        // entri rusak (versi lama) -> abaikan, nanti ditimpa.
      }
    }
  } catch (e) {
    console.log("gagal memuat cache offline", e);
  }
}

const pending = new Map<string, ReturnType<typeof setTimeout>>();

/**
 * Simpan setiap perubahan query yang cacheable (debounce 800ms agar satu
 * render yang menulis banyak query tidak menulis berulang kali).
 * Return fungsi untuk berhenti berlangganan.
 */
export function persistQueryCache(qc: QueryClient): () => void {
  const unsubscribe = qc.getQueryCache().subscribe((event) => {
    if (!event || event.type !== "updated") return;
    const q = event.query as Query;
    if (!isCacheableKey(q.queryKey)) return;
    if (q.state.status !== "success" || q.state.data === undefined) return;
    const sk = storageKey(q.queryKey);
    const timer = pending.get(sk);
    if (timer) clearTimeout(timer);
    pending.set(
      sk,
      setTimeout(() => {
        pending.delete(sk);
        const entry: CacheEntry = {
          key: q.queryKey,
          data: q.state.data,
          at: q.state.dataUpdatedAt || Date.now(),
        };
        AsyncStorage.setItem(sk, JSON.stringify(entry)).catch(() => {});
      }, 800),
    );
  });
  return () => {
    pending.forEach((t) => clearTimeout(t));
    pending.clear();
    unsubscribe();
  };
}

/** Hapus semua cache (dipanggil saat logout / ganti akun). */
export async function clearOfflineCache(): Promise<void> {
  try {
    pending.forEach((t) => clearTimeout(t));
    pending.clear();
    const keys = (await AsyncStorage.getAllKeys()).filter((k) => k.startsWith(PREFIX));
    if (keys.length) await AsyncStorage.multiRemove(keys);
  } catch (e) {
    console.log("gagal menghapus cache offline", e);
  }
}
