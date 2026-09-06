import { useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, TextInput, ActivityIndicator, Modal } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useMutation } from "@tanstack/react-query";
import { X, Plus, Check, Crown, Users, UserPlus, Trash2 } from "lucide-react-native";
import { fonts, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { useTree } from "@/src/tree-context";
import { useAuth } from "@/src/auth";
import { createTree, deleteTree } from "@/src/api";

export default function TreesScreen() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { trees, activeTreeId, setActive, refreshTrees } = useTree();
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [pendingDelete, setPendingDelete] = useState<{ id: string; name: string } | null>(null);

  const createMut = useMutation({
    mutationFn: (n: string) => createTree(n),
    onSuccess: async (tree) => {
      await refreshTrees();
      await setActive(tree.id);
      setCreateOpen(false);
      setName("");
      router.back();
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteTree(id),
    onSuccess: async (_r, id) => {
      setPendingDelete(null);
      const list = await refreshTrees();
      if (id === activeTreeId) {
        if (list.length > 0) await setActive(list[0].id);
        else router.replace("/welcome");
      }
    },
    onError: () => setPendingDelete(null),
  });

  const pick = async (id: string) => {
    await setActive(id);
    router.back();
  };

  return (
    <View style={[styles.root, { backgroundColor: colors.surface, paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: colors.onSurface }]}>{t("my_trees")}</Text>
        <Pressable onPress={() => router.back()} hitSlop={10}>
          <X size={24} color={colors.muted} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
        {trees.map((tree) => {
          const active = tree.id === activeTreeId;
          const isOwner = tree.owner_id === user?.user_id;
          return (
            <View
              key={tree.id}
              style={[styles.card, { backgroundColor: colors.surfaceSecondary, borderColor: active ? colors.brandPrimary : colors.border }]}
            >
              <Pressable testID={`tree-${tree.id}`} onPress={() => pick(tree.id)} style={styles.cardMain}>
                <View style={[styles.avatar, { backgroundColor: colors.brandTertiary }]}>
                  <Users size={22} color={colors.onBrandTertiary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.cardName, { color: colors.onSurface }]} numberOfLines={1}>{tree.name}</Text>
                  <View style={styles.metaRow}>
                    <View style={[styles.pill, { backgroundColor: tree.plan === "pro" ? colors.brandSecondary : colors.brandTertiary }]}>
                      {tree.plan === "pro" ? <Crown size={11} color={colors.onBrandSecondary} /> : null}
                      <Text style={[styles.pillText, { color: tree.plan === "pro" ? colors.onBrandSecondary : colors.onBrandTertiary }]}>
                        {tree.plan === "pro" ? "PRO" : "GRATIS"}
                      </Text>
                    </View>
                    <Text style={[styles.meta, { color: colors.muted }]}>
                      {tree.person_count}{tree.limit ? `/${tree.limit}` : ""} · {tree.role}
                    </Text>
                  </View>
                </View>
                {active ? <Check size={22} color={colors.brandPrimary} /> : null}
              </Pressable>
              {isOwner ? (
                <Pressable
                  testID={`delete-tree-${tree.id}`}
                  onPress={() => setPendingDelete({ id: tree.id, name: tree.name })}
                  hitSlop={8}
                  style={styles.trashBtn}
                >
                  <Trash2 size={18} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          );
        })}

        <Pressable
          testID="create-tree-button"
          onPress={() => setCreateOpen(true)}
          style={[styles.createBtn, { borderColor: colors.brandPrimary }]}
        >
          <Plus size={20} color={colors.brandPrimary} />
          <Text style={[styles.createText, { color: colors.brandPrimary }]}>{t("create_tree")}</Text>
        </Pressable>

        <Pressable
          testID="join-tree-button"
          onPress={() => { router.back(); router.push("/join"); }}
          style={[styles.createBtn, { borderColor: colors.brandSecondary }]}
        >
          <UserPlus size={20} color={colors.brandSecondary} />
          <Text style={[styles.createText, { color: colors.brandSecondary }]}>{t("join_tree")}</Text>
        </Pressable>
      </ScrollView>

      <Modal visible={createOpen} transparent animationType="slide" onRequestClose={() => setCreateOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setCreateOpen(false)}>
          <Pressable style={[styles.sheet, { backgroundColor: colors.surfaceSecondary, paddingBottom: insets.bottom + 24 }]} onPress={() => {}}>
            <Text style={[styles.sheetTitle, { color: colors.onSurface }]}>{t("create_tree")}</Text>
            <TextInput
              testID="tree-name-input"
              value={name}
              onChangeText={setName}
              placeholder={t("tree_name_placeholder")}
              placeholderTextColor={colors.muted}
              style={[styles.input, { backgroundColor: colors.surfaceTertiary, color: colors.onSurface }]}
            />
            <Pressable
              testID="submit-create-tree"
              disabled={createMut.isPending || !name.trim()}
              onPress={() => createMut.mutate(name.trim())}
              style={[styles.submit, { backgroundColor: colors.brandPrimary, opacity: createMut.isPending || !name.trim() ? 0.6 : 1 }]}
            >
              {createMut.isPending ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <Text style={[styles.submitText, { color: colors.onBrandPrimary }]}>{t("create")}</Text>
              )}
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
      <Modal visible={!!pendingDelete} transparent animationType="fade" onRequestClose={() => setPendingDelete(null)}>
        <Pressable style={styles.modalBg} onPress={() => setPendingDelete(null)}>
          <Pressable style={[styles.confirmSheet, { backgroundColor: colors.surfaceSecondary }]} onPress={() => {}}>
            <View style={[styles.confirmIcon, { backgroundColor: colors.surfaceTertiary }]}>
              <Trash2 size={26} color={colors.error} />
            </View>
            <Text style={[styles.confirmTitle, { color: colors.onSurface }]}>{t("delete_tree")}</Text>
            <Text style={[styles.confirmMsg, { color: colors.muted }]}>
              {t("delete_tree_confirm").replace("{name}", pendingDelete?.name ?? "")}
            </Text>
            <View style={styles.confirmRow}>
              <Pressable
                testID="cancel-delete-tree"
                style={[styles.confirmBtn, { backgroundColor: colors.surfaceTertiary }]}
                onPress={() => setPendingDelete(null)}
              >
                <Text style={[styles.confirmBtnText, { color: colors.onSurface }]}>{t("cancel")}</Text>
              </Pressable>
              <Pressable
                testID="confirm-delete-tree"
                style={[styles.confirmBtn, { backgroundColor: colors.error, opacity: deleteMut.isPending ? 0.6 : 1 }]}
                disabled={deleteMut.isPending}
                onPress={() => pendingDelete && deleteMut.mutate(pendingDelete.id)}
              >
                {deleteMut.isPending ? (
                  <ActivityIndicator color={colors.onError} />
                ) : (
                  <Text style={[styles.confirmBtnText, { color: colors.onError }]}>{t("delete")}</Text>
                )}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20, paddingBottom: 12 },
  title: { fontFamily: fonts.display, fontSize: 24 },
  card: { flexDirection: "row", alignItems: "center", gap: 6, borderRadius: 18, borderWidth: 1.5, paddingRight: 8 },
  cardMain: { flex: 1, flexDirection: "row", alignItems: "center", gap: 14, padding: 14 },
  trashBtn: { width: 40, height: 40, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  avatar: { width: 46, height: 46, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  cardName: { fontFamily: fonts.semibold, fontSize: 16 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 4 },
  pill: { flexDirection: "row", alignItems: "center", gap: 3, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999 },
  pillText: { fontFamily: fonts.bold, fontSize: 10, letterSpacing: 0.5 },
  meta: { fontFamily: fonts.regular, fontSize: 12 },
  createBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 16, borderWidth: 1.5, borderStyle: "dashed", paddingVertical: 16, marginTop: 4 },
  createText: { fontFamily: fonts.semibold, fontSize: 15 },
  modalBg: { flex: 1, backgroundColor: "rgba(31,42,68,0.5)", justifyContent: "flex-end" },
  sheet: { borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 24, gap: 16 },
  sheetTitle: { fontFamily: fonts.display, fontSize: 20 },
  input: { borderRadius: 14, paddingHorizontal: 16, paddingVertical: 14, fontFamily: fonts.regular, fontSize: 15 },
  submit: { height: 52, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  submitText: { fontFamily: fonts.semibold, fontSize: 16 },
  confirmSheet: { margin: 24, borderRadius: 24, padding: 24, alignItems: "center", gap: 10 },
  confirmIcon: { width: 60, height: 60, borderRadius: 999, alignItems: "center", justifyContent: "center", marginBottom: 4 },
  confirmTitle: { fontFamily: fonts.display, fontSize: 20 },
  confirmMsg: { fontFamily: fonts.regular, fontSize: 14, textAlign: "center", lineHeight: 20 },
  confirmRow: { flexDirection: "row", gap: 12, marginTop: 12, alignSelf: "stretch" },
  confirmBtn: { flex: 1, height: 48, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  confirmBtnText: { fontFamily: fonts.semibold, fontSize: 15 },
});
