import { View, Text, Modal, Pressable, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Crown, X, Check, ShieldQuestion } from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { fonts, useTheme, brandGradient } from "@/src/theme";
import { useTree } from "@/src/tree-context";

const PERKS = ["Anggota tak terbatas", "PDF tanpa watermark", "Backup ke Google Drive", "10-50 Editor"];

export function UpgradeModal({
  visible,
  onClose,
  limit,
}: {
  visible: boolean;
  onClose: () => void;
  limit?: number | null;
}) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { activeTree } = useTree();
  const isAdmin = activeTree?.role === "admin";
  const treeName = activeTree?.name ?? "";

  const goUpgrade = () => {
    onClose();
    router.push("/subscription");
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.bg} onPress={onClose}>
        <Pressable style={[styles.sheet, { backgroundColor: colors.surfaceSecondary, paddingBottom: insets.bottom + 24 }]} onPress={() => {}}>
          <Pressable style={styles.close} onPress={onClose} hitSlop={10}>
            <X size={22} color={colors.muted} />
          </Pressable>
          <LinearGradient colors={brandGradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.badge}>
            <Crown size={30} color="#FFFFFF" />
          </LinearGradient>
          <Text style={[styles.title, { color: colors.onSurface }]}>Buka Kunci Pohon Anda</Text>
          <Text style={[styles.desc, { color: colors.muted }]}>
            Pohon Keluarga <Text style={{ fontFamily: fonts.semibold, color: colors.onSurface }}>{treeName}</Text> sudah {limit ?? 50} orang. Upgrade ke Pro untuk buka kunci generasi selanjutnya. 1x bayar untuk semua anggota.
          </Text>
          <View style={styles.perks}>
            {PERKS.map((p) => (
              <View key={p} style={styles.perkRow}>
                <View style={[styles.perkDot, { backgroundColor: colors.brandTertiary }]}>
                  <Check size={13} color={colors.onBrandTertiary} />
                </View>
                <Text style={[styles.perkText, { color: colors.onSurfaceSecondary }]}>{p}</Text>
              </View>
            ))}
          </View>

          <Pressable onPress={goUpgrade} style={{ alignSelf: "stretch" }} testID="upgrade-now">
            <LinearGradient colors={brandGradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.cta}>
              <Text style={styles.ctaText}>Upgrade Sekarang</Text>
            </LinearGradient>
          </Pressable>

          {!isAdmin ? (
            <Pressable onPress={onClose} style={[styles.secondary, { borderColor: colors.border }]} testID="ask-admin">
              <ShieldQuestion size={18} color={colors.onSurfaceSecondary} />
              <Text style={[styles.secondaryText, { color: colors.onSurfaceSecondary }]}>Tanya ke Admin</Text>
            </Pressable>
          ) : null}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(31,42,68,0.5)", justifyContent: "flex-end" },
  sheet: { borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 24, alignItems: "center", gap: 14 },
  close: { position: "absolute", top: 16, right: 16, zIndex: 2 },
  badge: { width: 64, height: 64, borderRadius: 999, alignItems: "center", justifyContent: "center", marginTop: 8 },
  title: { fontFamily: fonts.display, fontSize: 24, textAlign: "center" },
  desc: { fontFamily: fonts.regular, fontSize: 14, textAlign: "center", lineHeight: 21 },
  perks: { alignSelf: "stretch", gap: 12, marginVertical: 6 },
  perkRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  perkDot: { width: 24, height: 24, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  perkText: { fontFamily: fonts.medium, fontSize: 14 },
  cta: { alignSelf: "stretch", height: 52, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  ctaText: { fontFamily: fonts.semibold, fontSize: 16, color: "#FFFFFF" },
  secondary: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, alignSelf: "stretch", height: 50, borderRadius: 16, borderWidth: 1.5 },
  secondaryText: { fontFamily: fonts.semibold, fontSize: 15 },
});
