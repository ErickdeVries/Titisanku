import { useState } from "react";
import { View, Text, Modal, Pressable, StyleSheet, ActivityIndicator } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Crown, X, Check } from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { fonts, useTheme, brandGradient } from "@/src/theme";
import { upgradeTree } from "@/src/api";
import { useTree } from "@/src/tree-context";

const PERKS = [
  "Anggota tak terbatas per pohon",
  "PDF tanpa watermark",
  "Backup ke Google Drive",
  "Dukungan prioritas",
];

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
  const { activeTree, activeTreeId, refreshTrees } = useTree();
  const [loading, setLoading] = useState(false);
  const isAdmin = activeTree?.role === "admin";

  const doUpgrade = async () => {
    if (!activeTreeId) return;
    setLoading(true);
    try {
      await upgradeTree(activeTreeId);
      await refreshTrees();
      onClose();
    } catch (e) {
      console.log("upgrade error", e);
    } finally {
      setLoading(false);
    }
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
          <Text style={[styles.title, { color: colors.onSurface }]}>Upgrade ke Pro</Text>
          <Text style={[styles.desc, { color: colors.muted }]}>
            {limit
              ? `Pohon gratis dibatasi ${limit} orang. Buka kunci untuk menambah anggota tanpa batas.`
              : "Buka semua fitur premium untuk pohon keluarga Anda."}
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
          {isAdmin ? (
            <Pressable onPress={doUpgrade} disabled={loading} style={{ opacity: loading ? 0.7 : 1 }}>
              <LinearGradient colors={brandGradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.cta}>
                {loading ? (
                  <ActivityIndicator color="#FFFFFF" />
                ) : (
                  <Text style={styles.ctaText}>Upgrade Sekarang</Text>
                )}
              </LinearGradient>
            </Pressable>
          ) : (
            <View style={[styles.notice, { backgroundColor: colors.surfaceTertiary }]}>
              <Text style={[styles.noticeText, { color: colors.onSurfaceTertiary }]}>
                Hanya admin pohon yang dapat melakukan upgrade. Hubungi admin keluarga Anda.
              </Text>
            </View>
          )}
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
  title: { fontFamily: fonts.display, fontSize: 24 },
  desc: { fontFamily: fonts.regular, fontSize: 14, textAlign: "center", lineHeight: 20 },
  perks: { alignSelf: "stretch", gap: 12, marginVertical: 6 },
  perkRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  perkDot: { width: 24, height: 24, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  perkText: { fontFamily: fonts.medium, fontSize: 14 },
  cta: { alignSelf: "stretch", height: 52, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  ctaText: { fontFamily: fonts.semibold, fontSize: 16, color: "#FFFFFF" },
  notice: { alignSelf: "stretch", borderRadius: 14, padding: 14 },
  noticeText: { fontFamily: fonts.regular, fontSize: 13, textAlign: "center" },
});
