import { useMemo, useState, useEffect } from "react";
import { View, Text, Pressable, ActivityIndicator, useWindowDimensions, Modal } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, { useSharedValue, useAnimatedStyle, withTiming, runOnJS } from "react-native-reanimated";
import Svg, { Line } from "react-native-svg";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getTree } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useTree } from "@/src/tree-context";
import { useI18n } from "@/src/i18n";
import { PersonNode } from "@/src/components/PersonNode";
import { buildLayout, NODE_R } from "@/src/tree-layout";
import { exportTreePdf } from "@/src/export-pdf";
import { GradientButton } from "@/src/components/GradientButton";
import { UpgradeModal } from "@/src/components/UpgradeModal";

const EMPTY_IMG =
  "https://images.unsplash.com/photo-1749006813623-bc3bd798158c?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzF8MHwxfHNlYXJjaHwxfHxmYW1pbHklMjB0cmVlJTIwY29uY2VwdCUyMGlsbHVzdHJhdGlvbnxlbnwwfHx8fDE3ODg2MTg1Nzl8MA&ixlib=rb-4.1.0&q=85";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingBottom: 12,
    backgroundColor: c.surface,
    borderBottomWidth: 1,
    borderBottomColor: c.divider,
  },
  headerTitle: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  headerLeft: { flex: 1, marginRight: 12 },
  headerMeta: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 2 },
  planChip: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999 },
  planChipText: { fontFamily: fonts.bold, fontSize: 10, letterSpacing: 0.5 },
  headerCount: { fontFamily: fonts.medium, fontSize: 12, color: c.muted },
  headerActions: { flexDirection: "row", alignItems: "center", gap: 8 },
  iconBtn: { width: 38, height: 38, borderRadius: 999, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  exportBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: c.surfaceTertiary, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999 },
  exportText: { fontFamily: fonts.medium, fontSize: 13, color: c.onSurfaceSecondary },
  statsStrip: { flexDirection: "row", gap: 10, paddingHorizontal: 16, paddingVertical: 12, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider },
  statCard: { flex: 1, backgroundColor: c.surfaceSecondary, borderRadius: 14, paddingVertical: 10, paddingHorizontal: 12, gap: 2 },
  statValue: { fontFamily: fonts.bold, fontSize: 18, color: c.onSurface },
  statLabel: { fontFamily: fonts.regular, fontSize: 11, color: c.muted },
  focusChip: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", marginHorizontal: 16, marginTop: 10, backgroundColor: c.brandTertiary, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 999 },
  focusChipText: { fontFamily: fonts.medium, fontSize: 12, color: c.onBrandTertiary },
  canvasArea: { flex: 1, overflow: "hidden" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 32, gap: 16 },
  emptyImg: { width: 180, height: 180, borderRadius: 20 },
  emptyTitle: { fontFamily: fonts.semibold, fontSize: 18, color: c.onSurface },
  emptyDesc: { fontFamily: fonts.regular, fontSize: 14, color: c.muted, textAlign: "center" },
  nodeWrap: { position: "absolute", width: 96, alignItems: "center" },
  addBtn: {
    position: "absolute",
    width: 34,
    height: 34,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#0F172A",
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 4,
  },
  legend: {
    position: "absolute",
    left: 16,
    flexDirection: "row",
    gap: 14,
    backgroundColor: "rgba(255,255,255,0.92)",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 12,
  },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 5 },
  legendDot: { width: 10, height: 10, borderRadius: 999 },
  legendText: { fontFamily: fonts.regular, fontSize: 11, color: c.onSurfaceSecondary },
  // export modal
  modalBg: { flex: 1, backgroundColor: "rgba(15,23,42,0.4)", justifyContent: "flex-end" },
  sheet: { backgroundColor: c.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, gap: 20 },
  sheetTitle: { fontFamily: fonts.bold, fontSize: 18, color: c.onSurface },
  stepperRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  stepperLabel: { fontFamily: fonts.medium, fontSize: 14, color: c.onSurfaceSecondary },
  stepper: { flexDirection: "row", alignItems: "center", gap: 16 },
  stepBtn: { width: 36, height: 36, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  stepVal: { fontFamily: fonts.semibold, fontSize: 16, color: c.onSurface, minWidth: 24, textAlign: "center" },
}));

function GrowNode({ x, y, children }: { x: number; y: number; children: any }) {
  const styles = useStyles();
  const p = useSharedValue(0);
  useEffect(() => {
    p.value = withTiming(1, { duration: 340 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const aStyle = useAnimatedStyle(() => ({
    opacity: p.value,
    transform: [{ scale: 0.55 + 0.45 * p.value }, { translateY: (1 - p.value) * -10 }],
  }));
  return <Animated.View style={[styles.nodeWrap, { left: x, top: y }, aStyle]}>{children}</Animated.View>;
}

function AddButton({ x, y, bg, icon, onPress, testID }: any) {  const styles = useStyles();
  return (
    <Pressable testID={testID} onPress={onPress} style={[styles.addBtn, { left: x, top: y, backgroundColor: bg }]}>
      <Feather name={icon} size={18} color="#FFFFFF" />
    </Pressable>
  );
}

export default function TreeScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width: screenW } = useWindowDimensions();

  const { data, isLoading } = useQuery({ queryKey: ["tree"], queryFn: getTree });
  const { activeTree, pendingFocusId, setPendingFocus } = useTree();
  const [selected, setSelected] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [filterUp, setFilterUp] = useState(2);
  const [filterDown, setFilterDown] = useState(2);
  const [exporting, setExporting] = useState(false);

  const role = data?.role ?? user?.role;
  const canEdit = role === "admin" || role === "editor";
  const plan = activeTree?.plan ?? data?.tree?.plan ?? "free";
  const limit = data?.limit ?? null;
  const personCount = data?.person_count ?? data?.people?.length ?? 0;
  const atLimit = limit != null && personCount >= limit;

  useEffect(() => {
    if (!focusId && data?.root_id) setFocusId(data.root_id);
  }, [data?.root_id, focusId]);

  useEffect(() => {
    if (pendingFocusId) {
      setFocusId(pendingFocusId);
      setSelected(pendingFocusId);
      setPendingFocus(null);
    }
  }, [pendingFocusId, setPendingFocus]);

  const activeFocus = focusId ?? data?.root_id ?? null;

  const layout = useMemo(
    () => buildLayout(data?.people ?? [], data?.relations ?? [], activeFocus, filterUp, filterDown),
    [data, activeFocus, filterUp, filterDown],
  );

  const stats = useMemo(() => {
    const people = data?.people ?? [];
    const members = people.length;
    const generations = new Set(layout.nodes.map((n) => n.gen)).size;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    let best: { name: string; days: number } | null = null;
    for (const p of people) {
      if (!p.birth_date || p.death_date) continue;
      const bd = new Date(p.birth_date);
      if (isNaN(bd.getTime())) continue;
      let next = new Date(today.getFullYear(), bd.getMonth(), bd.getDate());
      if (next < today) next = new Date(today.getFullYear() + 1, bd.getMonth(), bd.getDate());
      const days = Math.round((next.getTime() - today.getTime()) / 86400000);
      if (!best || days < best.days) best = { name: p.name, days };
    }
    return { members, generations, birthday: best };
  }, [data, layout]);

  const scale = useSharedValue(1);
  const savedScale = useSharedValue(1);
  const tx = useSharedValue(0);
  const ty = useSharedValue(0);
  const sx = useSharedValue(0);
  const sy = useSharedValue(0);

  useEffect(() => {
    // center the focused node at top-center
    const focusNode =
      layout.nodes.find((n) => n.id === activeFocus) ?? layout.nodes.find((n) => n.person.is_root) ?? layout.nodes[0];
    if (focusNode) {
      scale.value = withTiming(1);
      savedScale.value = 1;
      tx.value = withTiming(screenW / 2 - focusNode.x);
      ty.value = withTiming(100 - focusNode.y);
      sx.value = screenW / 2 - focusNode.x;
      sy.value = 100 - focusNode.y;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout.nodes.length, activeFocus]);

  const pan = Gesture.Pan()
    .minDistance(8)
    .onUpdate((e) => {
      tx.value = sx.value + e.translationX;
      ty.value = sy.value + e.translationY;
    })
    .onEnd(() => {
      sx.value = tx.value;
      sy.value = ty.value;
    });

  const pinch = Gesture.Pinch()
    .onUpdate((e) => {
      scale.value = Math.min(Math.max(savedScale.value * e.scale, 0.4), 2.5);
    })
    .onEnd(() => {
      savedScale.value = scale.value;
    });

  const composed = Gesture.Simultaneous(pan, pinch);

  const canvasStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: tx.value }, { translateY: ty.value }, { scale: scale.value }],
  }));

  const selNode = layout.nodes.find((n) => n.id === selected);

  const openAdd = (direction: string) => {
    if (!selNode) return;
    if (atLimit) {
      setSelected(null);
      setUpgradeOpen(true);
      return;
    }
    router.push(`/add-relative?focus_id=${selNode.id}&direction=${direction}&focus_name=${encodeURIComponent(selNode.person.name)}`);
    setSelected(null);
  };

  const doFocus = () => {
    if (!selNode) return;
    setFocusId(selNode.id);
    setSelected(null);
  };

  const focusName = layout.nodes.find((n) => n.id === activeFocus)?.person.name;
  const isRootFocus = !data?.root_id || activeFocus === data?.root_id;

  const doExport = async () => {
    setExporting(true);
    try {
      await exportTreePdf(data!.people, data!.relations, activeFocus ?? data!.root_id, filterUp, filterDown, "KETURUNANKU", plan === "free");
      setExportOpen(false);
    } catch (e) {
      console.log("export error", e);
    } finally {
      setExporting(false);
    }
  };

  if (isLoading) {
    return (
      <View style={[styles.root, { paddingTop: insets.top }]}>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.brandPrimary} />
        </View>
      </View>
    );
  }

  const hasTree = layout.nodes.length > 0;

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <View style={styles.headerLeft}>
          <Text style={styles.headerTitle} numberOfLines={1}>{activeTree?.name ?? t("tree")}</Text>
          <View style={styles.headerMeta}>
            <View style={[styles.planChip, { backgroundColor: plan === "free" ? colors.brandTertiary : colors.brandSecondary }]}>
              <Text style={[styles.planChipText, { color: plan === "free" ? colors.onBrandTertiary : colors.onBrandSecondary }]}>
                {plan === "pro" ? "PRO" : plan === "family" ? "KELUARGA" : "GRATIS"}
              </Text>
            </View>
            {limit != null ? (
              <Text style={styles.headerCount}>{personCount}/{limit}</Text>
            ) : (
              <Text style={styles.headerCount}>{personCount} orang</Text>
            )}
          </View>
        </View>
        {hasTree ? (
          <View style={styles.headerActions}>
            <Pressable style={styles.iconBtn} onPress={() => setFilterOpen(true)} testID="open-filter">
              <Feather name="sliders" size={18} color={colors.brandSecondary} />
            </Pressable>
            <Pressable
              style={styles.iconBtn}
              onPress={() => router.push(`/explorer/${activeFocus ?? data?.root_id}`)}
              testID="open-explorer"
            >
              <Feather name="compass" size={18} color={colors.brandSecondary} />
            </Pressable>
            <Pressable style={styles.exportBtn} onPress={() => setExportOpen(true)} testID="export-pdf-button">
              <Feather name="file-text" size={15} color={colors.onSurfaceSecondary} />
              <Text style={styles.exportText}>{t("export_pdf")}</Text>
            </Pressable>
          </View>
        ) : null}
      </View>

      {hasTree ? (
        <>
          <View style={styles.statsStrip}>
            <View style={styles.statCard}>
              <Text style={styles.statValue}>{stats.members}</Text>
              <Text style={styles.statLabel}>{t("stats_members")}</Text>
            </View>
            <View style={styles.statCard}>
              <Text style={styles.statValue}>{stats.generations}</Text>
              <Text style={styles.statLabel}>{t("stats_generations")}</Text>
            </View>
            <View style={styles.statCard} testID="stat-birthday">
              <Text style={styles.statValue} numberOfLines={1}>
                {stats.birthday ? (stats.birthday.days === 0 ? "🎂" : `${stats.birthday.days}`) : "—"}
              </Text>
              <Text style={styles.statLabel} numberOfLines={1}>
                {stats.birthday
                  ? stats.birthday.days === 0
                    ? `${t("today_birthday")} ${stats.birthday.name}`
                    : `${stats.birthday.name} · ${t("days_left")}`
                  : t("no_birthday")}
              </Text>
            </View>
          </View>
          {!isRootFocus ? (
            <Pressable style={styles.focusChip} onPress={() => setFocusId(data?.root_id ?? null)} testID="reset-focus">
              <Feather name="crosshair" size={13} color={colors.onBrandTertiary} />
              <Text style={styles.focusChipText}>
                {t("focused_on")} {focusName} · {t("back_to_root")}
              </Text>
              <Feather name="x" size={13} color={colors.onBrandTertiary} />
            </Pressable>
          ) : null}
        </>
      ) : null}

      {!hasTree ? (
        <View style={styles.center}>
          <Image source={{ uri: EMPTY_IMG }} style={styles.emptyImg} contentFit="cover" />
          <Text style={styles.emptyTitle}>{t("empty_tree_title")}</Text>
          <Text style={styles.emptyDesc}>{t("empty_tree_desc")}</Text>
        </View>
      ) : (
        <View style={styles.canvasArea}>
          <GestureDetector gesture={composed}>
            <Animated.View style={{ flex: 1 }}>
              <Pressable style={{ flex: 1 }} onPress={() => setSelected(null)}>
                <Animated.View style={[{ width: layout.width, height: layout.height }, canvasStyle]}>
                  <Svg width={layout.width} height={layout.height} style={{ position: "absolute", top: 0, left: 0 }}>
                    {layout.edges.map((e) => {
                      const stroke =
                        e.kind === "adopted"
                          ? colors.nodeAdoptedLine
                          : e.kind === "divorce"
                            ? colors.nodeDivorceLine
                            : colors.nodeRelationLine;
                      return (
                        <Line
                          key={e.key}
                          x1={e.x1}
                          y1={e.y1}
                          x2={e.x2}
                          y2={e.y2}
                          stroke={stroke}
                          strokeWidth={2}
                          strokeLinecap="round"
                          strokeDasharray={e.kind === "adopted" ? "7,6" : undefined}
                        />
                      );
                    })}
                  </Svg>

                  {layout.nodes.map((n) => (
                    <GrowNode key={n.id} x={n.x - 48} y={n.y - NODE_R - 3}>
                      <PersonNode
                        person={n.person}
                        selected={selected === n.id}
                        onPress={() => {
                          if (selected === n.id) router.push(`/person/${n.id}`);
                          else setSelected(n.id);
                        }}
                      />
                    </GrowNode>
                  ))}

                  {selNode ? (
                    <AddButton testID="focus-node" x={selNode.x - 62} y={selNode.y - 17} bg={colors.surfaceInverse} icon="crosshair" onPress={doFocus} />
                  ) : null}
                  {selNode && canEdit ? (
                    <>
                      <AddButton testID="add-father" x={selNode.x - 62} y={selNode.y - NODE_R - 22} bg={colors.maleNode} icon="arrow-up" onPress={() => openAdd("father")} />
                      <AddButton testID="add-mother" x={selNode.x + 28} y={selNode.y - NODE_R - 22} bg={colors.femaleNode} icon="arrow-up" onPress={() => openAdd("mother")} />
                      <AddButton testID="add-spouse" x={selNode.x + 42} y={selNode.y - 17} bg={colors.brandPrimary} icon="heart" onPress={() => openAdd("spouse")} />
                      <AddButton testID="add-sibling" x={selNode.x - 62} y={selNode.y + NODE_R - 6} bg={colors.brandSecondary} icon="users" onPress={() => openAdd("sibling")} />
                      <AddButton testID="add-child" x={selNode.x + 28} y={selNode.y + NODE_R - 6} bg={colors.success} icon="arrow-down" onPress={() => openAdd("child")} />
                    </>
                  ) : null}
                </Animated.View>
              </Pressable>
            </Animated.View>
          </GestureDetector>

          <View style={[styles.legend, { bottom: insets.bottom + 16 }]}>
            <View style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: colors.maleNode }]} />
              <Text style={styles.legendText}>{t("male")}</Text>
            </View>
            <View style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: colors.femaleNode }]} />
              <Text style={styles.legendText}>{t("female")}</Text>
            </View>
            <View style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: colors.adminNode }]} />
              <Text style={styles.legendText}>{t("admin")}</Text>
            </View>
          </View>
        </View>
      )}

      <Modal visible={exportOpen} transparent animationType="slide" onRequestClose={() => setExportOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setExportOpen(false)}>
          <Pressable style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]} onPress={() => {}}>
            <Text style={styles.sheetTitle}>{t("export_pdf")}</Text>
            <Text style={{ fontFamily: fonts.regular, fontSize: 13, color: colors.muted, marginBottom: 4 }}>{t("export_current_view")}</Text>
            <View style={{ backgroundColor: colors.surfaceTertiary, borderRadius: 12, padding: 14, gap: 8, marginBottom: 16 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Feather name="target" size={16} color={colors.brandSecondary} />
                <Text style={{ fontFamily: fonts.medium, fontSize: 14, color: colors.onSurface }}>{t("center")}: {focusName ?? t("root_person")}</Text>
              </View>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Feather name="arrow-up" size={16} color={colors.muted} />
                <Text style={{ fontFamily: fonts.regular, fontSize: 14, color: colors.onSurfaceSecondary }}>{filterUp > 20 ? t("all_generations") : `${filterUp} ${t("gen_above")}`}</Text>
              </View>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Feather name="arrow-down" size={16} color={colors.muted} />
                <Text style={{ fontFamily: fonts.regular, fontSize: 14, color: colors.onSurfaceSecondary }}>{filterDown > 20 ? t("all_generations") : `${filterDown} ${t("gen_below")}`}</Text>
              </View>
            </View>
            <GradientButton testID="do-export-button" title={t("export")} icon="download" loading={exporting} onPress={doExport} />
          </Pressable>
        </Pressable>
      </Modal>

      <UpgradeModal visible={upgradeOpen} onClose={() => setUpgradeOpen(false)} limit={limit} />

      <Modal visible={filterOpen} transparent animationType="slide" onRequestClose={() => setFilterOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFilterOpen(false)}>
          <Pressable style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]} onPress={() => {}}>
            <Text style={styles.sheetTitle}>{t("filter_tree_view")}</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.brandTertiary, alignSelf: "flex-start", paddingHorizontal: 12, paddingVertical: 7, borderRadius: 999, marginBottom: 4 }}>
              <Feather name="target" size={14} color={colors.onBrandTertiary} />
              <Text style={{ fontFamily: fonts.medium, fontSize: 12, color: colors.onBrandTertiary }}>{t("current_center")}: {focusName ?? t("root_person")}</Text>
            </View>
            <View style={styles.stepperRow}>
              <Text style={styles.stepperLabel}>{t("gen_ancestors")}</Text>
              <View style={styles.stepper}>
                <Pressable style={styles.stepBtn} onPress={() => setFilterUp((v) => Math.max(0, v - 1))} testID="filter-up-minus">
                  <Feather name="minus" size={16} color={colors.onSurface} />
                </Pressable>
                <Text style={styles.stepVal}>{filterUp > 20 ? "∞" : filterUp}</Text>
                <Pressable style={styles.stepBtn} onPress={() => setFilterUp((v) => Math.min(10, v + 1))} testID="filter-up-plus">
                  <Feather name="plus" size={16} color={colors.onSurface} />
                </Pressable>
              </View>
            </View>
            <View style={styles.stepperRow}>
              <Text style={styles.stepperLabel}>{t("gen_descendants")}</Text>
              <View style={styles.stepper}>
                <Pressable style={styles.stepBtn} onPress={() => setFilterDown((v) => Math.max(0, v - 1))} testID="filter-down-minus">
                  <Feather name="minus" size={16} color={colors.onSurface} />
                </Pressable>
                <Text style={styles.stepVal}>{filterDown > 20 ? "∞" : filterDown}</Text>
                <Pressable style={styles.stepBtn} onPress={() => setFilterDown((v) => Math.min(10, v + 1))} testID="filter-down-plus">
                  <Feather name="plus" size={16} color={colors.onSurface} />
                </Pressable>
              </View>
            </View>
            <View style={{ flexDirection: "row", gap: 12 }}>
              <GradientButton
                testID="filter-show-all"
                variant="secondary"
                title={t("show_all")}
                onPress={() => { setFilterUp(99); setFilterDown(99); }}
                style={{ flex: 1 }}
              />
              <GradientButton
                testID="filter-apply"
                title={t("apply_filter")}
                onPress={() => setFilterOpen(false)}
                style={{ flex: 1 }}
              />
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}
