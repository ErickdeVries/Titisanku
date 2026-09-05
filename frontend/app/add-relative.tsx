import { useState } from "react";
import { View, Text, Pressable } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { addRelative } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { PersonForm, PersonFormValue } from "@/src/components/PersonForm";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  closeBtn: { width: 36, height: 36, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.bold, fontSize: 17, color: c.onSurface },
  sub: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
}));

export default function AddRelative() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { focus_id, direction, focus_name } = useLocalSearchParams<{ focus_id: string; direction: string; focus_name: string }>();

  const [submitting, setSubmitting] = useState(false);

  const dirLabel =
    direction === "father" ? t("add_father") : direction === "mother" ? t("add_mother") : direction === "spouse" ? t("add_spouse") : t("add_child");

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
