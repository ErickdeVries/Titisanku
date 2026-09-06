import { useState } from "react";
import { View, Text, Pressable, TextInput, ScrollView, ActivityIndicator, Alert } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useMutation } from "@tanstack/react-query";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { submitFeedback } from "@/src/api";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  backBtn: { width: 36, height: 36, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  label: { fontFamily: fonts.medium, fontSize: 13, color: c.muted, marginBottom: 10, marginTop: 6 },
  chips: { flexDirection: "row", gap: 10, marginBottom: 20 },
  chip: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 999, borderWidth: 1.5, borderColor: c.border },
  chipOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  chipText: { fontFamily: fonts.semibold, fontSize: 13, color: c.onSurfaceSecondary },
  chipTextOn: { color: c.onBrandPrimary },
  input: { backgroundColor: c.surfaceSecondary, borderColor: c.border, borderWidth: 1, borderRadius: 14, padding: 16, minHeight: 140, textAlignVertical: "top", fontFamily: fonts.regular, fontSize: 15, color: c.onSurface },
  send: { height: 52, borderRadius: 16, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: 20, flexDirection: "row", gap: 8 },
  sendText: { fontFamily: fonts.semibold, fontSize: 16, color: c.onBrandPrimary },
}));

export default function FeedbackScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [category, setCategory] = useState("idea");
  const [message, setMessage] = useState("");

  const cats = [
    { id: "bug", label: t("feedback_cat_bug"), icon: "alert-circle" as const },
    { id: "idea", label: t("feedback_cat_idea"), icon: "zap" as const },
    { id: "other", label: t("feedback_cat_other"), icon: "message-circle" as const },
  ];

  const mut = useMutation({
    mutationFn: () => submitFeedback(message.trim(), category),
    onSuccess: () => {
      Alert.alert(t("send_feedback"), t("feedback_sent"));
      router.back();
    },
    onError: () => Alert.alert(t("error_generic")),
  });

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.backBtn} onPress={() => router.back()} hitSlop={8} testID="feedback-back">
          <Feather name="chevron-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("send_feedback")}</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: 20 }} keyboardShouldPersistTaps="handled">
        <Text style={styles.label}>{t("feedback_desc")}</Text>
        <View style={styles.chips}>
          {cats.map((c) => {
            const on = category === c.id;
            return (
              <Pressable key={c.id} style={[styles.chip, on && styles.chipOn]} onPress={() => setCategory(c.id)} testID={`feedback-cat-${c.id}`}>
                <Feather name={c.icon} size={14} color={on ? colors.onBrandPrimary : colors.onSurfaceSecondary} />
                <Text style={[styles.chipText, on && styles.chipTextOn]}>{c.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <TextInput
          testID="feedback-input"
          style={styles.input}
          placeholder={t("feedback_placeholder")}
          placeholderTextColor={colors.muted}
          value={message}
          onChangeText={setMessage}
          multiline
        />
        <Pressable
          testID="feedback-send"
          style={[styles.send, { opacity: !message.trim() || mut.isPending ? 0.6 : 1 }]}
          disabled={!message.trim() || mut.isPending}
          onPress={() => mut.mutate()}
        >
          {mut.isPending ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <>
              <Feather name="send" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.sendText}>{t("send")}</Text>
            </>
          )}
        </Pressable>
      </ScrollView>
    </View>
  );
}
