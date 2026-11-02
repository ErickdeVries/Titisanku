/**
 * Google Play Billing helper (Android).
 *
 * Produk langganan tahunan didefinisikan di Play Console (lihat
 * docs/play-review/PLAY_BILLING_SETUP.md). Purchases diverifikasi di server
 * (`POST /payments/play/verify`) sebelum plan diaktifkan — klien tidak pernah
 * mempercayai pembelian tanpa verifikasi.
 */
import { Platform } from "react-native";
import type { Purchase } from "expo-iap";

export type BillingPlan = "pro" | "family";

export type PlanPurchase = { purchaseToken: string; productId: string; purchase: Purchase };

const PRODUCTS: Record<BillingPlan, string> = {
  pro: "titisanku_pro_yearly",
  family: "titisanku_family_yearly",
};

export const billingSupported = Platform.OS === "android" || Platform.OS === "ios";

const APPLE_PRODUCTS: Record<BillingPlan, string> = {
  pro: process.env.EXPO_PUBLIC_IOS_PRO_PRODUCT_ID || "com.titisanku.pro.yearly",
  family: process.env.EXPO_PUBLIC_IOS_FAMILY_PRODUCT_ID || "com.titisanku.family.yearly",
};

export const productIdFor = (plan: BillingPlan) => Platform.OS === "ios" ? APPLE_PRODUCTS[plan] : PRODUCTS[plan];

/**
 * Selesaikan transaksi StoreKit agar tidak diputar ulang di antrean. Dipanggil
 * SETELAH server memverifikasi JWS & mengaktifkan plan.
 */
export async function finishApplePurchase(purchase: Purchase): Promise<void> {
  if (Platform.OS !== "ios") return;
  try {
    const iap = await import("expo-iap");
    await iap.finishTransaction({ purchase, isConsumable: false });
  } catch {
    // best-effort: entitlement sudah aktif di server, transaksi akan
    // diselesaikan pada percobaan berikutnya.
  }
}

/**
 * Pemulihan pembelian (wajib untuk review App Store): kirim ulang JWS semua
 * transaksi aktif ke server agar plan pulih setelah reinstall/ganti perangkat.
 */
export async function restoreApplePurchases(verify: (productId: string, jws: string) => Promise<unknown>): Promise<number> {
  if (Platform.OS !== "ios") return 0;
  const iap = await import("expo-iap");
  await iap.initConnection();
  const purchases = await iap.getAvailablePurchases();
  let restored = 0;
  for (const p of purchases) {
    if (!p.transactionId) continue;
    const jws = await iap.getTransactionJwsIOS(p.transactionId);
    if (!jws) continue;
    await verify(p.productId, jws);
    await iap.finishTransaction({ purchase: p, isConsumable: false }).catch(() => {});
    restored += 1;
  }
  return restored;
}

export async function purchaseApplePlan(plan: BillingPlan): Promise<{ productId: string; transactionJws: string; purchase: Purchase }> {
  if (Platform.OS !== "ios") throw new Error("unsupported");
  const iap = await import("expo-iap");
  const productId = APPLE_PRODUCTS[plan];
  await iap.initConnection();
  const products = await iap.fetchProducts({ skus: [productId], type: "subs" });
  if (!products?.length) throw new Error("Produk Apple belum tersedia.");
  const purchase = await new Promise<Purchase>((resolve, reject) => {
    let settled = false;
    const updated = iap.purchaseUpdatedListener((p) => {
      if (!settled && p.productId === productId) { settled = true; resolve(p); }
    });
    const errors = iap.purchaseErrorListener((e) => {
      if (!settled) { settled = true; reject(e); }
    });
    iap.requestPurchase({ type: "subs", request: { apple: { sku: productId } } }).catch(reject).finally(() => {
      setTimeout(() => { updated.remove(); errors.remove(); }, 60000);
    });
  });
  if (!purchase.transactionId) throw new Error("Apple transaction ID tidak tersedia.");
  const jws = await iap.getTransactionJwsIOS(purchase.transactionId);
  if (!jws) throw new Error("Apple tidak mengembalikan transaksi terverifikasi.");
  return { productId, transactionJws: jws, purchase };
}

/**
 * Lakukan pembelian langganan lewat Play Billing dan kembalikan purchase token
 * untuk diverifikasi server. Melempar error bila pengguna membatalkan / gagal.
 */
export async function purchasePlan(plan: BillingPlan): Promise<PlanPurchase> {
  if (!billingSupported) throw new Error("unsupported");
  const iap = await import("expo-iap");

  await iap.initConnection();

  const result = await new Promise<PlanPurchase>((resolve, reject) => {
    let settled = false;
    const done = (fn: () => void) => {
      if (settled) return;
      settled = true;
      sub.remove();
      errSub.remove();
      fn();
    };
    const sub = iap.purchaseUpdatedListener((purchase) => {
      const token = purchase.purchaseToken ?? null;
      if (!token) return;
      // Abaikan transaksi yang bukan untuk produk ini atau belum lunas,
      // agar purchase tertunda dari produk lain tidak ikut terpakai.
      if (purchase.productId && purchase.productId !== PRODUCTS[plan]) return;
      const state = (purchase as { purchaseState?: string | number }).purchaseState;
      if (state === "pending" || state === 2) return;
      // Simpan objek Purchase utuh: `finishTransaction` di expo-iap v6
      // memerlukan data lengkap (bukan sekadar token + productId).
      done(() =>
        resolve({
          purchaseToken: token,
          productId: purchase.productId || PRODUCTS[plan],
          purchase,
        }),
      );
    });
    const errSub = iap.purchaseErrorListener((error) => {
      const code = (error as { code?: string })?.code || "";
      if (code === "user-cancelled" || code === "user_cancelled") {
        done(() => reject(new Error("cancelled")));
      } else {
        done(() => reject(new Error(error?.message || "purchase-failed")));
      }
    });

    iap
      .requestPurchase({
        type: "subs",
        request: { google: { skus: [PRODUCTS[plan]] } },
      })
      .catch((e: unknown) => done(() => reject(e instanceof Error ? e : new Error("purchase-failed"))));
  });

  return result;
}

/**
 * Selesaikan transaksi Play agar tidak dikembalikan. Dipanggil SETELAH server
 * memverifikasi & mengaktifkan plan.
 */
export async function finishPlayPurchase(
  purchaseToken: string,
  productId: string,
  purchase?: Purchase,
): Promise<void> {
  if (!billingSupported) return;
  const iap = await import("expo-iap");
  // expo-iap v6: finishTransaction menerima objek Purchase lengkap.
  // Prioritaskan objek dari listener; kalau tidak ada, cari di daftar pembelian aktif.
  // Bila tetap tidak ketemu, lewati — server sudah acknowledge lewat Play
  // Developer API sehingga dana tidak dikembalikan.
  let target: Purchase | undefined = purchase;
  if (!target) {
    try {
      const pending = await iap.getAvailablePurchases();
      target = pending.find(
        (p) => p.purchaseToken === purchaseToken || p.productId === productId,
      );
    } catch {
      return;
    }
  }
  if (!target) return;
  try {
    await iap.finishTransaction({ purchase: target, isConsumable: false });
  } catch {
    // best-effort: server sudah acknowledge via Play Developer API
  }
}
