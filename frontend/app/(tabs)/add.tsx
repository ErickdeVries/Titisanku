import { useMemo, useState, useEffect } from "react";
import { View, Text, Pressable, Modal, FlatList, TextInput } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getTree, fileUrl, Person } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { nodeColor } from "@/src/components/PersonNode";
import { GradientButton } from "@/src/components/GradientButton";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 20, paddingBottom: 12, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: fonts.bold, fontSize: 20, color: c.onSurface },
  body: { padding: 20, gap: 20 },
  label: { fontFamily: fonts.medium, fontSize: 13, color: c.muted, marginBottom: 8 },
  targetCard: { flexDirection: "row", alignItems: "center", gap: 14, backgroundColor: c.surfaceSecondary, borderRadius: 16, padding: 14 },
  avatar: { width: 48, height: 48, borderRadius: 999, alignItems: "center", justifyContent: "center", overflow: "hidden", borderWidth: 2 },
  avatarImg: { width: "100%", height: "100%" },
  targetName: { fontFamily: fonts.semibold, fontSize: 15, color: c.onSurface },
  changeBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  changeText: { fontFamily: fonts.medium, fontSize: 13, color: c.brandSecondary },
  dirGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  dirCard: { width: "47%", flexGrow: 1, backgroundColor: c.surfaceSecondary, borderRadius: 16, padding: 16, gap: 10, borderWidth: 2, borderColor: "transparent" },
  dirCardActive: { borderColor: c.brandPrimary, backgroundColor: c.brandTertiary },
  dirIcon: { width: 40, height: 40, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  dirText: { fontFamily: fonts.semibold, fontSize: 15, color: c.onSurface },
  noPerm: { fontFamily: fonts.regular, fontSize: 14, color: c.muted, textAlign: "center", padding: 40 },
  // modal
  modalBg: { flex: 1, backgroundColor: "rgba(15,23,42,0.4)", justifyContent: "flex-end" },
  sheet: { backgroundColor: c.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: "80%" },
  sheetHeader: { padding: 20, borderBottomWidth: 1, borderBottomColor: c.divider },
  searchBar: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: c.surfaceTertiary, borderRadius: 999, paddingHorizontal: 16, height: 46, marginTop: 12 },
  input: { flex: 1, fontFamily: fonts.regular, fontSize: 15, color: c.onSurface },
  row: { flexDirection: "row", alignItems: "center", gap: 14, paddingVertical: 12, paddingHorizontal: 20 },
}));

export default function AddScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const { user } = useAuth();
  const insets = useSafeAreaInsets();

  const { data } = useQuery({ queryKey: ["tree"], queryFn: getTree });
  const people = data?.people ?? [];

  const [targetId, setTargetId] = useState<string | null>(null);
  const [direction, setDirection] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    if (!targetId && data?.root_id) setTargetId(data.root_id);
  }, [data?.root_id, targetId]);

  const target = people.find((p) => p.id === targetId);
  const canEdit = (data?.role ?? user?.role) === "admin" || (data?.role ?? user?.role) === "editor";

  const filtered = useMemo(
    () => (q.trim() ? people.filter((p) => p.name.toLowerCase().includes(q.toLowerCase())) : people),
    [q, people],
  );

  const directions = [
    { key: "father", label: t("add_father"), icon: "arrow-up", color: colors.maleNode, dir: "father" },
    { key: "mother", label: t("add_mother"), icon: "arrow-up", color: colors.femaleNode, dir: "mother" },
    { key: "spouse", label: t("add_spouse"), icon: "heart", color: colors.brandPrimary, dir: "spouse" },
    { key: "older", label: t("add_older_sibling"), icon: "users", color: colors.brandSecondary, dir: "sibling", sib: "older" },
    { key: "younger", label: t("add_younger_sibling"), icon: "users", color: colors.brandSecondary, dir: "sibling", sib: "younger" },
    { key: "child", label: t("add_child"), icon: "arrow-down", color: colors.success, dir: "child" },
  ];

  const cont = () => {
    if (!target || !direction) return;
    const sel = directions.find((d) => d.key === direction);
    if (!sel) return;
    const sibQ = (sel as any).sib ? `&sib=${(sel as any).sib}` : "";
    router.push(`/add-relative?focus_id=${target.id}&direction=${sel.dir}&focus_name=${encodeURIComponent(target.name)}${sibQ}`);
    setDirection(null);
  };

  if (!canEdit) {
    return (
      <View style={styles.root}>
        <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
          <Text style={styles.title}>{t("add")}</Text>
        </View>
        <Text style={styles.noPerm}>{t("no_permission")}</Text>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Text style={styles.title}>{t("add")}</Text>
      </View>
      <View style={styles.body}>
        <View>
          <Text style={styles.label}>{t("add_relative_to")}</Text>
          <View style={styles.targetCard}>
            <View style={[styles.avatar, { borderColor: target ? nodeColor(target, colors) : colors.border }]}>
              {target && fileUrl(target.photo_url) ? (
                <Image source={{ uri: fileUrl(target.photo_url)! }} style={styles.avatarImg} contentFit="cover" />
              ) : (
                <Feather name="user" size={22} color={colors.muted} />
              )}
            </View>
            <Text style={[styles.targetName, { flex: 1 }]}>{target?.name ?? "-"}</Text>
            <Pressable style={styles.changeBtn} onPress={() => setPickerOpen(true)} testID="change-target">
              <Feather name="repeat" size={15} color={colors.brandSecondary} />
              <Text style={styles.changeText}>{t("select_person")}</Text>
            </Pressable>
          </View>
        </View>

        <View>
          <Text style={styles.label}>{t("relation")}</Text>
          <View style={styles.dirGrid}>
            {directions.map((d) => (
              <Pressable
                key={d.key}
                style={[styles.dirCard, direction === d.key && styles.dirCardActive]}
                onPress={() => setDirection(d.key)}
                testID={`dir-${d.key}`}
              >
                <View style={[styles.dirIcon, { backgroundColor: d.color }]}>
                  <Feather name={d.icon as any} size={20} color="#FFFFFF" />
                </View>
                <Text style={styles.dirText}>{d.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <GradientButton testID="add-continue" title={t("save")} icon="arrow-right" disabled={!target || !direction} onPress={cont} />
      </View>

      <Modal visible={pickerOpen} transparent animationType="slide" onRequestClose={() => setPickerOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setPickerOpen(false)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <View style={styles.sheetHeader}>
              <Text style={styles.title}>{t("select_person")}</Text>
              <View style={styles.searchBar}>
                <Feather name="search" size={18} color={colors.muted} />
                <TextInput style={styles.input} placeholder={t("search_placeholder")} placeholderTextColor={colors.muted} value={q} onChangeText={setQ} />
              </View>
            </View>
            <FlatList
              data={filtered}
              keyExtractor={(p) => p.id}
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={{ paddingBottom: insets.bottom + 20 }}
              renderItem={({ item }) => (
                <Pressable
                  style={styles.row}
                  onPress={() => {
                    setTargetId(item.id);
                    setPickerOpen(false);
                    setQ("");
                  }}
                  testID={`pick-${item.id}`}
                >
                  <View style={[styles.avatar, { borderColor: nodeColor(item, colors) }]}>
                    {fileUrl(item.photo_url) ? (
                      <Image source={{ uri: fileUrl(item.photo_url)! }} style={styles.avatarImg} contentFit="cover" />
                    ) : (
                      <Feather name="user" size={20} color={nodeColor(item, colors)} />
                    )}
                  </View>
                  <Text style={styles.targetName}>{item.name}</Text>
                </Pressable>
              )}
            />
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}
