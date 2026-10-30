/**
 * Google Play Billing helper (Android).
 *
 * Produk langganan tahunan didefinisikan di Play Console (lihat
 * docs/play-review/PLAY_BILLING_SETUP.md). Purchases diverifikasi di server
 * (`POST /payments/play/verify`) sebelum plan diaktifkan — klien tidak pernah
 * mempercayai pembelian tanpa verifikasi.
 */
import { Platform } from "react-native";

export type BillingPlan = "pro" | "family";

const PRODUCTS: Record<BillingPlan, string> = {
  pro: "titisanku_pro_yearly",
  family: "titisanku_family_yearly",
};

export const billingSupported = Platform.OS === "android";

export const productIdFor = (plan: BillingPlan) => PRODUCTS[plan];

/**
 * Lakukan pembelian langganan lewat Play Billing dan kembalikan purchase token
 * untuk diverifikasi server. Melempar error bila pengguna membatalkan / gagal.
 */
export async function purchasePlan(plan: BillingPlan): Promise<{ purchaseToken: string; productId: string }> {
  if (!billingSupported) throw new Error("unsupported");
  const iap = await import("expo-iap");

  await iap.initConnection();

  const result = await new Promise<{ purchaseToken: string; productId: string }>((resolve, reject) => {
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
      done(() => resolve({ purchaseToken: token, productId: purchase.productId || PRODUCTS[plan] }));
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
export async function finishPlayPurchase(purchaseToken: string, productId: string): Promise<void> {
  if (!billingSupported) return;
  const iap = await import("expo-iap");
  // finishTransaction menandai transaksi selesai; parameter bervariasi per versi.
  try {
    await (iap as unknown as { finishTransaction: (args: unknown) => Promise<void> }).finishTransaction({
      productId,
      purchaseToken,
      isConsumable: false,
    });
  } catch {
    // best-effort: server sudah acknowledge via Play Developer API
  }
}
