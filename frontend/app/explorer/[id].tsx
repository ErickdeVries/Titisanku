import { useMemo, useState } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { runOnJS } from "react-native-reanimated";
import { ArrowLeft, Plus, Minus, ChevronUp, Heart, ChevronDown, Users } from "lucide-react-native";
import { fonts, useTheme } from "@/src/theme";
import { getTree, Person } from "@/src/api";
import { useTree } from "@/src/tree-context";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { BigPersonCard } from "@/src/components/BigPersonCard";

const PARENT_TYPES = ["parent", "adopted_child"];
const byBirth = (a: Person, b: Person) => {
  const da = a.birth_date ? new Date(a.birth_date).getTime() : Infinity;
  const db = b.birth_date ? new Date(b.birth_date).getTime() : Infinity;
  return da - db;
};

function AddChip({ label, color, onPress, testID }: any) {
  const { colors } = useTheme();
  return (
    <Pressable onPress={onPress} testID={testID} style={[styles.addChip, { borderColor: color }]}>
      <Plus size={15} color={color} />
      <Text style={[styles.addChipText, { color }]}>{label}</Text>
    </Pressable>
  );
}

export default function Explorer() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { activeTree } = useTree();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [zoom, setZoom] = useState(1);
  const [expUp, setExpUp] = useState(1);
  const [expDown, setExpDown] = useState(1);

  const { data, isLoading } = useQuery({ queryKey: ["tree"], queryFn: getTree });
  const role = data?.role ?? user?.role;
  const canEdit = role === "admin" || role === "editor";

  const rel = useMemo(() => {
    const people = data?.people ?? [];
    const relations = data?.relations ?? [];
    const byId = new Map(people.map((p) => [p.id, p] as const));
    const center = byId.get(id);
    const parentIds = relations.filter((r) => r.related_person_id === id && PARENT_TYPES.includes(r.relation_type)).map((r) => r.person_id);
    const parents = parentIds.map((pid) => byId.get(pid)).filter(Boolean) as Person[];
    parents.sort((a, b) => (a.gender === "male" ? -1 : b.gender === "male" ? 1 : 0));
    const spouses = relations
      .filter((r) => (r.relation_type === "spouse" || r.relation_type === "divorced") && (r.person_id === id || r.related_person_id === id))
      .map((r) => {
        const pid = r.person_id === id ? r.related_person_id : r.person_id;
        const p = byId.get(pid);
        return p ? { person: p, divorced: r.relation_type === "divorced" } : null;
      })
      .filter(Boolean) as { person: Person; divorced: boolean }[];
    const sibSet = new Set<string>();
    if (parentIds.length) {
      for (const pid of parentIds) {
        relations
          .filter((r) => r.person_id === pid && PARENT_TYPES.includes(r.relation_type))
          .forEach((r) => { if (r.related_person_id !== id) sibSet.add(r.related_person_id); });
      }
    } else {
      relations
        .filter((r) => r.relation_type === "sibling" && (r.person_id === id || r.related_person_id === id))
        .forEach((r) => sibSet.add(r.person_id === id ? r.related_person_id : r.person_id));
    }
    const siblings = [...sibSet].map((sid) => byId.get(sid)).filter(Boolean).sort(byBirth) as Person[];
    const children = relations
      .filter((r) => r.person_id === id && PARENT_TYPES.includes(r.relation_type))
      .map((r) => byId.get(r.related_person_id))
      .filter(Boolean)
      .sort(byBirth) as Person[];
    const parentsOf = (pid: string) =>
      relations.filter((r) => r.related_person_id === pid && PARENT_TYPES.includes(r.relation_type)).map((r) => byId.get(r.person_id)).filter(Boolean) as Person[];
    const childrenOf = (pid: string) =>
      relations.filter((r) => r.person_id === pid && PARENT_TYPES.includes(r.relation_type)).map((r) => byId.get(r.related_person_id)).filter(Boolean) as Person[];
    const gpSet = new Map<string, Person>();
    parents.forEach((p) => parentsOf(p.id).forEach((gp) => gpSet.set(gp.id, gp)));
    const grandparents = [...gpSet.values()];
    const gcSet = new Map<string, Person>();
    children.forEach((c) => childrenOf(c.id).forEach((gc) => gcSet.set(gc.id, gc)));
    const grandchildren = [...gcSet.values()].sort(byBirth);
    const hasFather = parents.some((p) => p.gender === "male");
    const hasMother = parents.some((p) => p.gender === "female");
    return { center, parents, spouses, siblings, children, grandparents, grandchildren, hasFather, hasMother };
  }, [data, id]);

  const setZ = (v: number) => setZoom(Math.min(1.6, Math.max(0.7, Math.round(v * 20) / 20)));
  const pinch = Gesture.Pinch().onUpdate((e) => {
    runOnJS(setZ)(zoom * e.scale);
  });

  const goExplore = (pid: string) => router.push(`/explorer/${pid}`);
  const goDetail = (pid: string) => router.push(`/person/${pid}`);
  const goAdd = (direction: string, sib?: string) => {
    if (!rel.center) return;
    router.push(`/add-relative?focus_id=${id}&direction=${direction}&focus_name=${encodeURIComponent(rel.center.name)}${sib ? `&sib=${sib}` : ""}`);
  };

  if (isLoading || !rel.center) {
    return (
      <View style={[styles.root, { backgroundColor: colors.surface }]}>
        <View style={styles.center}><ActivityIndicator size="large" color={colors.brandPrimary} /></View>
      </View>
    );
  }

  const Section = ({ label, icon }: { label: string; icon: any }) => (
    <View style={styles.sectionHead}>
      {icon}
      <Text style={[styles.sectionLabel, { color: colors.muted }]}>{label}</Text>
    </View>
  );

  return (
    <View style={[styles.root, { backgroundColor: colors.surface, paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="explorer-back">
          <ArrowLeft size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={[styles.title, { color: colors.onSurface }]} numberOfLines={1}>{rel.center.name}</Text>
        <Pressable onPress={() => goDetail(id)} hitSlop={10} testID="explorer-detail">
          <Text style={[styles.detailLink, { color: colors.brandSecondary }]}>{t("open_detail")}</Text>
        </Pressable>
      </View>

      <View style={styles.filterBar}>
        <View style={styles.filterGroup}>
          <ChevronUp size={15} color={colors.muted} />
          <Pressable onPress={() => setExpUp((v) => Math.max(0, v - 1))} hitSlop={8} testID="exp-up-minus"><Minus size={16} color={colors.onSurface} /></Pressable>
          <Text style={[styles.filterVal, { color: colors.onSurface }]}>{expUp}</Text>
          <Pressable onPress={() => setExpUp((v) => Math.min(2, v + 1))} hitSlop={8} testID="exp-up-plus"><Plus size={16} color={colors.onSurface} /></Pressable>
        </View>
        <View style={styles.filterGroup}>
          <ChevronDown size={15} color={colors.muted} />
          <Pressable onPress={() => setExpDown((v) => Math.max(0, v - 1))} hitSlop={8} testID="exp-down-minus"><Minus size={16} color={colors.onSurface} /></Pressable>
          <Text style={[styles.filterVal, { color: colors.onSurface }]}>{expDown}</Text>
          <Pressable onPress={() => setExpDown((v) => Math.min(2, v + 1))} hitSlop={8} testID="exp-down-plus"><Plus size={16} color={colors.onSurface} /></Pressable>
        </View>
      </View>

      <GestureDetector gesture={pinch}>
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 90, gap: 18 }} showsVerticalScrollIndicator={false}>
          {/* Grandparents */}
          {expUp >= 2 && rel.grandparents.length ? (
            <>
              <Section label={t("grandparents_label")} icon={<ChevronUp size={16} color={colors.muted} />} />
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rowContent}>
                {rel.grandparents.map((p) => (
                  <BigPersonCard key={p.id} person={p} scale={zoom} onPress={() => goExplore(p.id)} testID={`exp-gp-${p.id}`} />
                ))}
              </ScrollView>
            </>
          ) : null}

          {/* Parents */}
          {expUp >= 1 ? (
            <>
              <Section label={t("parents_label")} icon={<ChevronUp size={16} color={colors.muted} />} />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rowContent}>
            {rel.parents.map((p) => (
              <BigPersonCard key={p.id} person={p} scale={zoom} onPress={() => goExplore(p.id)} testID={`exp-parent-${p.id}`} />
            ))}
            {canEdit && !rel.hasFather ? <AddChip label={t("add_father")} color={colors.maleNode} onPress={() => goAdd("father")} testID="exp-add-father" /> : null}
            {canEdit && !rel.hasMother ? <AddChip label={t("add_mother")} color={colors.femaleNode} onPress={() => goAdd("mother")} testID="exp-add-mother" /> : null}
            {!rel.parents.length && !canEdit ? <Text style={[styles.empty, { color: colors.muted }]}>{t("no_relatives")}</Text> : null}
          </ScrollView>
            </>
          ) : null}

          {/* Center + spouse */}
          <View style={styles.centerRow}>
            <BigPersonCard person={rel.center} scale={zoom * 1.08} highlight onInfo={() => goDetail(id)} testID="exp-center" />
            {rel.spouses.map((s) => (
              <View key={s.person.id} style={styles.spouseWrap}>
                <Heart size={18 * zoom} color={s.divorced ? colors.error : colors.brandPrimary} style={{ marginHorizontal: 4 }} />
                <BigPersonCard
                  person={s.person}
                  scale={zoom}
                  label={s.divorced ? t("divorced_badge") : t("spouse_label")}
                  onPress={() => goExplore(s.person.id)}
                  testID={`exp-spouse-${s.person.id}`}
                />
              </View>
            ))}
            {canEdit ? <AddChip label={t("add_spouse")} color={colors.brandPrimary} onPress={() => goAdd("spouse")} testID="exp-add-spouse" /> : null}
          </View>

          {/* Siblings */}
          <Section label={t("siblings_label")} icon={<Users size={16} color={colors.muted} />} />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rowContent}>
            {rel.siblings.map((p, i) => (
              <BigPersonCard
                key={p.id}
                person={p}
                scale={zoom}
                label={i < rel.siblings.length / 2 ? t("add_older_sibling") : t("add_younger_sibling")}
                onPress={() => goExplore(p.id)}
                testID={`exp-sibling-${p.id}`}
              />
            ))}
            {canEdit ? <AddChip label={t("add_older_sibling")} color={colors.brandSecondary} onPress={() => goAdd("sibling", "older")} testID="exp-add-older" /> : null}
            {canEdit ? <AddChip label={t("add_younger_sibling")} color={colors.brandSecondary} onPress={() => goAdd("sibling", "younger")} testID="exp-add-younger" /> : null}
            {!rel.siblings.length && !canEdit ? <Text style={[styles.empty, { color: colors.muted }]}>{t("no_relatives")}</Text> : null}
          </ScrollView>

          {/* Children */}
          {expDown >= 1 ? (
            <>
              <Section label={t("children_label")} icon={<ChevronDown size={16} color={colors.muted} />} />
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rowContent}>
                {rel.children.map((p) => (
                  <BigPersonCard key={p.id} person={p} scale={zoom} onPress={() => goExplore(p.id)} testID={`exp-child-${p.id}`} />
                ))}
                {canEdit ? <AddChip label={t("add_child")} color={colors.success} onPress={() => goAdd("child")} testID="exp-add-child" /> : null}
                {!rel.children.length && !canEdit ? <Text style={[styles.empty, { color: colors.muted }]}>{t("no_relatives")}</Text> : null}
              </ScrollView>
            </>
          ) : null}

          {/* Grandchildren */}
          {expDown >= 2 && rel.grandchildren.length ? (
            <>
              <Section label={t("grandchildren_label")} icon={<ChevronDown size={16} color={colors.muted} />} />
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rowContent}>
                {rel.grandchildren.map((p) => (
                  <BigPersonCard key={p.id} person={p} scale={zoom} onPress={() => goExplore(p.id)} testID={`exp-gc-${p.id}`} />
                ))}
              </ScrollView>
            </>
          ) : null}
        </ScrollView>
      </GestureDetector>

      {/* Zoom controls */}
      <View style={[styles.zoomBar, { bottom: insets.bottom + 20, backgroundColor: colors.surfaceSecondary, borderColor: colors.border }]}>
        <Pressable onPress={() => setZ(zoom - 0.1)} hitSlop={8} testID="zoom-out"><Minus size={20} color={colors.onSurface} /></Pressable>
        <Text style={[styles.zoomVal, { color: colors.muted }]}>{Math.round(zoom * 100)}%</Text>
        <Pressable onPress={() => setZ(zoom + 0.1)} hitSlop={8} testID="zoom-in"><Plus size={20} color={colors.onSurface} /></Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 16, paddingBottom: 12, gap: 12 },
  title: { fontFamily: fonts.display, fontSize: 20, flex: 1, textAlign: "center" },
  detailLink: { fontFamily: fonts.medium, fontSize: 12 },
  filterBar: { flexDirection: "row", justifyContent: "center", gap: 20, paddingBottom: 10 },
  filterGroup: { flexDirection: "row", alignItems: "center", gap: 10 },
  filterVal: { fontFamily: fonts.semibold, fontSize: 14, minWidth: 16, textAlign: "center" },
  sectionHead: { flexDirection: "row", alignItems: "center", gap: 6 },
  sectionLabel: { fontFamily: fonts.semibold, fontSize: 12, textTransform: "uppercase", letterSpacing: 0.6 },
  rowContent: { gap: 14, paddingVertical: 10, paddingHorizontal: 2, alignItems: "flex-start" },
  centerRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 10, paddingVertical: 6 },
  spouseWrap: { flexDirection: "row", alignItems: "center" },
  empty: { fontFamily: fonts.regular, fontSize: 13, paddingVertical: 16 },
  addChip: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1.5, borderStyle: "dashed", borderRadius: 14, paddingHorizontal: 12, paddingVertical: 10, alignSelf: "center", marginTop: 20 },
  addChipText: { fontFamily: fonts.semibold, fontSize: 13 },
  zoomBar: { position: "absolute", right: 16, flexDirection: "row", alignItems: "center", gap: 12, borderWidth: 1, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 10 },
  zoomVal: { fontFamily: fonts.medium, fontSize: 12, minWidth: 38, textAlign: "center" },
});
