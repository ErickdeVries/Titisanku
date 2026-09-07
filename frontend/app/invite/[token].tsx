import { useState } from "react";
import { View, Text, Pressable, StyleSheet, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { Users, UserPlus, Check } from "lucide-react-native";
import { fonts, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { useAuth } from "@/src/auth";
import { useTree } from "@/src/tree-context";
import { getInviteInfo, acceptInviteLink } from "@/src/api";
import { storage } from "@/src/utils/storage";

export default function InviteScreen() {
  const { colors, gradient } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token: string }>();
  const { user, login, signingIn } = useAuth();
  const { refreshTrees, setActive } = useTree();
  const [busy, setBusy] = useState(false);

  const { data: info, isLoading } = useQuery({
    queryKey: ["invite", token],
    queryFn: () => getInviteInfo(token),
    enabled: !!user && !!token,
    retry: false,
  });

  const startLogin = async () => {
    await storage.setItem("pending_invite", token);
    await login();
  };

  const join = async () => {
    setBusy(true);
    try {
      const r = await acceptInviteLink(token);
      await refreshTrees();
      await setActive(r.tree_id);
      router.replace("/(tabs)");
    } catch (e) {
      console.log("accept invite error", e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={[styles.root, { backgroundColor: colors.surface }]}>
      <View style={styles.content}>
        <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.badge}>
          <Users size={40} color="#FFFFFF" />
        </LinearGradient>

        {!user ? (
          <>
            <Text style={[styles.title, { color: colors.onSurface }]}>Titisanku</Text>
            <Text style={[styles.desc, { color: colors.muted }]}>{t("login_to_continue")}</Text>
            <Pressable onPress={startLogin} disabled={signingIn} style={{ width: "100%" }} testID="invite-login">
              <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.cta}>
                {signingIn ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.ctaText}>{t("login_to_continue")}</Text>}
              </LinearGradient>
            </Pressable>
          </>
        ) : isLoading ? (
          <ActivityIndicator size="large" color={colors.brandPrimary} style={{ marginTop: 20 }} />
        ) : !info ? (
          <>
            <Text style={[styles.title, { color: colors.onSurface }]}>Oops</Text>
            <Text style={[styles.desc, { color: colors.muted }]}>Undangan tidak valid atau sudah tidak aktif.</Text>
            <Pressable onPress={() => router.replace("/(tabs)")} style={[styles.secondary, { borderColor: colors.border }]}>
              <Text style={[styles.secondaryText, { color: colors.onSurface }]}>Kembali</Text>
            </Pressable>
          </>
        ) : (
          <>
            <Text style={[styles.desc, { color: colors.muted }]}>
              <Text style={{ fontFamily: fonts.semibold, color: colors.onSurface }}>{info.inviter_name}</Text> {t("invited_by")}
            </Text>
            <Text style={[styles.title, { color: colors.onSurface }]} numberOfLines={2}>{info.tree_name}</Text>

            {info.already_member ? (
              <Text style={[styles.desc, { color: colors.success }]}>{t("already_member_msg")}</Text>
            ) : null}

            <Pressable onPress={join} disabled={busy} style={{ width: "100%", marginTop: 8 }} testID="invite-join">
              <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.cta}>
                {busy ? (
                  <ActivityIndicator color="#FFFFFF" />
                ) : (
                  <>
                    {info.already_member ? <Check size={18} color="#FFFFFF" /> : <UserPlus size={18} color="#FFFFFF" />}
                    <Text style={styles.ctaText}>{info.already_member ? t("open_detail") : t("join_as_editor")}</Text>
                  </>
                )}
              </LinearGradient>
            </Pressable>

            <Pressable onPress={() => router.replace("/(tabs)")} style={[styles.secondary, { borderColor: colors.border }]} testID="invite-cancel">
              <Text style={[styles.secondaryText, { color: colors.onSurfaceSecondary }]}>{t("cancel")}</Text>
            </Pressable>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, alignItems: "center", justifyContent: "center", padding: 28 },
  content: { alignItems: "center", gap: 14, width: "100%", maxWidth: 420 },
  badge: { width: 88, height: 88, borderRadius: 999, alignItems: "center", justifyContent: "center", marginBottom: 8 },
  title: { fontFamily: fonts.display, fontSize: 26, textAlign: "center" },
  desc: { fontFamily: fonts.regular, fontSize: 15, textAlign: "center", lineHeight: 21 },
  cta: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 54, borderRadius: 16 },
  ctaText: { fontFamily: fonts.semibold, fontSize: 16, color: "#FFFFFF" },
  secondary: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 52, borderRadius: 16, borderWidth: 1.5, width: "100%", marginTop: 4 },
  secondaryText: { fontFamily: fonts.semibold, fontSize: 15 },
});
