import { View, Text, Pressable, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { ArrowLeft, Check, Lock, Crown } from "lucide-react-native";
import { fonts, makeStyles, useTheme, usePremiumTheme, PREMIUM_THEMES, PremiumThemeId } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { useTree } from "@/src/tree-context";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20, paddingBottom: 12 },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  intro: { fontFamily: fonts.regular, fontSize: 13, color: c.muted, paddingHorizontal: 20, marginBottom: 8 },
  card: { flexDirection: "row", alignItems: "center", gap: 14, backgroundColor: c.surfaceSecondary, borderRadius: 18, padding: 16, borderWidth: 2 },
  swatches: { flexDirection: "row" },
  swatch: { width: 26, height: 40, borderRadius: 6, marginLeft: -8, borderWidth: 2, borderColor: c.surfaceSecondary },
  info: { flex: 1 },
  name: { fontFamily: fonts.semibold, fontSize: 16, color: c.onSurface },
  tagRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 3 },
  proTag: { flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: c.brandTertiary, paddingHorizontal: 7, paddingVertical: 2, borderRadius: 999 },
  proTagText: { fontFamily: fonts.bold, fontSize: 10, color: c.onBrandTertiary, letterSpacing: 0.5 },
  freeTagText: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  check: { width: 26, height: 26, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  upsell: { margin: 20, borderRadius: 18, padding: 16, flexDirection: "row", alignItems: "center", gap: 12 },
  upsellText: { flex: 1, fontFamily: fonts.medium, fontSize: 13, color: "#FFFFFF" },
  upsellBtn: { backgroundColor: "rgba(255,255,255,0.22)", paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999 },
  upsellBtnText: { fontFamily: fonts.semibold, fontSize: 13, color: "#FFFFFF" },
}));

export default function ThemesScreen() {
  const styles = useStyles();
  const { colors, gradient } = useTheme();
  const { themeId, setThemeId } = usePremiumTheme();
  const { t } = useI18n();
  const { activeTree } = useTree();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const isPro = activeTree?.plan === "pro" || activeTree?.plan === "family";

  const onSelect = (id: PremiumThemeId, premium: boolean) => {
    if (premium && !isPro) {
      router.push("/subscription");
      return;
    }
    setThemeId(id);
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="themes-back">
          <ArrowLeft size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("premium_themes")}</Text>
        <View style={{ width: 24 }} />
      </View>
      <Text style={styles.intro}>{t("premium_themes_desc")}</Text>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 30, gap: 12 }}>
        {PREMIUM_THEMES.map((th) => {
          const selected = th.id === themeId;
          const locked = th.premium && !isPro;
          return (
            <Pressable
              key={th.id}
              testID={`theme-${th.id}`}
              onPress={() => onSelect(th.id, th.premium)}
              style={[styles.card, { borderColor: selected ? colors.brandPrimary : colors.border }]}
            >
              <View style={styles.swatches}>
                {th.swatch.map((s, i) => (
                  <View key={i} style={[styles.swatch, { backgroundColor: s, marginLeft: i === 0 ? 0 : -8 }]} />
                ))}
              </View>
              <View style={styles.info}>
                <Text style={styles.name}>{th.name}</Text>
                <View style={styles.tagRow}>
                  {th.premium ? (
                    <View style={styles.proTag}>
                      <Crown size={10} color={colors.onBrandTertiary} />
                      <Text style={styles.proTagText}>PRO</Text>
                    </View>
                  ) : (
                    <Text style={styles.freeTagText}>{t("plan_free")}</Text>
                  )}
                </View>
              </View>
              {selected ? (
                <View style={[styles.check, { backgroundColor: colors.brandPrimary }]}>
                  <Check size={15} color={colors.onBrandPrimary} />
                </View>
              ) : locked ? (
                <Lock size={18} color={colors.muted} />
              ) : null}
            </Pressable>
          );
        })}
      </ScrollView>

      {!isPro ? (
        <Pressable onPress={() => router.push("/subscription")} testID="themes-upsell">
          <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={[styles.upsell, { marginBottom: insets.bottom + 16 }]}>
            <Crown size={22} color="#FFFFFF" />
            <Text style={styles.upsellText}>{t("theme_locked_msg")}</Text>
            <View style={styles.upsellBtn}>
              <Text style={styles.upsellBtnText}>{t("subscription")}</Text>
            </View>
          </LinearGradient>
        </Pressable>
      ) : null}
    </View>
  );
}
