import { View, Text, Pressable, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { ArrowLeft, Check, Lock, Crown } from "lucide-react-native";
import { fonts, makeStyles, useTheme, usePremiumTheme, PREMIUM_THEMES, PremiumThemeId, BG_PRESETS, BgPresetId } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { useTree } from "@/src/tree-context";
import { useAuth } from "@/src/auth";

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
  sectionLabel: { fontFamily: fonts.semibold, fontSize: 13, color: c.onSurfaceSecondary, marginTop: 18, marginBottom: 10, textTransform: "uppercase", letterSpacing: 0.5 },
  bgRow: { flexDirection: "row", flexWrap: "wrap", gap: 14 },
  bgItem: { alignItems: "center", width: 62, gap: 6 },
  bgSwatch: { width: 48, height: 48, borderRadius: 999, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  bgName: { fontFamily: fonts.regular, fontSize: 11, color: c.onSurfaceSecondary, textAlign: "center" },
}));

export default function ThemesScreen() {
  const styles = useStyles();
  const { colors, gradient } = useTheme();
  const { themeId, setThemeId, chatBgId, setChatBgId, canvasBgId, setCanvasBgId } = usePremiumTheme();
  const { t } = useI18n();
  const { activeTree } = useTree();
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const isPro =
    activeTree?.plan === "pro" ||
    activeTree?.plan === "family" ||
    activeTree?.plan === "unlimited" ||
    !!user?.is_superadmin;

  const onSelect = (id: PremiumThemeId, premium: boolean) => {
    if (premium && !isPro) {
      router.push("/subscription");
      return;
    }
    setThemeId(id);
  };

  const renderBgPicker = (label: string, value: BgPresetId, onChange: (id: BgPresetId) => void, keyPrefix: string) => (
    <View>
      <Text style={styles.sectionLabel}>{label}</Text>
      <View style={styles.bgRow}>
        {BG_PRESETS.map((b) => {
          const sel = b.id === value;
          return (
            <Pressable key={b.id} onPress={() => onChange(b.id)} style={styles.bgItem} testID={`${keyPrefix}-${b.id}`}>
              <View style={[styles.bgSwatch, { backgroundColor: b.color ?? colors.surfaceTertiary, borderColor: sel ? colors.brandPrimary : colors.border }]}>
                {b.color === null ? (
                  <Crown size={16} color={colors.brandPrimary} />
                ) : sel ? (
                  <Check size={16} color={b.id === "graphite" ? "#FFFFFF" : "#1A1A1A"} />
                ) : null}
              </View>
              <Text style={styles.bgName}>{b.name}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );

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

        {renderBgPicker(t("chat_bg_label"), chatBgId, setChatBgId, "chatbg")}
        {renderBgPicker(t("canvas_bg_label"), canvasBgId, setCanvasBgId, "canvasbg")}
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
