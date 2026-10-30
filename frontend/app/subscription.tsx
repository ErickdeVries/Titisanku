import { useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, Alert, Platform } from "react-native";
import { useRouter } from "expo-router";
import { useGoBack } from "@/src/hooks/useGoBack";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import * as WebBrowser from "expo-web-browser";
import { ArrowLeft, Crown, Check, Users, Image as ImageIcon, GitBranch, Receipt, ChevronRight } from "lucide-react-native";
import { fonts, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { useTree } from "@/src/tree-context";
import { createSnap, paymentStatus, playVerify } from "@/src/api";
import { purchasePlan, finishPlayPurchase, billingSupported } from "@/src/billing";
import { formatBytes } from "@/src/utils/format";

type PlanId = "free" | "pro" | "family";
const PLANS: { id: PlanId; name: string; price: string; perks: string[] }[] = [
  { id: "free", name: "Free", price: "Gratis", perks: ["1 Pohon Keluarga", "50 Orang", "500 MB Foto", "3 Editor", "PDF dengan watermark"] },
  { id: "pro", name: "Pro", price: "Rp149.000/tahun", perks: ["Orang tak terbatas", "10 GB Foto", "10 Editor", "PDF tanpa watermark", "Backup Google Drive", "Tema Premium"] },
  { id: "family", name: "Keluarga", price: "Rp199.000/tahun", perks: ["Semua fitur Pro", "25 GB Foto", "50 Editor", "Cetak Buku Silsilah"] },
];
const RANK: Record<PlanId, number> = { free: 0, pro: 1, family: 2 };
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function SubscriptionScreen() {
  const { colors, gradient } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const goBack = useGoBack("/");
  const insets = useSafeAreaInsets();
  const { activeTree, activeTreeId, refreshTrees } = useTree();
  const [busy, setBusy] = useState<PlanId | null>(null);
  // Reading the clock is impure, so it is captured once per render pass instead
  // of being called inline while rendering.
  const [now] = useState(() => Date.now());

  const plan = (activeTree?.plan ?? "free") as PlanId;
  const isAdmin = activeTree?.role === "admin";
  const expIso = (activeTree as any)?.expires_at as string | undefined;
  const expDate = expIso ? new Date(expIso) : null;
  const daysLeft = expDate ? Math.ceil((expDate.getTime() - now) / 86400000) : null;
  const expFmt = expDate
    ? expDate.toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" })
    : null;
  const limits = activeTree?.plan_limits;
  // Kuota foto kini berbasis byte (bukan jumlah foto), mengikuti harga asli
  // penyimpanan. Batas ini datang dari backend sebagai storage_limit.
  const storageUsed = activeTree?.storage_used ?? 0;
  const storageMax = activeTree?.storage_limit ?? null;
  const usage = [
    { icon: <Users size={16} color={colors.brandSecondary} />, label: "Orang", value: `${activeTree?.person_count ?? 0}${limits?.people != null ? `/${limits.people}` : ""}`, unlimited: limits?.people == null },
    { icon: <GitBranch size={16} color={colors.brandSecondary} />, label: "Editor", value: `${activeTree?.editor_count ?? 0}${limits?.editors != null ? `/${limits.editors}` : ""}`, unlimited: limits?.editors == null },
    { icon: <ImageIcon size={16} color={colors.brandSecondary} />, label: "Penyimpanan", value: `${formatBytes(storageUsed)}${storageMax != null ? `/${formatBytes(storageMax)}` : ""}`, unlimited: storageMax == null },
  ];

  const pollUntilPaid = async (orderId: string) => {
    for (let i = 0; i < 40; i++) {
      await sleep(3000);
      try {
        const s = await paymentStatus(orderId);
        if (s.status === "paid") {
          await refreshTrees();
          Alert.alert(t("payment_success_title"), t("payment_success_msg"));
          return true;
        }
        if (s.status === "failed") {
          Alert.alert(t("payment_failed_title"), t("payment_failed_msg"));
          return false;
        }
      } catch {
        /* keep polling */
      }
    }
    Alert.alert(t("payment_pending_title"), t("payment_pending_msg"));
    return false;
  };

  const doUpgrade = async (target: PlanId) => {
    if (!activeTreeId) return;
    if (target !== "pro" && target !== "family") return;
    setBusy(target);
    try {
      if (billingSupported) {
        // Android: wajib pakai Google Play Billing untuk produk digital.
        const purchase = await purchasePlan(target);
        const res = await playVerify(purchase.productId, purchase.purchaseToken, activeTreeId);
        await finishPlayPurchase(purchase.purchaseToken, purchase.productId);
        await refreshTrees();
        Alert.alert(t("payment_success_title"), `${t("payment_success_msg")} (${res.plan})`);
        return;
      }
      // Web: tetap Midtrans (Play Billing tidak berlaku di luar aplikasi Android).
      const finishUrl = Platform.OS === "web" ? window.location.origin + "/" : undefined;
      const res = await createSnap(target, finishUrl);
      if (Platform.OS === "web") {
        window.open(res.redirect_url, "_blank");
      } else {
        await WebBrowser.openBrowserAsync(res.redirect_url);
      }
      await pollUntilPaid(res.order_id);
    } catch (e) {
      const msg = (e as Error)?.message;
      if (msg === "cancelled") {
        // pengguna membatalkan pembelian; jangan tampilkan error keras
      } else if (msg === "unsupported") {
        Alert.alert(t("payment_failed_title"), t("payment_failed_msg"));
      } else {
        console.log("payment error", e);
        Alert.alert(t("payment_failed_title"), t("payment_failed_msg"));
      }
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={[styles.root, { backgroundColor: colors.surface }]}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={() => goBack()} hitSlop={10}>
          <ArrowLeft size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={[styles.title, { color: colors.onSurface }]}>{t("subscription")}</Text>
        <View style={{ width: 24 }} />
      </View>

      {!activeTree ? (
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 30, gap: 16 }}>
          {/* Current usage */}
          <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.usageCard}>
            <View style={styles.usageTop}>
              <Crown size={22} color="#FFFFFF" />
              <Text style={styles.usagePlan}>{plan === "free" ? "Free" : plan === "pro" ? "Pro" : "Keluarga"}</Text>
            </View>
            <Text style={styles.usageTree} numberOfLines={1}>{activeTree.name}</Text>
            {plan !== "free" && expFmt ? (
              <Text style={styles.usageExp}>Berlaku sampai {expFmt}</Text>
            ) : null}
            <View style={styles.usageRow}>
              {usage.map((u) => (
                <View key={u.label} style={styles.usageItem}>
                  <Text style={styles.usageVal}>{u.value}</Text>
                  <Text style={styles.usageLabel}>{u.label}{u.unlimited ? " ∞" : ""}</Text>
                </View>
              ))}
            </View>
          </LinearGradient>

          {plan !== "free" && daysLeft != null && daysLeft <= 14 ? (
            <View style={[styles.expBanner, { backgroundColor: colors.brandTertiary, borderColor: colors.brandPrimary }]}>
              <Crown size={18} color={colors.brandSecondary} />
              <Text style={[styles.expBannerText, { color: colors.onSurface }]}>
                {daysLeft <= 0
                  ? "Paket Anda telah berakhir. Perpanjang untuk membuka kembali fitur premium."
                  : `Paket berakhir dalam ${daysLeft} hari. Perpanjang agar fitur premium tetap aktif.`}
              </Text>
            </View>
          ) : null}

          {/* Plans */}
          {PLANS.map((p) => {
            const current = p.id === plan;
            const canUpgrade = isAdmin && RANK[p.id] > RANK[plan];
            return (
              <View
                key={p.id}
                style={[styles.planCard, { backgroundColor: colors.surfaceSecondary, borderColor: current ? colors.brandPrimary : colors.border, borderWidth: current ? 2 : 1 }]}
              >
                <View style={styles.planHead}>
                  <View>
                    <Text style={[styles.planName, { color: colors.onSurface }]}>{p.name}</Text>
                    <Text style={[styles.planPrice, { color: colors.brandSecondary }]}>{p.price}</Text>
                  </View>
                  {current ? (
                    <View style={[styles.currentChip, { backgroundColor: colors.brandTertiary }]}>
                      <Check size={13} color={colors.onBrandTertiary} />
                      <Text style={[styles.currentChipText, { color: colors.onBrandTertiary }]}>{t("current_plan")}</Text>
                    </View>
                  ) : null}
                </View>
                {p.perks.map((perk) => (
                  <View key={perk} style={styles.perkRow}>
                    <Check size={15} color={colors.success} />
                    <Text style={[styles.perkText, { color: colors.onSurfaceSecondary }]}>{perk}</Text>
                  </View>
                ))}
                {canUpgrade ? (
                  <Pressable onPress={() => doUpgrade(p.id)} disabled={busy === p.id} style={{ marginTop: 10 }} testID={`upgrade-${p.id}`}>
                    <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.cta}>
                      {busy === p.id ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.ctaText}>{t("upgrade_to_pro").replace("Pro", p.name)}</Text>}
                    </LinearGradient>
                  </Pressable>
                ) : null}
              </View>
            );
          })}

          {!isAdmin ? (
            <Text style={[styles.note, { color: colors.muted }]}>Hanya admin pohon yang dapat mengubah paket. Editor tetap menikmati fitur paket ini.</Text>
          ) : billingSupported ? (
            <Text style={[styles.note, { color: colors.muted }]}>Langganan diproses oleh Google Play. Paket aktif otomatis setelah pembayaran berhasil, dan dapat dikelola di Play Store &gt; Pembayaran &amp; langganan.</Text>
          ) : (
            <Text style={[styles.note, { color: colors.muted }]}>Pembayaran aman diproses oleh Midtrans. Paket aktif otomatis setelah pembayaran berhasil.</Text>
          )}

          <Pressable
            style={[styles.historyRow, { backgroundColor: colors.surfaceSecondary, borderColor: colors.border }]}
            onPress={() => router.push("/payment-history")}
            testID="payment-history-row"
          >
            <Receipt size={20} color={colors.brandSecondary} />
            <View style={{ flex: 1 }}>
              <Text style={[styles.historyTitle, { color: colors.onSurface }]}>{t("payment_history")}</Text>
              <Text style={[styles.historyDesc, { color: colors.muted }]}>{t("payment_history_desc")}</Text>
            </View>
            <ChevronRight size={20} color={colors.muted} />
          </Pressable>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20, paddingBottom: 12 },
  title: { fontFamily: fonts.display, fontSize: 22 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  usageCard: { borderRadius: 24, padding: 20, gap: 6 },
  usageTop: { flexDirection: "row", alignItems: "center", gap: 10 },
  usagePlan: { fontFamily: fonts.bold, fontSize: 20, color: "#FFFFFF" },
  usageTree: { fontFamily: fonts.medium, fontSize: 14, color: "rgba(255,255,255,0.85)" },
  usageExp: { fontFamily: fonts.regular, fontSize: 12, color: "rgba(255,255,255,0.8)", marginTop: 2 },
  expBanner: { flexDirection: "row", alignItems: "center", gap: 10, padding: 14, borderRadius: 16, borderWidth: 1 },
  expBannerText: { fontFamily: fonts.medium, fontSize: 13, flex: 1, lineHeight: 18 },
  usageRow: { flexDirection: "row", justifyContent: "space-between", marginTop: 12 },
  usageItem: { alignItems: "center", flex: 1 },
  usageVal: { fontFamily: fonts.bold, fontSize: 18, color: "#FFFFFF" },
  usageLabel: { fontFamily: fonts.regular, fontSize: 12, color: "rgba(255,255,255,0.85)" },
  planCard: { borderRadius: 24, padding: 18, gap: 8 },
  planHead: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 4 },
  planName: { fontFamily: fonts.display, fontSize: 20 },
  planPrice: { fontFamily: fonts.semibold, fontSize: 14, marginTop: 2 },
  currentChip: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999 },
  currentChipText: { fontFamily: fonts.semibold, fontSize: 11 },
  perkRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  perkText: { fontFamily: fonts.regular, fontSize: 14 },
  cta: { height: 50, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  ctaText: { fontFamily: fonts.semibold, fontSize: 15, color: "#FFFFFF" },
  note: { fontFamily: fonts.regular, fontSize: 12, textAlign: "center", paddingHorizontal: 10 },
  historyRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: 16, borderRadius: 18, borderWidth: 1 },
  historyTitle: { fontFamily: fonts.semibold, fontSize: 15 },
  historyDesc: { fontFamily: fonts.regular, fontSize: 12, marginTop: 2 },
});
