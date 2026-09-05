import { useMemo, useState } from "react";
import { View, Text, Pressable, ActivityIndicator, TextInput, Modal, Alert } from "react-native";
import { Image } from "expo-image";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, { useSharedValue, useAnimatedStyle } from "react-native-reanimated";
import * as ImagePicker from "expo-image-picker";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getPerson, updatePerson, deletePerson, fileUrl, getTree, listPersonNotes, addPersonNote, addPersonFile, deleteNote, deleteRelation } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { nodeColor } from "@/src/components/PersonNode";
import { PersonForm, PersonFormValue } from "@/src/components/PersonForm";
import { GradientButton } from "@/src/components/GradientButton";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  iconBtn: { width: 36, height: 36, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontFamily: fonts.semibold, fontSize: 16, color: c.onSurface },
  hero: { alignItems: "center", paddingVertical: 24, gap: 8 },
  avatar: { width: 120, height: 120, borderRadius: 999, borderWidth: 4, overflow: "hidden", alignItems: "center", justifyContent: "center", backgroundColor: c.surfaceTertiary },
  avatarImg: { width: "100%", height: "100%" },
  name: { fontFamily: fonts.bold, fontSize: 22, color: c.onSurface },
  roleTag: { flexDirection: "row", gap: 6, alignItems: "center", backgroundColor: c.brandTertiary, paddingHorizontal: 12, paddingVertical: 4, borderRadius: 999 },
  roleTagText: { fontFamily: fonts.medium, fontSize: 12, color: c.onBrandTertiary },
  quickRow: { flexDirection: "row", justifyContent: "center", gap: 10, paddingHorizontal: 20, marginBottom: 8, flexWrap: "wrap" },
  quickBtn: { alignItems: "center", gap: 6, width: 72 },
  quickIcon: { width: 48, height: 48, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  quickLabel: { fontFamily: fonts.medium, fontSize: 12, color: c.onSurfaceSecondary },
  infoCard: { marginHorizontal: 20, marginTop: 12, backgroundColor: c.surfaceSecondary, borderRadius: 16, overflow: "hidden" },
  infoRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14 },
  infoLabel: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  infoValue: { fontFamily: fonts.medium, fontSize: 15, color: c.onSurface },
  divider: { height: 1, backgroundColor: c.divider, marginLeft: 14 },
  marriageTitle: { fontFamily: fonts.semibold, fontSize: 13, color: c.muted, textTransform: "uppercase", letterSpacing: 0.5, marginHorizontal: 20, marginTop: 20, marginBottom: 8 },
  spouseSub: { fontFamily: fonts.regular, fontSize: 12, color: c.muted, marginTop: 2 },
  divorceBadge: { backgroundColor: c.error, paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999 },
  divorceBadgeText: { fontFamily: fonts.semibold, fontSize: 11, color: c.onError },
  actions: { padding: 20, gap: 12 },
  deleteBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, padding: 16, borderRadius: 999, backgroundColor: c.surfaceTertiary },
  deleteText: { fontFamily: fonts.semibold, fontSize: 15, color: c.error },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  tabs: { flexDirection: "row", marginHorizontal: 20, marginTop: 8, backgroundColor: c.surfaceTertiary, borderRadius: 12, padding: 4, gap: 4 },
  tab: { flex: 1, height: 38, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  tabActive: { backgroundColor: c.surface, shadowColor: "#0F172A", shadowOpacity: 0.06, shadowRadius: 4, elevation: 2 },
  tabText: { fontFamily: fonts.medium, fontSize: 13, color: c.muted },
  tabTextActive: { color: c.onSurface },
  noteInputRow: { marginHorizontal: 20, marginTop: 16, gap: 10 },
  noteInput: { backgroundColor: c.surfaceTertiary, borderRadius: 12, padding: 14, minHeight: 80, textAlignVertical: "top", fontFamily: fonts.regular, fontSize: 15, color: c.onSurface },
  noteCard: { marginHorizontal: 20, marginTop: 12, backgroundColor: c.surfaceSecondary, borderRadius: 14, padding: 14, gap: 4 },
  noteHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  noteMeta: { fontFamily: fonts.semibold, fontSize: 13, color: c.brandSecondary },
  noteText: { fontFamily: fonts.regular, fontSize: 14, color: c.onSurface, lineHeight: 20 },
  emptyTab: { alignItems: "center", padding: 40, gap: 8 },
  emptyTabText: { fontFamily: fonts.regular, fontSize: 14, color: c.muted },
  fileCard: { marginHorizontal: 20, marginTop: 12, backgroundColor: c.surfaceSecondary, borderRadius: 14, overflow: "hidden" },
  fileImg: { width: "100%", height: 180, backgroundColor: c.surfaceTertiary },
  fileMetaRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10, padding: 12 },
  fileMeta: { flex: 1, fontFamily: fonts.medium, fontSize: 13, color: c.onSurfaceSecondary },
  viewerBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.95)", alignItems: "center", justifyContent: "center" },
  viewerImg: { width: "100%", height: "80%" },
  viewerClose: { position: "absolute", top: 50, right: 20, width: 40, height: 40, borderRadius: 999, backgroundColor: "rgba(255,255,255,0.2)", alignItems: "center", justifyContent: "center" },
  confirmBg: { flex: 1, backgroundColor: "rgba(15,23,42,0.5)", alignItems: "center", justifyContent: "center", padding: 30 },
  confirmCard: { backgroundColor: c.surface, borderRadius: 20, padding: 24, gap: 16, width: "100%" },
  confirmTitle: { fontFamily: fonts.semibold, fontSize: 17, color: c.onSurface, textAlign: "center", lineHeight: 24 },
  confirmRow: { flexDirection: "row", gap: 12 },
}));

function InfoRow({ icon, label, value }: { icon: string; label: string; value?: string | null }) {
  const styles = useStyles();
  const { colors } = useTheme();
  if (!value) return null;
  return (
    <View style={styles.infoRow}>
      <Feather name={icon as any} size={18} color={colors.muted} />
      <View>
        <Text style={styles.infoLabel}>{label}</Text>
        <Text style={styles.infoValue}>{value}</Text>
      </View>
    </View>
  );
}

export default function PersonDetail() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { user } = useAuth();
  const { id } = useLocalSearchParams<{ id: string }>();

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [activeTab, setActiveTab] = useState<"data" | "notes" | "files">("data");
  const [noteText, setNoteText] = useState("");
  const [noteBusy, setNoteBusy] = useState(false);
  const [fileBusy, setFileBusy] = useState(false);
  const [viewerUri, setViewerUri] = useState<string | null>(null);
  const [deathConfirm, setDeathConfirm] = useState(false);
  const [lastSaved, setLastSaved] = useState<any>(null);
  const zScale = useSharedValue(1);
  const zSaved = useSharedValue(1);

  const { data: person, isLoading } = useQuery({ queryKey: ["person", id], queryFn: () => getPerson(id) });
  const { data: tree } = useQuery({ queryKey: ["tree"], queryFn: getTree });
  const { data: notes } = useQuery({ queryKey: ["notes", id], queryFn: () => listPersonNotes(id) });

  const textNotes = (notes ?? []).filter((n: any) => n.note_text && (!n.attachments || n.attachments.length === 0));
  const fileNotes = (notes ?? []).filter((n: any) => n.attachments && n.attachments.length > 0);

  const submitNote = async () => {
    if (!noteText.trim()) return;
    setNoteBusy(true);
    try {
      await addPersonNote(id, noteText.trim());
      setNoteText("");
      await qc.invalidateQueries({ queryKey: ["notes", id] });
      await qc.invalidateQueries({ queryKey: ["tree"] });
    } catch (e) {
      console.log("note error", e);
    } finally {
      setNoteBusy(false);
    }
  };

  const submitFile = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.6 });
    if (res.canceled || !res.assets?.length) return;
    setFileBusy(true);
    try {
      await addPersonFile(id, res.assets[0].uri);
      await qc.invalidateQueries({ queryKey: ["notes", id] });
      await qc.invalidateQueries({ queryKey: ["tree"] });
    } catch (e) {
      console.log("file error", e);
    } finally {
      setFileBusy(false);
    }
  };

  const fmtDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString();
    } catch {
      return iso;
    }
  };

  const spouses = useMemo(() => {
    if (!tree) return [];
    const rels = tree.relations.filter(
      (r) => (r.relation_type === "spouse" || r.relation_type === "divorced") && (r.person_id === id || r.related_person_id === id),
    );
    return rels.map((r) => {
      const pid = r.person_id === id ? r.related_person_id : r.person_id;
      const partner = tree.people.find((p) => p.id === pid);
      return {
        id: r.id,
        name: partner?.name ?? "?",
        marriage_date: r.marriage_date,
        divorce_date: r.divorce_date,
        divorced: r.relation_type === "divorced",
      };
    });
  }, [tree, id]);

  const isAdmin = (tree?.role ?? user?.role) === "admin";
  const canEdit = (tree?.role ?? user?.role) === "admin" || (tree?.role ?? user?.role) === "editor";

  const relatives = useMemo(() => {
    if (!tree) return [] as { key: string; label: string; icon: string; person: any }[];
    const byId = new Map(tree.people.map((p) => [p.id, p] as const));
    const PAR = ["parent", "adopted_child"];
    const parentIds = tree.relations
      .filter((r) => r.related_person_id === id && PAR.includes(r.relation_type))
      .map((r) => r.person_id);
    const parentRelId = (pid: string) =>
      tree.relations.find((r) => r.related_person_id === id && r.person_id === pid && PAR.includes(r.relation_type))?.id;
    const parents = parentIds.map((pid) => byId.get(pid)).filter(Boolean) as any[];
    const father = parents.find((p) => p.gender === "male");
    const mother = parents.find((p) => p.gender === "female");
    const gp: any[] = [];
    parentIds.forEach((pid) => {
      tree.relations
        .filter((r) => r.related_person_id === pid && PAR.includes(r.relation_type))
        .forEach((r) => { const g = byId.get(r.person_id); if (g) gp.push(g); });
    });
    const sibSet = new Set<string>();
    const explicitSibRel = new Map<string, string>();
    if (parentIds.length) {
      parentIds.forEach((pid) =>
        tree.relations
          .filter((r) => r.person_id === pid && PAR.includes(r.relation_type))
          .forEach((r) => { if (r.related_person_id !== id) sibSet.add(r.related_person_id); }),
      );
    } else {
      tree.relations
        .filter((r) => r.relation_type === "sibling" && (r.person_id === id || r.related_person_id === id))
        .forEach((r) => {
          const sid = r.person_id === id ? r.related_person_id : r.person_id;
          sibSet.add(sid);
          explicitSibRel.set(sid, r.id);
        });
    }
    const siblings = [...sibSet].map((sid) => byId.get(sid)).filter(Boolean) as any[];
    const childRelId = (cid: string) =>
      tree.relations.find((r) => r.person_id === id && r.related_person_id === cid && PAR.includes(r.relation_type))?.id;
    const children = tree.relations
      .filter((r) => r.person_id === id && PAR.includes(r.relation_type))
      .map((r) => byId.get(r.related_person_id))
      .filter(Boolean) as any[];
    const rows: { key: string; label: string; icon: string; person: any; relId?: string }[] = [];
    if (father) rows.push({ key: "ayah", label: "Ayah", icon: "arrow-up", person: father, relId: parentRelId(father.id) });
    if (mother) rows.push({ key: "ibu", label: "Ibu", icon: "arrow-up", person: mother, relId: parentRelId(mother.id) });
    gp.filter((g) => g.gender === "male").forEach((g, i) => rows.push({ key: `kakek${i}`, label: "Kakek", icon: "chevrons-up", person: g }));
    gp.filter((g) => g.gender === "female").forEach((g, i) => rows.push({ key: `nenek${i}`, label: "Nenek", icon: "chevrons-up", person: g }));
    siblings.forEach((s, i) => rows.push({ key: `sib${i}`, label: t("siblings_label"), icon: "users", person: s, relId: explicitSibRel.get(s.id) }));
    children.forEach((ch, i) => rows.push({ key: `anak${i}`, label: t("children_label"), icon: "arrow-down", person: ch, relId: childRelId(ch.id) }));
    return rows;
  }, [tree, id, t]);

  const delRel = (relId: string, name: string) => {
    Alert.alert("Hapus Relasi", `Hapus hubungan dengan ${name}? Orang tetap ada di pohon.`, [
      { text: t("cancel"), style: "cancel" },
      {
        text: t("delete"),
        style: "destructive",
        onPress: async () => {
          try {
            await deleteRelation(relId);
            await qc.invalidateQueries({ queryKey: ["tree"] });
            await qc.invalidateQueries({ queryKey: ["person", id] });
          } catch (e) {
            console.log("delete relation error", e);
          }
        },
      },
    ]);
  };

  const save = async (v: PersonFormValue) => {
    setSaving(true);
    const fields = {
      name: v.name,
      gender: v.gender,
      birth_date: v.birth_date,
      birth_place: v.birth_place,
      death_date: v.death_date,
      photo_url: v.photo_url,
      job: v.job,
      is_adopted: v.is_adopted,
      notes: v.notes,
    };
    const newlyDeceased = !!v.death_date && !person?.death_date;
    try {
      await updatePerson(id, fields);
      await qc.invalidateQueries({ queryKey: ["person", id] });
      await qc.invalidateQueries({ queryKey: ["tree"] });
      setEditing(false);
      if (newlyDeceased) {
        setLastSaved(fields);
        setDeathConfirm(true);
      }
    } catch (e) {
      console.log("save error", e);
    } finally {
      setSaving(false);
    }
  };

  const keepChatVisible = async () => {
    // "No" -> override is_alive back to true so their chat stays visible
    try {
      await updatePerson(id, { ...lastSaved, is_alive: true });
      await qc.invalidateQueries({ queryKey: ["tree"] });
    } catch (e) {
      console.log("override error", e);
    }
    setDeathConfirm(false);
  };

  const delNote = async (noteId: string) => {
    try {
      await deleteNote(noteId);
      await qc.invalidateQueries({ queryKey: ["notes", id] });
      await qc.invalidateQueries({ queryKey: ["tree"] });
    } catch (e) {
      console.log("delete note error", e);
    }
  };

  const del = async () => {
    setDeleting(true);
    try {
      await deletePerson(id);
      await qc.invalidateQueries({ queryKey: ["tree"] });
      router.back();
    } catch (e) {
      console.log("delete error", e);
      setDeleting(false);
    }
  };

  const pinch = Gesture.Pinch()
    .onUpdate((e) => {
      zScale.value = Math.min(Math.max(zSaved.value * e.scale, 1), 4);
    })
    .onEnd(() => {
      zSaved.value = zScale.value;
    });
  const zStyle = useAnimatedStyle(() => ({ transform: [{ scale: zScale.value }] }));

  const goAdd = (direction: string, sib?: string) => {
    if (!person) return;
    router.push(
      `/add-relative?focus_id=${person.id}&direction=${direction}&focus_name=${encodeURIComponent(person.name)}${sib ? `&sib=${sib}` : ""}`,
    );
  };

  if (isLoading || !person) {
    return (
      <View style={[styles.root, { paddingTop: insets.top }]}>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.brandPrimary} />
        </View>
      </View>
    );
  }

  const color = nodeColor(person, colors);
  const photo = fileUrl(person.photo_url);

  const quick = [
    { key: "father", label: t("add_father"), icon: "arrow-up", color: colors.maleNode, dir: "father" },
    { key: "mother", label: t("add_mother"), icon: "arrow-up", color: colors.femaleNode, dir: "mother" },
    { key: "spouse", label: t("add_spouse"), icon: "heart", color: colors.brandPrimary, dir: "spouse" },
    { key: "older", label: t("add_older_sibling"), icon: "users", color: colors.brandSecondary, dir: "sibling", sib: "older" },
    { key: "younger", label: t("add_younger_sibling"), icon: "users", color: colors.brandSecondary, dir: "sibling", sib: "younger" },
    { key: "child", label: t("add_child"), icon: "arrow-down", color: colors.success, dir: "child" },
  ];

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.iconBtn} onPress={() => (editing ? setEditing(false) : router.back())} testID="detail-back">
          <Feather name={editing ? "x" : "chevron-left"} size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>{editing ? t("edit") : t("detail")}</Text>
        <View style={{ flexDirection: "row", gap: 8 }}>
          {!editing ? (
            <Pressable style={styles.iconBtn} onPress={() => router.push(`/explorer/${id}`)} testID="open-explorer">
              <Feather name="compass" size={17} color={colors.brandSecondary} />
            </Pressable>
          ) : null}
          {canEdit && !editing ? (
            <Pressable style={styles.iconBtn} onPress={() => setEditing(true)} testID="edit-button">
              <Feather name="edit-2" size={17} color={colors.onSurface} />
            </Pressable>
          ) : !editing ? (
            <View style={styles.iconBtn} />
          ) : (
            <View style={styles.iconBtn} />
          )}
        </View>
      </View>

      {editing ? (
        <PersonForm
          initial={{
            name: person.name,
            gender: person.gender ?? null,
            birth_date: person.birth_date ?? null,
            birth_place: person.birth_place ?? null,
            death_date: person.death_date ?? null,
            photo_url: person.photo_url ?? null,
            job: person.job ?? null,
            is_adopted: person.is_adopted ?? false,
            notes: person.notes ?? null,
          }}
          showAdopted
          submitLabel={t("save")}
          submitting={saving}
          onSubmit={save}
        />
      ) : (
        <KeyboardAwareScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 40 }} bottomOffset={20} keyboardShouldPersistTaps="handled">
          <View style={styles.hero}>
            <View style={[styles.avatar, { borderColor: color }]}>
              {photo ? <Image source={{ uri: photo }} style={styles.avatarImg} contentFit="cover" /> : <Feather name="user" size={48} color={color} />}
            </View>
            <Text style={styles.name}>{person.name}</Text>
            <View style={styles.roleTag}>
              <Feather name={person.is_root ? "award" : person.gender === "female" ? "user" : "user"} size={12} color={colors.onBrandTertiary} />
              <Text style={styles.roleTagText}>
                {person.is_root ? t("admin") : person.gender === "male" ? t("male") : person.gender === "female" ? t("female") : "-"}
              </Text>
            </View>
          </View>

          {canEdit ? (
            <View style={styles.quickRow}>
              {quick.map((d) => (
                <Pressable key={d.key} style={styles.quickBtn} onPress={() => goAdd(d.dir, (d as any).sib)} testID={`quick-${d.key}`}>
                  <View style={[styles.quickIcon, { backgroundColor: d.color }]}>
                    <Feather name={d.icon as any} size={20} color="#FFFFFF" />
                  </View>
                  <Text style={styles.quickLabel}>{d.label}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}

          <View style={styles.tabs}>
            {(["data", "notes", "files"] as const).map((tb) => (
              <Pressable key={tb} style={[styles.tab, activeTab === tb && styles.tabActive]} onPress={() => setActiveTab(tb)} testID={`detail-tab-${tb}`}>
                <Text style={[styles.tabText, activeTab === tb && styles.tabTextActive]}>
                  {tb === "data" ? t("tab_data") : tb === "notes" ? t("tab_notes") : t("tab_files")}
                </Text>
              </Pressable>
            ))}
          </View>

          {activeTab === "data" ? (
            <>
              <View style={styles.infoCard}>
                <InfoRow icon="calendar" label={t("birth_date")} value={person.birth_date} />
                <View style={styles.divider} />
                <InfoRow icon="map-pin" label={t("birth_place")} value={person.birth_place} />
                <View style={styles.divider} />
                <InfoRow icon="briefcase" label={t("job")} value={person.job} />
                <View style={styles.divider} />
                <InfoRow icon="star" label={t("death_date")} value={person.death_date || t("alive")} />
                {person.notes ? (
                  <>
                    <View style={styles.divider} />
                    <InfoRow icon="file-text" label={t("notes")} value={person.notes} />
                  </>
                ) : null}
              </View>

              {spouses.length ? (
                <>
                  <Text style={styles.marriageTitle}>{t("marriage_info")}</Text>
                  <View style={styles.infoCard}>
                    {spouses.map((s, i) => (
                      <View key={s.id}>
                        {i > 0 ? <View style={styles.divider} /> : null}
                        <View style={styles.infoRow}>
                          <Feather name="heart" size={18} color={s.divorced ? colors.error : colors.brandPrimary} />
                          <View style={{ flex: 1 }}>
                            <Text style={styles.infoLabel}>{t("spouse_label")}</Text>
                            <Text style={styles.infoValue}>{s.name}</Text>
                            {s.marriage_date ? (
                              <Text style={styles.spouseSub}>
                                {t("married_since")} {s.marriage_date}
                              </Text>
                            ) : null}
                            {s.divorced && s.divorce_date ? (
                              <Text style={[styles.spouseSub, { color: colors.error }]}>
                                {t("divorced_badge")} · {s.divorce_date}
                              </Text>
                            ) : null}
                          </View>
                          {s.divorced ? (
                            <View style={styles.divorceBadge}>
                              <Text style={styles.divorceBadgeText}>{t("divorced_badge")}</Text>
                            </View>
                          ) : null}
                          {canEdit ? (
                            <Pressable onPress={() => delRel(s.id, s.name)} hitSlop={10} testID={`spouse-del-${s.id}`} style={{ marginLeft: 6 }}>
                              <Feather name="trash-2" size={17} color={colors.error} />
                            </Pressable>
                          ) : null}
                        </View>
                      </View>
                    ))}
                  </View>
                </>
              ) : null}

              {relatives.length ? (
                <>
                  <Text style={styles.marriageTitle}>Relasi Keluarga</Text>
                  <View style={styles.infoCard}>
                    {relatives.map((r, i) => (
                      <View key={r.key}>
                        {i > 0 ? <View style={styles.divider} /> : null}
                        <Pressable style={styles.infoRow} onPress={() => router.push(`/person/${r.person.id}`)} testID={`rel-${r.key}`}>
                          <Feather name={r.icon as any} size={18} color={colors.brandSecondary} />
                          <View style={{ flex: 1 }}>
                            <Text style={styles.infoLabel}>{r.label}</Text>
                            <Text style={styles.infoValue}>{r.person.name}</Text>
                          </View>
                          {canEdit && r.relId ? (
                            <Pressable onPress={() => delRel(r.relId!, r.person.name)} hitSlop={10} testID={`rel-del-${r.key}`} style={{ marginRight: 4 }}>
                              <Feather name="trash-2" size={17} color={colors.error} />
                            </Pressable>
                          ) : null}
                          <Feather name="chevron-right" size={18} color={colors.muted} />
                        </Pressable>
                      </View>
                    ))}
                  </View>
                </>
              ) : null}

              {isAdmin && !person.is_root ? (
                <View style={styles.actions}>
                  <Pressable style={styles.deleteBtn} onPress={del} testID="delete-button">
                    {deleting ? (
                      <ActivityIndicator color={colors.error} />
                    ) : (
                      <>
                        <Feather name="trash-2" size={18} color={colors.error} />
                        <Text style={styles.deleteText}>{t("delete")}</Text>
                      </>
                    )}
                  </Pressable>
                </View>
              ) : null}
            </>
          ) : null}

          {activeTab === "notes" ? (
            <>
              {canEdit ? (
                <View style={styles.noteInputRow}>
                  <TextInput
                    testID="note-input"
                    style={styles.noteInput}
                    placeholder={t("note_placeholder")}
                    placeholderTextColor={colors.muted}
                    value={noteText}
                    onChangeText={setNoteText}
                    multiline
                  />
                  <GradientButton testID="add-note-button" title={t("add_note")} icon="plus" loading={noteBusy} onPress={submitNote} />
                </View>
              ) : null}
              {textNotes.length === 0 ? (
                <View style={styles.emptyTab}>
                  <Feather name="file-text" size={28} color={colors.muted} />
                  <Text style={styles.emptyTabText}>{t("no_notes")}</Text>
                </View>
              ) : (
                textNotes.map((n: any) => (
                  <View key={n.id} style={styles.noteCard} testID={`note-${n.id}`}>
                    <View style={styles.noteHeader}>
                      <Text style={styles.noteMeta}>
                        {n.author_name} · {fmtDate(n.created_at)}
                      </Text>
                      {isAdmin || n.author_id === user?.user_id ? (
                        <Pressable onPress={() => delNote(n.id)} hitSlop={10} testID={`delete-note-${n.id}`}>
                          <Feather name="trash-2" size={16} color={colors.error} />
                        </Pressable>
                      ) : null}
                    </View>
                    <Text style={styles.noteText}>{n.note_text}</Text>
                  </View>
                ))
              )}
            </>
          ) : null}

          {activeTab === "files" ? (
            <>
              {canEdit ? (
                <View style={styles.noteInputRow}>
                  <GradientButton testID="add-file-button" title={t("add_file")} icon="upload" loading={fileBusy} onPress={submitFile} />
                </View>
              ) : null}
              {fileNotes.length === 0 ? (
                <View style={styles.emptyTab}>
                  <Feather name="folder" size={28} color={colors.muted} />
                  <Text style={styles.emptyTabText}>{t("no_files")}</Text>
                </View>
              ) : (
                fileNotes.map((n: any) => (
                  <View key={n.id} style={styles.fileCard} testID={`file-${n.id}`}>
                    <Pressable onPress={() => setViewerUri(fileUrl(n.attachments[0]) ?? null)} testID={`file-open-${n.id}`}>
                      <Image source={{ uri: fileUrl(n.attachments[0]) }} style={styles.fileImg} contentFit="cover" />
                    </Pressable>
                    <View style={styles.fileMetaRow}>
                      <Text style={styles.fileMeta} numberOfLines={1}>
                        {n.note_text} · {n.author_name} · {fmtDate(n.created_at)}
                      </Text>
                      {isAdmin || n.author_id === user?.user_id ? (
                        <Pressable onPress={() => delNote(n.id)} hitSlop={10} testID={`delete-file-${n.id}`}>
                          <Feather name="trash-2" size={16} color={colors.error} />
                        </Pressable>
                      ) : null}
                    </View>
                  </View>
                ))
              )}
            </>
          ) : null}
        </KeyboardAwareScrollView>
      )}

      <Modal visible={!!viewerUri} transparent animationType="fade" onRequestClose={() => { setViewerUri(null); zScale.value = 1; zSaved.value = 1; }}>
        <View style={styles.viewerBg}>
          <GestureDetector gesture={pinch}>
            <Animated.View style={[{ width: "100%", height: "80%" }, zStyle]}>
              {viewerUri ? <Image source={{ uri: viewerUri }} style={styles.viewerImg} contentFit="contain" /> : null}
            </Animated.View>
          </GestureDetector>
          <Pressable style={styles.viewerClose} onPress={() => { setViewerUri(null); zScale.value = 1; zSaved.value = 1; }} testID="viewer-close">
            <Feather name="x" size={22} color="#FFFFFF" />
          </Pressable>
        </View>
      </Modal>

      <Modal visible={deathConfirm} transparent animationType="fade" onRequestClose={() => setDeathConfirm(false)}>
        <View style={styles.confirmBg}>
          <View style={styles.confirmCard}>
            <Feather name="help-circle" size={32} color={colors.brandPrimary} style={{ alignSelf: "center" }} />
            <Text style={styles.confirmTitle}>
              {t("hide_chat_prompt")} {person.name} {t("hide_chat_prompt2")}
            </Text>
            <View style={styles.confirmRow}>
              <GradientButton testID="death-confirm-no" variant="secondary" title={t("no")} onPress={keepChatVisible} style={{ flex: 1 }} />
              <GradientButton testID="death-confirm-yes" title={t("yes")} onPress={() => setDeathConfirm(false)} style={{ flex: 1 }} />
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}
