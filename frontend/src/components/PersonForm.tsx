import React, { useState } from "react";
import { Linking, Pressable, Text, TextInput, View } from "react-native";
import { Image } from "expo-image";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import * as ImagePicker from "expo-image-picker";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { fileUrl, uploadPhoto } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { GradientButton } from "./GradientButton";
import { DateField } from "./DateField";

export type PersonFormValue = {
  name: string;
  gender: string | null;
  birth_date: string | null;
  birth_place: string | null;
  death_date: string | null;
  photo_url: string | null;
  job: string | null;
  is_adopted: boolean;
  notes: string | null;
  marriage_date: string | null;
  divorce_date: string | null;
  is_divorced: boolean;
};

type Props = {
  initial?: Partial<PersonFormValue>;
  lockedGender?: "male" | "female";
  showAdopted?: boolean;
  showMarriageTabs?: boolean;
  submitLabel: string;
  submitting?: boolean;
  onSubmit: (v: PersonFormValue) => void;
};

const useStyles = makeStyles((c) => ({
  content: { padding: 20, paddingBottom: 40, gap: 18 },
  tabs: { flexDirection: "row", backgroundColor: c.surfaceTertiary, borderRadius: 12, padding: 4, gap: 4 },
  tab: { flex: 1, height: 40, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  tabActive: { backgroundColor: c.surface, shadowColor: "#0F172A", shadowOpacity: 0.06, shadowRadius: 4, elevation: 2 },
  tabText: { fontFamily: fonts.medium, fontSize: 13, color: c.muted },
  tabTextActive: { color: c.onSurface },
  label: { fontFamily: fonts.medium, fontSize: 13, color: c.onSurfaceSecondary, marginBottom: 6 },
  input: {
    backgroundColor: c.surfaceTertiary,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 14,
    fontFamily: fonts.regular,
    fontSize: 15,
    color: c.onSurface,
  },
  multiline: { minHeight: 90, textAlignVertical: "top" },
  genderRow: { flexDirection: "row", gap: 10 },
  genderBtn: {
    flex: 1,
    height: 50,
    borderRadius: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: c.surfaceTertiary,
  },
  genderText: { fontFamily: fonts.medium, fontSize: 14, color: c.onSurfaceSecondary },
  photoWrap: { alignItems: "center", gap: 10 },
  photoBtnRow: { flexDirection: "row", alignItems: "center", gap: 20 },
  photo: { width: 100, height: 100, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  photoImg: { width: "100%", height: "100%" },
  uploadBtn: { flexDirection: "row", alignItems: "center", gap: 6 },
  uploadText: { fontFamily: fonts.medium, fontSize: 13, color: c.brandSecondary },
  checkRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  checkbox: { width: 26, height: 26, borderRadius: 7, borderWidth: 2, borderColor: c.borderStrong, alignItems: "center", justifyContent: "center" },
  checkboxOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  checkLabel: { fontFamily: fonts.regular, fontSize: 15, color: c.onSurface, flex: 1 },
  dateBtn: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: c.surfaceTertiary, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 15 },
  dateText: { fontFamily: fonts.regular, fontSize: 15 },
  err: { fontFamily: fonts.regular, fontSize: 12, color: c.error, marginTop: 4 },
  sticky: { padding: 16, paddingBottom: 24, backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.divider },
  permNote: { fontFamily: fonts.regular, fontSize: 12, color: c.muted, textAlign: "center" },
}));

function Checkbox({ value, onToggle, label, testID }: { value: boolean; onToggle: () => void; label: string; testID?: string }) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <Pressable style={styles.checkRow} onPress={onToggle} testID={testID}>
      <View style={[styles.checkbox, value && styles.checkboxOn]}>
        {value ? <Feather name="check" size={16} color={colors.onBrandPrimary} /> : null}
      </View>
      <Text style={styles.checkLabel}>{label}</Text>
    </Pressable>
  );
}

export function PersonForm({ initial, lockedGender, showAdopted, showMarriageTabs, submitLabel, submitting, onSubmit }: Props) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();

  const [tab, setTab] = useState<"general" | "marriage" | "divorce">("general");
  const [name, setName] = useState(initial?.name ?? "");
  const [gender, setGender] = useState<string | null>(lockedGender ?? initial?.gender ?? null);
  const [birthDate, setBirthDate] = useState(initial?.birth_date ?? null);
  const [birthPlace, setBirthPlace] = useState(initial?.birth_place ?? "");
  const [job, setJob] = useState(initial?.job ?? "");
  const [deathDate, setDeathDate] = useState(initial?.death_date ?? null);
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [photoUrl, setPhotoUrl] = useState<string | null>(initial?.photo_url ?? null);
  const [isAdopted, setIsAdopted] = useState(initial?.is_adopted ?? false);
  const [marriageDate, setMarriageDate] = useState(initial?.marriage_date ?? null);
  const [divorceDate, setDivorceDate] = useState(initial?.divorce_date ?? null);
  const [isDivorced, setIsDivorced] = useState(initial?.is_divorced ?? false);
  const [uploading, setUploading] = useState(false);
  const [nameErr, setNameErr] = useState(false);
  const [permBlocked, setPermBlocked] = useState(false);

  const doUpload = async (uri: string) => {
    setUploading(true);
    try {
      const path = await uploadPhoto(uri);
      setPhotoUrl(path);
    } catch (e) {
      console.log("upload error", e);
    } finally {
      setUploading(false);
    }
  };

  const pickPhoto = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      setPermBlocked(!perm.canAskAgain);
      return;
    }
    setPermBlocked(false);
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.6,
    });
    if (res.canceled || !res.assets?.length) return;
    await doUpload(res.assets[0].uri);
  };

  const takePhoto = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      setPermBlocked(!perm.canAskAgain);
      return;
    }
    setPermBlocked(false);
    const res = await ImagePicker.launchCameraAsync({
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.6,
    });
    if (res.canceled || !res.assets?.length) return;
    await doUpload(res.assets[0].uri);
  };

  const submit = () => {
    if (!name.trim()) {
      setNameErr(true);
      setTab("general");
      return;
    }
    onSubmit({
      name: name.trim(),
      gender,
      birth_date: birthDate,
      birth_place: birthPlace || null,
      death_date: deathDate,
      photo_url: photoUrl,
      job: job || null,
      is_adopted: isAdopted,
      notes: notes || null,
      marriage_date: marriageDate,
      divorce_date: divorceDate,
      is_divorced: isDivorced,
    });
  };

  const preview = fileUrl(photoUrl);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAwareScrollView bottomOffset={90} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {showMarriageTabs ? (
          <View style={styles.tabs}>
            {(["general", "marriage", "divorce"] as const).map((tb) => (
              <Pressable key={tb} style={[styles.tab, tab === tb && styles.tabActive]} onPress={() => setTab(tb)} testID={`form-tab-${tb}`}>
                <Text style={[styles.tabText, tab === tb && styles.tabTextActive]}>
                  {tb === "general" ? t("general") : tb === "marriage" ? t("marriage") : t("divorce")}
                </Text>
              </Pressable>
            ))}
          </View>
        ) : null}

        {tab === "general" ? (
          <>
            <View style={styles.photoWrap}>
              <Pressable style={styles.photo} onPress={pickPhoto} testID="photo-picker">
                {preview ? (
                  <Image source={{ uri: preview }} style={styles.photoImg} contentFit="cover" />
                ) : (
                  <Feather name="camera" size={28} color={colors.muted} />
                )}
              </Pressable>
              <View style={styles.photoBtnRow}>
                <Pressable style={styles.uploadBtn} onPress={pickPhoto}>
                  <Feather name="upload" size={14} color={colors.brandSecondary} />
                  <Text style={styles.uploadText}>{uploading ? "..." : t("upload_photo")}</Text>
                </Pressable>
                <Pressable style={styles.uploadBtn} onPress={takePhoto} testID="photo-camera">
                  <Feather name="camera" size={14} color={colors.brandSecondary} />
                  <Text style={styles.uploadText}>{t("take_photo")}</Text>
                </Pressable>
              </View>
              {permBlocked ? (
                <Pressable onPress={() => Linking.openSettings()}>
                  <Text style={styles.permNote}>{t("upload_photo")} · Settings</Text>
                </Pressable>
              ) : null}
            </View>

            <View>
              <Text style={styles.label}>{t("name")}</Text>
              <TextInput
                testID="input-name"
                style={styles.input}
                value={name}
                onChangeText={(v) => {
                  setName(v);
                  setNameErr(false);
                }}
                placeholder={t("name")}
                placeholderTextColor={colors.muted}
              />
              {nameErr ? <Text style={styles.err}>{t("name")} {t("required")}</Text> : null}
            </View>

            {!lockedGender ? (
              <View>
                <Text style={styles.label}>{t("gender")}</Text>
                <View style={styles.genderRow}>
                  <Pressable
                    testID="gender-male"
                    style={[styles.genderBtn, gender === "male" && { backgroundColor: colors.maleNode }]}
                    onPress={() => setGender("male")}
                  >
                    <Feather name="user" size={16} color={gender === "male" ? colors.onBrandSecondary : colors.onSurfaceSecondary} />
                    <Text style={[styles.genderText, gender === "male" && { color: colors.onBrandSecondary }]}>{t("male")}</Text>
                  </Pressable>
                  <Pressable
                    testID="gender-female"
                    style={[styles.genderBtn, gender === "female" && { backgroundColor: colors.femaleNode }]}
                    onPress={() => setGender("female")}
                  >
                    <Feather name="user" size={16} color={gender === "female" ? colors.onError : colors.onSurfaceSecondary} />
                    <Text style={[styles.genderText, gender === "female" && { color: colors.onError }]}>{t("female")}</Text>
                  </Pressable>
                </View>
              </View>
            ) : null}

            <View>
              <Text style={styles.label}>{t("birth_date")}</Text>
              <DateField value={birthDate} onChange={setBirthDate} testID="input-birth-date" />
            </View>
            <View>
              <Text style={styles.label}>{t("birth_place")}</Text>
              <TextInput testID="input-birth-place" style={styles.input} value={birthPlace} onChangeText={setBirthPlace} placeholder={t("birth_place")} placeholderTextColor={colors.muted} />
            </View>
            <View>
              <Text style={styles.label}>{t("job")}</Text>
              <TextInput testID="input-job" style={styles.input} value={job} onChangeText={setJob} placeholder={t("job")} placeholderTextColor={colors.muted} />
            </View>
            <View>
              <Text style={styles.label}>{t("death_date")}</Text>
              <DateField value={deathDate} onChange={setDeathDate} testID="input-death-date" />
            </View>
            <View>
              <Text style={styles.label}>{t("notes")}</Text>
              <TextInput testID="input-notes" style={[styles.input, styles.multiline]} value={notes} onChangeText={setNotes} placeholder={t("notes")} placeholderTextColor={colors.muted} multiline />
            </View>
            {showAdopted ? <Checkbox testID="check-adopted" value={isAdopted} onToggle={() => setIsAdopted((v) => !v)} label={t("adopted_child")} /> : null}
          </>
        ) : null}

        {tab === "marriage" ? (
          <View>
            <Text style={styles.label}>{t("marriage_date")}</Text>
            <DateField value={marriageDate} onChange={setMarriageDate} testID="input-marriage-date" />
          </View>
        ) : null}

        {tab === "divorce" ? (
          <View style={{ gap: 18 }}>
            <Checkbox testID="check-divorced" value={isDivorced} onToggle={() => setIsDivorced((v) => !v)} label={t("is_divorced")} />
            {isDivorced ? (
              <View>
                <Text style={styles.label}>{t("divorce_date")}</Text>
                <DateField value={divorceDate} onChange={setDivorceDate} testID="input-divorce-date" />
              </View>
            ) : null}
          </View>
        ) : null}
      </KeyboardAwareScrollView>

      <KeyboardStickyView>
        <View style={styles.sticky}>
          <GradientButton testID="form-submit" title={submitLabel} onPress={submit} loading={submitting} />
        </View>
      </KeyboardStickyView>
    </View>
  );
}
