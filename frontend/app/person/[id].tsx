import { useState } from "react";
import { View, Text, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getPerson, updatePerson, deletePerson, fileUrl } from "@/src/api";
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
  actions: { padding: 20, gap: 12 },
  deleteBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, padding: 16, borderRadius: 999, backgroundColor: c.surfaceTertiary },
  deleteText: { fontFamily: fonts.semibold, fontSize: 15, color: c.error },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
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

  const { data: person, isLoading } = useQuery({ queryKey: ["person", id], queryFn: () => getPerson(id) });

  const isAdmin = user?.role === "admin";
  const canEdit = user?.role === "admin" || user?.role === "editor";

  const save = async (v: PersonFormValue) => {
    setSaving(true);
    try {
      await updatePerson(id, {
        name: v.name,
        gender: v.gender,
        birth_date: v.birth_date,
        birth_place: v.birth_place,
        death_date: v.death_date,
        photo_url: v.photo_url,
        job: v.job,
        is_adopted: v.is_adopted,
        notes: v.notes,
      });
      await qc.invalidateQueries({ queryKey: ["person", id] });
      await qc.invalidateQueries({ queryKey: ["tree"] });
      setEditing(false);
    } catch (e) {
      console.log("save error", e);
    } finally {
      setSaving(false);
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

  const goAdd = (direction: string) => {
    if (!person) return;
    router.push(`/add-relative?focus_id=${person.id}&direction=${direction}&focus_name=${encodeURIComponent(person.name)}`);
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
    { key: "father", label: t("add_father"), icon: "arrow-up", color: colors.maleNode },
    { key: "mother", label: t("add_mother"), icon: "arrow-up", color: colors.femaleNode },
    { key: "spouse", label: t("add_spouse"), icon: "heart", color: colors.brandPrimary },
    { key: "child", label: t("add_child"), icon: "arrow-down", color: colors.success },
  ];

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.iconBtn} onPress={() => (editing ? setEditing(false) : router.back())} testID="detail-back">
          <Feather name={editing ? "x" : "chevron-left"} size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>{editing ? t("edit") : t("detail")}</Text>
        {canEdit && !editing ? (
          <Pressable style={styles.iconBtn} onPress={() => setEditing(true)} testID="edit-button">
            <Feather name="edit-2" size={17} color={colors.onSurface} />
          </Pressable>
        ) : (
          <View style={styles.iconBtn} />
        )}
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
        <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 40 }}>
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
                <Pressable key={d.key} style={styles.quickBtn} onPress={() => goAdd(d.key)} testID={`quick-${d.key}`}>
                  <View style={[styles.quickIcon, { backgroundColor: d.color }]}>
                    <Feather name={d.icon as any} size={20} color={colors.onBrandPrimary} />
                  </View>
                  <Text style={styles.quickLabel}>{d.label}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}

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
        </ScrollView>
      )}
    </View>
  );
}
