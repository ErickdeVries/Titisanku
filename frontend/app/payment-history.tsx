import { View, Text, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useGoBack } from "@/src/hooks/useGoBack";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Receipt } from "lucide-react-native";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { paymentHistory, PaymentOrder } from "@/src/api";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20, paddingBottom: 12 },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", paddingTop: 60 },
  emptyIcon: { width: 72, height: 72, borderRadius: 999, alignItems: "center", justifyContent: "center", backgroundColor: c.surfaceTertiary, marginBottom: 14 },
  emptyText: { fontFamily: fonts.regular, fontSize: 14, color: c.muted, textAlign: "center", paddingHorizontal: 40 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 18, padding: 16, borderWidth: 1, borderColor: c.border, gap: 8 },
  rowTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  planName: { fontFamily: fonts.semibold, fontSize: 16, color: c.onSurface },
  amount: { fontFamily: fonts.display, fontSize: 18, color: c.onSurface },
  meta: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  orderId: { fontFamily: fonts.regular, fontSize: 11, color: c.muted },
  chip: { alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  chipText: { fontFamily: fonts.semibold, fontSize: 11 },
}));

const rupiah = (n: number) => "Rp" + (n || 0).toLocaleString("id-ID");
const fmtDate = (s?: string) => {
  try { return new Date(s!).toLocaleString("id-ID", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return "-"; }
};

export default function PaymentHistoryScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const goBack = useGoBack("/");
  const insets = useSafeAreaInsets();

  const { data, isLoading } = useQuery({ queryKey: ["paymentHistory"], queryFn: paymentHistory });
  const orders = data?.orders ?? [];

  const statusStyle = (status: string) => {
    if (status === "paid") return { bg: colors.brandTertiary, fg: colors.onBrandTertiary, label: t("pay_status_paid") };
    if (status === "failed") return { bg: colors.surfaceTertiary, fg: colors.error, label: t("pay_status_failed") };
    return { bg: colors.surfaceTertiary, fg: colors.muted, label: t("pay_status_pending") };
  };
  const planLabel = (p: string) => (p === "pro" ? "Pro" : p === "family" ? "Keluarga" : p);

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable onPress={() => goBack()} hitSlop={10} testID="payment-history-back">
          <ArrowLeft size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("payment_history")}</Text>
        <View style={{ width: 24 }} />
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      ) : orders.length === 0 ? (
        <View style={styles.center}>
          <View style={styles.emptyIcon}>
            <Receipt size={30} color={colors.muted} />
          </View>
          <Text style={styles.emptyText}>{t("payment_history_empty")}</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 30, gap: 12 }}>
          {orders.map((o: PaymentOrder) => {
            const s = statusStyle(o.status);
            return (
              <View key={o.order_id} style={styles.card}>
                <View style={styles.rowTop}>
                  <Text style={styles.planName}>Titisanku {planLabel(o.plan)}</Text>
                  <Text style={styles.amount}>{rupiah(o.amount)}</Text>
                </View>
                {o.tree_name ? <Text style={styles.meta}>{o.tree_name}</Text> : null}
                <Text style={styles.meta}>{fmtDate(o.paid_at || o.created_at)}</Text>
                <View style={styles.rowTop}>
                  <View style={[styles.chip, { backgroundColor: s.bg }]}>
                    <Text style={[styles.chipText, { color: s.fg }]}>{s.label}</Text>
                  </View>
                  <Text style={styles.orderId}>{o.order_id}</Text>
                </View>
              </View>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
}
