import { useState } from "react";
import { View, Text, Pressable, StyleSheet, TextInput, ActivityIndicator, Modal } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useMutation } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { TreePine, Plus, Users, ChevronRight, LogOut } from "lucide-react-native";
import { fonts, useTheme, brandGradient } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { useAuth } from "@/src/auth";
import { useTree } from "@/src/tree-context";
import { createTree } from "@/src/api";

export default function WelcomeScreen() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user, logout } = useAuth();
  const { refreshTrees, setActive } = useTree();
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");

  const createMut = useMutation({
    mutationFn: (n: string) => createTree(n),
    onSuccess: async (tree) => {
      await refreshTrees();
      await setActive(tree.id);
      setCreateOpen(false);
      setName("");
      router.replace("/(tabs)");
    },
  });

  return (
    <View style={[styles.root, { backgroundColor: colors.surface, paddingTop: insets.top + 24 }]}>
      <View style={styles.hero}>
        <LinearGradient colors={brandGradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.badge}>
          <TreePine size={42} color="#FFFFFF" />
        </LinearGradient>
        <Text style={[styles.title, { color: colors.onSurface }]}>{t("welcome_title")}</Text>
        <Text style={[styles.subtitle, { color: colors.muted }]}>{t("welcome_subtitle")}</Text>
      </View>

      <View style={styles.cards}>
        <Pressable
          testID="welcome-create"
          onPress={() => setCreateOpen(true)}
          style={[styles.card, { backgroundColor: colors.surfaceSecondary, borderColor: colors.border }]}
        >
          <View style={[styles.cardIcon, { backgroundColor: colors.brandTertiary }]}>
            <Plus size={24} color={colors.onBrandTertiary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={[styles.cardTitle, { color: colors.onSurface }]}>{t("create_tree_card_title")}</Text>
            <Text style={[styles.cardDesc, { color: colors.muted }]}>{t("create_tree_card_desc")}</Text>
          </View>
          <ChevronRight size={22} color={colors.muted} />
        </Pressable>

        <Pressable
          testID="welcome-join"
          onPress={() => router.push("/join")}
          style={[styles.card, { backgroundColor: colors.surfaceSecondary, borderColor: colors.border }]}
        >
          <View style={[styles.cardIcon, { backgroundColor: colors.brandTertiary }]}>
            <Users size={24} color={colors.onBrandTertiary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={[styles.cardTitle, { color: colors.onSurface }]}>{t("join_tree_card_title")}</Text>
            <Text style={[styles.cardDesc, { color: colors.muted }]}>{t("join_tree_card_desc")}</Text>
          </View>
          <ChevronRight size={22} color={colors.muted} />
        </Pressable>
      </View>

      <Pressable onPress={logout} style={styles.logout} hitSlop={10} testID="welcome-logout">
        <LogOut size={16} color={colors.muted} />
        <Text style={[styles.logoutText, { color: colors.muted }]}>{user?.email} · {t("logout")}</Text>
      </Pressable>

      <Modal visible={createOpen} transparent animationType="slide" onRequestClose={() => setCreateOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setCreateOpen(false)}>
          <Pressable style={[styles.sheet, { backgroundColor: colors.surfaceSecondary, paddingBottom: insets.bottom + 24 }]} onPress={() => {}}>
            <Text style={[styles.sheetTitle, { color: colors.onSurface }]}>{t("create_tree")}</Text>
            <TextInput
              testID="welcome-tree-name-input"
              value={name}
              onChangeText={setName}
              placeholder={t("tree_name_placeholder")}
              placeholderTextColor={colors.muted}
              style={[styles.input, { backgroundColor: colors.surfaceTertiary, color: colors.onSurface }]}
              autoFocus
            />
            <Pressable
              testID="welcome-submit-create"
              disabled={createMut.isPending || !name.trim()}
              onPress={() => createMut.mutate(name.trim())}
              style={{ opacity: createMut.isPending || !name.trim() ? 0.6 : 1 }}
            >
              <LinearGradient colors={brandGradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.submit}>
                {createMut.isPending ? (
                  <ActivityIndicator color="#FFFFFF" />
                ) : (
                  <Text style={styles.submitText}>{t("create")}</Text>
                )}
              </LinearGradient>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, paddingHorizontal: 24 },
  hero: { alignItems: "center", marginTop: 20, marginBottom: 36 },
  badge: { width: 92, height: 92, borderRadius: 999, alignItems: "center", justifyContent: "center", marginBottom: 20 },
  title: { fontFamily: fonts.display, fontSize: 30, textAlign: "center" },
  subtitle: { fontFamily: fonts.regular, fontSize: 15, textAlign: "center", lineHeight: 22, marginTop: 10, paddingHorizontal: 8 },
  cards: { gap: 14 },
  card: { flexDirection: "row", alignItems: "center", gap: 14, borderRadius: 20, borderWidth: 1.5, padding: 18 },
  cardIcon: { width: 50, height: 50, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  cardTitle: { fontFamily: fonts.semibold, fontSize: 16 },
  cardDesc: { fontFamily: fonts.regular, fontSize: 13, marginTop: 3, lineHeight: 18 },
  logout: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: "auto", marginBottom: 28, paddingVertical: 12 },
  logoutText: { fontFamily: fonts.medium, fontSize: 13 },
  modalBg: { flex: 1, backgroundColor: "rgba(31,42,68,0.5)", justifyContent: "flex-end" },
  sheet: { borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 24, gap: 16 },
  sheetTitle: { fontFamily: fonts.display, fontSize: 20 },
  input: { borderRadius: 14, paddingHorizontal: 16, paddingVertical: 14, fontFamily: fonts.regular, fontSize: 15 },
  submit: { height: 52, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  submitText: { fontFamily: fonts.semibold, fontSize: 16, color: "#FFFFFF" },
});
