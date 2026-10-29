import { useMemo, useState } from "react";
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput, ActivityIndicator, Modal, FlatList, Alert,
} from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useGoBack } from "@/src/hooks/useGoBack";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useMutation } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { ArrowLeft, Check, GitBranch, User, Search } from "lucide-react-native";
import { fonts, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { useTree } from "@/src/tree-context";
import { getTree, claimBranch, fileUrl } from "@/src/api";
import { nodeColor } from "@/src/components/PersonNode";

type Scope = "descendants" | "children" | "whole";

export default function ClaimBranchScreen() {
  const { colors, gradient } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const goBack = useGoBack("/");
  const insets = useSafeAreaInsets();
  const { activeTreeId, refreshTrees, setActive } = useTree();
  const params = useLocalSearchParams<{ person_id?: string; person_name?: string }>();

  const { data } = useQuery({ queryKey: ["tree"], queryFn: getTree });
  const people = data?.people ?? [];

  const [personId, setPersonId] = useState<string | null>(params.person_id ?? null);
  const [scope, setScope] = useState<Scope>("descendants");
  const [name, setName] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [q, setQ] = useState("");

  const person = people.find((p) => p.id === personId);
  const personName = person?.name ?? params.person_name ?? "";

  const filtered = useMemo(
    () => (q.trim() ? people.filter((p) => p.name.toLowerCase().includes(q.toLowerCase())) : people),
    [q, people],
  );

  const scopes: { key: Scope; label: string; desc: string }[] = [
    { key: "descendants", label: t("scope_descendants"), desc: t("scope_descendants_desc") },
    { key: "children", label: t("scope_children"), desc: t("scope_children_desc") },
    { key: "whole", label: t("scope_whole"), desc: t("scope_whole_desc") },
  ];

  const claimMut = useMutation({
    mutationFn: () => claimBranch(activeTreeId!, personId!, scope, name.trim() || undefined),
    onSuccess: async (tree) => {
      await refreshTrees();
      await setActive(tree.id);
      Alert.alert(t("claim_branch"), t("claim_done").replace("{n}", String(tree.copied)));
      router.replace("/(tabs)");
    },
    onError: () => Alert.alert(t("error_generic")),
  });

  return (
    <View style={[styles.root, { backgroundColor: colors.surface }]}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={() => goBack()} hitSlop={10}>
          <ArrowLeft size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={[styles.title, { color: colors.onSurface }]}>{t("claim_branch")}</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }} keyboardShouldPersistTaps="handled">
        <View style={styles.heroRow}>
          <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.heroBadge}>
            <GitBranch size={22} color="#FFFFFF" />
          </LinearGradient>
          <Text style={[styles.heroDesc, { color: colors.muted }]}>{t("claim_branch_desc")}</Text>
        </View>

        {/* Person selector */}
        <View>
          <Text style={[styles.label, { color: colors.muted }]}>{t("claim_branch_from")}</Text>
          <Pressable
            testID="claim-select-person"
            onPress={() => setPickerOpen(true)}
            style={[styles.personCard, { backgroundColor: colors.surfaceSecondary, borderColor: colors.border }]}
          >
            <View style={[styles.avatar, { borderColor: person ? nodeColor(person, colors) : colors.border }]}>
              {person && fileUrl(person.photo_url) ? (
                <Image source={{ uri: fileUrl(person.photo_url)! }} style={styles.avatarImg} contentFit="cover" />
              ) : (
                <User size={22} color={colors.muted} />
              )}
            </View>
            <Text style={[styles.personName, { color: personName ? colors.onSurface : colors.muted, flex: 1 }]}>
              {personName || t("select_branch_person")}
            </Text>
            <Search size={18} color={colors.brandSecondary} />
          </Pressable>
        </View>

        {/* Scope toggle */}
        <View>
          <Text style={[styles.label, { color: colors.muted }]}>{t("claim_scope_title")}</Text>
          <View style={{ gap: 10 }}>
            {scopes.map((s) => {
              const active = scope === s.key;
              return (
                <Pressable
                  key={s.key}
                  testID={`scope-${s.key}`}
                  onPress={() => setScope(s.key)}
                  style={[styles.scopeCard, { backgroundColor: colors.surfaceSecondary, borderColor: active ? colors.brandPrimary : colors.border }]}
                >
                  <View style={[styles.radio, { borderColor: active ? colors.brandPrimary : colors.borderStrong }]}>
                    {active ? <View style={[styles.radioDot, { backgroundColor: colors.brandPrimary }]} /> : null}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.scopeLabel, { color: colors.onSurface }]}>{s.label}</Text>
                    <Text style={[styles.scopeDesc, { color: colors.muted }]}>{s.desc}</Text>
                  </View>
                </Pressable>
              );
            })}
          </View>
        </View>

        {/* Tree name */}
        <View>
          <Text style={[styles.label, { color: colors.muted }]}>{t("new_tree_name_optional")}</Text>
          <TextInput
            testID="claim-name-input"
            value={name}
            onChangeText={setName}
            placeholder={t("tree_name_placeholder")}
            placeholderTextColor={colors.muted}
            style={[styles.input, { backgroundColor: colors.surfaceSecondary, color: colors.onSurface, borderColor: colors.border }]}
          />
        </View>

        <Text style={[styles.note, { color: colors.muted }]}>{t("claim_note")}</Text>

        <Pressable
          testID="claim-submit"
          onPress={() => claimMut.mutate()}
          disabled={!personId || claimMut.isPending}
          style={{ opacity: !personId || claimMut.isPending ? 0.6 : 1 }}
        >
          <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.cta}>
            {claimMut.isPending ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <>
                <Check size={18} color="#FFFFFF" />
                <Text style={styles.ctaText}>{t("claim_now")}</Text>
              </>
            )}
          </LinearGradient>
        </Pressable>
      </ScrollView>

      <Modal visible={pickerOpen} transparent animationType="slide" onRequestClose={() => setPickerOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setPickerOpen(false)}>
          <Pressable style={[styles.sheet, { backgroundColor: colors.surface }]} onPress={() => {}}>
            <View style={[styles.sheetHeader, { borderBottomColor: colors.divider }]}>
              <Text style={[styles.title, { color: colors.onSurface }]}>{t("select_branch_person")}</Text>
              <View style={[styles.searchBar, { backgroundColor: colors.surfaceTertiary }]}>
                <Search size={18} color={colors.muted} />
                <TextInput
                  style={[styles.searchInput, { color: colors.onSurface }]}
                  placeholder={t("search_placeholder")}
                  placeholderTextColor={colors.muted}
                  value={q}
                  onChangeText={setQ}
                />
              </View>
            </View>
            <FlatList
              data={filtered}
              keyExtractor={(p) => p.id}
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={{ paddingBottom: insets.bottom + 20 }}
              renderItem={({ item }) => (
                <Pressable
                  style={styles.pickRow}
                  onPress={() => { setPersonId(item.id); setPickerOpen(false); setQ(""); }}
                  testID={`claim-pick-${item.id}`}
                >
                  <View style={[styles.avatar, { borderColor: nodeColor(item, colors) }]}>
                    {fileUrl(item.photo_url) ? (
                      <Image source={{ uri: fileUrl(item.photo_url)! }} style={styles.avatarImg} contentFit="cover" />
                    ) : (
                      <User size={20} color={nodeColor(item, colors)} />
                    )}
                  </View>
                  <Text style={[styles.personName, { color: colors.onSurface }]}>{item.name}</Text>
                </Pressable>
              )}
            />
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20, paddingBottom: 12 },
  title: { fontFamily: fonts.display, fontSize: 22 },
  heroRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  heroBadge: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  heroDesc: { fontFamily: fonts.regular, fontSize: 13, lineHeight: 19, flex: 1 },
  label: { fontFamily: fonts.medium, fontSize: 13, marginBottom: 8 },
  personCard: { flexDirection: "row", alignItems: "center", gap: 12, borderRadius: 16, borderWidth: 1, padding: 12 },
  avatar: { width: 46, height: 46, borderRadius: 999, alignItems: "center", justifyContent: "center", overflow: "hidden", borderWidth: 2 },
  avatarImg: { width: "100%", height: "100%" },
  personName: { fontFamily: fonts.semibold, fontSize: 15 },
  scopeCard: { flexDirection: "row", alignItems: "center", gap: 12, borderRadius: 16, borderWidth: 1.5, padding: 14 },
  radio: { width: 22, height: 22, borderRadius: 999, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  radioDot: { width: 11, height: 11, borderRadius: 999 },
  scopeLabel: { fontFamily: fonts.semibold, fontSize: 15 },
  scopeDesc: { fontFamily: fonts.regular, fontSize: 12, marginTop: 2 },
  input: { borderRadius: 14, borderWidth: 1, paddingHorizontal: 16, paddingVertical: 14, fontFamily: fonts.regular, fontSize: 15 },
  note: { fontFamily: fonts.regular, fontSize: 12, lineHeight: 18 },
  cta: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 54, borderRadius: 16 },
  ctaText: { fontFamily: fonts.semibold, fontSize: 16, color: "#FFFFFF" },
  modalBg: { flex: 1, backgroundColor: "rgba(15,23,42,0.4)", justifyContent: "flex-end" },
  sheet: { borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: "80%" },
  sheetHeader: { padding: 20, borderBottomWidth: 1 },
  searchBar: { flexDirection: "row", alignItems: "center", gap: 8, borderRadius: 999, paddingHorizontal: 16, height: 46, marginTop: 12 },
  searchInput: { flex: 1, fontFamily: fonts.regular, fontSize: 15 },
  pickRow: { flexDirection: "row", alignItems: "center", gap: 14, paddingVertical: 12, paddingHorizontal: 20 },
});
