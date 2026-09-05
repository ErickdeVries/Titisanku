import { useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { ArrowLeft, Crown, Check } from "lucide-react-native";
import { fonts, useTheme, brandGradient } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { useTree } from "@/src/tree-context";
import { UpgradeModal } from "@/src/components/UpgradeModal";

const PERKS = [
  "Anggota tak terbatas per pohon",
  "PDF tanpa watermark",
  "Backup ke Google Drive",
  "Dukungan prioritas",
];

export default function SubscriptionScreen() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { activeTree } = useTree();
  const [upgradeOpen, setUpgradeOpen] = useState(false);

  const isPro = activeTree?.plan === "pro";
  const count = activeTree?.person_count ?? 0;
  const limit = activeTree?.limit ?? null;
  const pct = limit ? Math.min(100, Math.round((count / limit) * 100)) : 100;

  return (
    <View style={[styles.root, { backgroundColor: colors.surface }]}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={() => router.back()} hitSlop={10}>
          <ArrowLeft size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={[styles.title, { color: colors.onSurface }]}>{t("subscription")}</Text>
        <View style={{ width: 24 }} />
      </View>

      {!activeTree ? (
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 16 }}>
          <LinearGradient colors={brandGradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.planCard}>
            <View style={styles.planTop}>
              <Crown size={26} color="#FFFFFF" />
              <Text style={styles.planName}>{isPro ? t("plan_pro") : t("plan_free")}</Text>
            </View>
            <Text style={styles.planTree} numberOfLines={1}>{activeTree.name}</Text>
            <Text style={styles.planSlots}>
              {t("people_slots")}: {count}{limit ? ` / ${limit}` : ` · ${t("unlimited")}`}
            </Text>
            {limit ? (
              <View style={styles.barBg}>
                <View style={[styles.barFill, { width: `${pct}%` }]} />
              </View>
            ) : null}
          </LinearGradient>

          <View style={[styles.perkCard, { backgroundColor: colors.surfaceSecondary }]}>
            <Text style={[styles.perkTitle, { color: colors.onSurface }]}>{t("plan_pro")}</Text>
            {PERKS.map((p) => (
              <View key={p} style={styles.perkRow}>
                <View style={[styles.perkDot, { backgroundColor: colors.brandTertiary }]}>
                  <Check size={13} color={colors.onBrandTertiary} />
                </View>
                <Text style={[styles.perkText, { color: colors.onSurfaceSecondary }]}>{p}</Text>
              </View>
            ))}
          </View>

          {isPro ? (
            <View style={[styles.activeBanner, { backgroundColor: colors.brandTertiary }]}>
              <Crown size={18} color={colors.onBrandTertiary} />
              <Text style={[styles.activeText, { color: colors.onBrandTertiary }]}>{t("pro_active")}</Text>
            </View>
          ) : (
            <Pressable testID="open-upgrade" onPress={() => setUpgradeOpen(true)}>
              <LinearGradient colors={brandGradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.cta}>
                <Text style={styles.ctaText}>{t("upgrade_to_pro")}</Text>
              </LinearGradient>
            </Pressable>
          )}
        </ScrollView>
      )}

      <UpgradeModal visible={upgradeOpen} onClose={() => setUpgradeOpen(false)} limit={limit} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20, paddingBottom: 12 },
  title: { fontFamily: fonts.display, fontSize: 22 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  planCard: { borderRadius: 22, padding: 22, gap: 6 },
  planTop: { flexDirection: "row", alignItems: "center", gap: 10 },
  planName: { fontFamily: fonts.bold, fontSize: 20, color: "#FFFFFF" },
  planTree: { fontFamily: fonts.medium, fontSize: 14, color: "rgba(255,255,255,0.85)" },
  planSlots: { fontFamily: fonts.regular, fontSize: 13, color: "rgba(255,255,255,0.9)", marginTop: 6 },
  barBg: { height: 8, borderRadius: 999, backgroundColor: "rgba(255,255,255,0.3)", marginTop: 8, overflow: "hidden" },
  barFill: { height: 8, borderRadius: 999, backgroundColor: "#FFFFFF" },
  perkCard: { borderRadius: 18, padding: 18, gap: 12 },
  perkTitle: { fontFamily: fonts.semibold, fontSize: 16, marginBottom: 2 },
  perkRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  perkDot: { width: 24, height: 24, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  perkText: { fontFamily: fonts.medium, fontSize: 14 },
  activeBanner: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 16, paddingVertical: 16 },
  activeText: { fontFamily: fonts.semibold, fontSize: 15 },
  cta: { height: 54, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  ctaText: { fontFamily: fonts.semibold, fontSize: 16, color: "#FFFFFF" },
});
