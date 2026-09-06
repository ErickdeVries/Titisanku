import { useMemo, useState } from "react";
import { View, Text, Pressable } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { addRelative, getTree } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { PersonForm, PersonFormValue } from "@/src/components/PersonForm";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  closeBtn: { width: 36, height: 36, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.bold, fontSize: 17, color: c.onSurface },
  sub: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  pickerWrap: { paddingHorizontal: 16, paddingTop: 14, paddingBottom: 4 },
  pickerLabel: { fontFamily: fonts.semibold, fontSize: 13, color: c.onSurface, marginBottom: 8 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: c.surfaceTertiary, borderWidth: 1, borderColor: c.divider },
  chipActive: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  chipText: { fontFamily: fonts.medium, fontSize: 13, color: c.onSurfaceSecondary },
  chipTextActive: { color: c.onBrandPrimary },
}));

export default function AddRelative() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { focus_id, direction, focus_name, sib } = useLocalSearchParams<{ focus_id: string; direction: string; focus_name: string; sib?: string }>();

  const [submitting, setSubmitting] = useState(false);
  const [otherParent, setOtherParent] = useState<string | null>(null);

  const isChild = direction === "child";
  const { data: tree } = useQuery({ queryKey: ["tree"], queryFn: getTree, enabled: isChild });
  const spouses = useMemo(() => {
    if (!isChild || !tree) return [] as { id: string; name: string }[];
    const rels = tree.relations.filter(
      (r) => (r.relation_type === "spouse" || r.relation_type === "divorced") && (r.person_id === focus_id || r.related_person_id === focus_id),
    );
    const ids = rels.map((r) => (r.person_id === focus_id ? r.related_person_id : r.person_id));
    return ids
      .map((id) => tree.people.find((p) => p.id === id))
      .filter((p): p is NonNullable<typeof p> => !!p)
      .map((p) => ({ id: p.id, name: p.name }));
  }, [isChild, tree, focus_id]);

  const dirLabel =
    direction === "father"
      ? t("add_father")
      : direction === "mother"
        ? t("add_mother")
        : direction === "spouse"
          ? t("add_spouse")
          : direction === "sibling"
            ? sib === "older"
              ? t("add_older_sibling")
              : sib === "younger"
                ? t("add_younger_sibling")
                : t("add_sibling")
            : t("add_child");

  const onSubmit = async (v: PersonFormValue) => {
    setSubmitting(true);
    try {
      await addRelative({
        focus_id,
        direction,
        person: {
          name: v.name,
          gender: v.gender,
          birth_date: v.birth_date,
          birth_place: v.birth_place,
          death_date: v.death_date,
          photo_url: v.photo_url,
          job: v.job,
          is_adopted: v.is_adopted,
          notes: v.notes,
        },
        marriage_date: v.marriage_date,
        divorce_date: v.divorce_date,
        is_divorced: v.is_divorced,
        other_parent_id: isChild && spouses.length >= 2 ? otherParent : undefined,
      });
      await qc.invalidateQueries({ queryKey: ["tree"] });
      router.back();
    } catch (e) {
      console.log("add relative error", e);
      setSubmitting(false);
    }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.closeBtn} onPress={() => router.back()} testID="close-modal">
          <Feather name="x" size={20} color={colors.onSurface} />
        </Pressable>
        <View>
          <Text style={styles.title}>
            {t("add")} {dirLabel}
          </Text>
          <Text style={styles.sub}>
            {t("add_relative_to")} {focus_name}
          </Text>
        </View>
      </View>
      {isChild && spouses.length >= 2 ? (
        <View style={styles.pickerWrap}>
          <Text style={styles.pickerLabel}>{t("choose_other_parent")}</Text>
          <View style={styles.chips}>
            {spouses.map((s) => (
              <Pressable
                key={s.id}
                onPress={() => setOtherParent(s.id)}
                style={[styles.chip, otherParent === s.id && styles.chipActive]}
                testID={`other-parent-${s.id}`}
              >
                <Text style={[styles.chipText, otherParent === s.id && styles.chipTextActive]}>{s.name}</Text>
              </Pressable>
            ))}
            <Pressable
              onPress={() => setOtherParent(null)}
              style={[styles.chip, otherParent === null && styles.chipActive]}
              testID="other-parent-none"
            >
              <Text style={[styles.chipText, otherParent === null && styles.chipTextActive]}>{t("unknown_parent")}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
      <PersonForm
        lockedGender={direction === "father" ? "male" : direction === "mother" ? "female" : undefined}
        showAdopted={direction === "child"}
        showMarriageTabs={direction === "spouse"}
        submitLabel={t("save")}
        submitting={submitting}
        onSubmit={onSubmit}
      />
    </View>
  );
}
