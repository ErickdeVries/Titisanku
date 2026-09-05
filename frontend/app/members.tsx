import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, Alert, Platform, Share } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Image } from "expo-image";
import * as Linking from "expo-linking";
import * as Clipboard from "expo-clipboard";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Shield, Trash2, Link2, Copy, Check } from "lucide-react-native";
import { fonts, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { useTree } from "@/src/tree-context";
import { getMembers, changeMemberRole, removeMember, createInviteLink, fileUrl, TreeMember } from "@/src/api";

const ROLES = ["admin", "editor", "viewer"] as const;

export default function MembersScreen() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { activeTreeId } = useTree();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["members", activeTreeId],
    queryFn: () => getMembers(activeTreeId!),
    enabled: !!activeTreeId,
  });

  const roleMut = useMutation({
    mutationFn: ({ uid, role }: { uid: string; role: string }) => changeMemberRole(activeTreeId!, uid, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members", activeTreeId] }),
  });
  const removeMut = useMutation({
    mutationFn: (uid: string) => removeMember(activeTreeId!, uid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members", activeTreeId] }),
  });

  const isAdmin = data?.role === "admin";
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const buildUrl = (token: string) =>
    Platform.OS === "web" && typeof window !== "undefined"
      ? `${window.location.origin}/invite/${token}`
      : Linking.createURL(`/invite/${token}`);

  const inviteMut = useMutation({
    mutationFn: () => createInviteLink(activeTreeId!),
    onSuccess: (r) => setInviteUrl(buildUrl(r.token)),
  });

  const copyLink = async () => {
    if (!inviteUrl) return;
    await Clipboard.setStringAsync(inviteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const shareLink = async () => {
    if (!inviteUrl) return;
    try {
      await Share.share({ message: inviteUrl });
    } catch {}
  };

  const cycleRole = (m: TreeMember) => {
    if (!isAdmin || m.is_owner) return;
    const idx = ROLES.indexOf(m.role);
    const next = ROLES[(idx + 1) % ROLES.length];
    roleMut.mutate({ uid: m.user_id, role: next });
  };

  const confirmRemove = (m: TreeMember) => {
    Alert.alert(t("remove"), `${m.name}?`, [
      { text: t("cancel"), style: "cancel" },
      { text: t("remove"), style: "destructive", onPress: () => removeMut.mutate(m.user_id) },
    ]);
  };

  return (
    <View style={[styles.root, { backgroundColor: colors.surface }]}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={() => router.back()} hitSlop={10}>
          <ArrowLeft size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={[styles.title, { color: colors.onSurface }]}>{t("manage_members")}</Text>
        <View style={{ width: 24 }} />
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10 }}>
          {isAdmin ? (
            <View style={[styles.inviteCard, { backgroundColor: colors.surfaceSecondary, borderColor: colors.border }]}>
              <View style={styles.inviteHead}>
                <Link2 size={18} color={colors.brandSecondary} />
                <Text style={[styles.inviteTitle, { color: colors.onSurface }]}>{t("invite_link")}</Text>
              </View>
              {inviteUrl ? (
                <>
                  <Text style={[styles.inviteUrl, { color: colors.muted, backgroundColor: colors.surfaceTertiary }]} numberOfLines={1}>
                    {inviteUrl}
                  </Text>
                  <View style={{ flexDirection: "row", gap: 10 }}>
                    <Pressable onPress={copyLink} style={[styles.inviteBtn, { backgroundColor: colors.brandTertiary }]} testID="copy-invite">
                      {copied ? <Check size={16} color={colors.onBrandTertiary} /> : <Copy size={16} color={colors.onBrandTertiary} />}
                      <Text style={[styles.inviteBtnText, { color: colors.onBrandTertiary }]}>{copied ? t("link_copied") : t("copy_link")}</Text>
                    </Pressable>
                    <Pressable onPress={shareLink} style={[styles.inviteBtn, { backgroundColor: colors.brandSecondary }]} testID="share-invite">
                      <Text style={[styles.inviteBtnText, { color: colors.onBrandSecondary }]}>{t("share_link")}</Text>
                    </Pressable>
                  </View>
                </>
              ) : (
                <Pressable
                  onPress={() => inviteMut.mutate()}
                  disabled={inviteMut.isPending}
                  style={[styles.inviteCreate, { backgroundColor: colors.brandPrimary, opacity: inviteMut.isPending ? 0.6 : 1 }]}
                  testID="create-invite-link"
                >
                  {inviteMut.isPending ? (
                    <ActivityIndicator color={colors.onBrandPrimary} />
                  ) : (
                    <Text style={[styles.inviteCreateText, { color: colors.onBrandPrimary }]}>{t("create_invite_link")}</Text>
                  )}
                </Pressable>
              )}
            </View>
          ) : null}
          <Text style={[styles.sub, { color: colors.muted }]}>
            {(data?.members.length ?? 0)} {t("members_count")}
          </Text>
          {data?.members.map((m) => (
            <View key={m.user_id} style={[styles.card, { backgroundColor: colors.surfaceSecondary }]}>
              <View style={[styles.avatar, { backgroundColor: colors.surfaceTertiary }]}>
                {m.picture ? (
                  <Image source={{ uri: fileUrl(m.picture) }} style={styles.avatarImg} contentFit="cover" />
                ) : (
                  <Text style={[styles.avatarInit, { color: colors.onSurfaceTertiary }]}>{m.name.charAt(0).toUpperCase()}</Text>
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[styles.name, { color: colors.onSurface }]} numberOfLines={1}>
                  {m.name}{m.is_owner ? ` · ${t("owner")}` : ""}
                </Text>
                <Text style={[styles.email, { color: colors.muted }]} numberOfLines={1}>{m.email}</Text>
              </View>
              <Pressable
                testID={`role-${m.user_id}`}
                onPress={() => cycleRole(m)}
                disabled={!isAdmin || m.is_owner}
                style={[styles.roleChip, { backgroundColor: colors.brandTertiary, opacity: !isAdmin || m.is_owner ? 0.6 : 1 }]}
              >
                <Shield size={12} color={colors.onBrandTertiary} />
                <Text style={[styles.roleText, { color: colors.onBrandTertiary }]}>{m.role}</Text>
              </Pressable>
              {isAdmin && !m.is_owner ? (
                <Pressable testID={`remove-${m.user_id}`} onPress={() => confirmRemove(m)} hitSlop={8} style={{ marginLeft: 8 }}>
                  <Trash2 size={18} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
          {isAdmin ? (
            <Text style={[styles.hint, { color: colors.muted }]}>Ketuk peran untuk mengubah (admin → editor → viewer).</Text>
          ) : null}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20, paddingBottom: 12 },
  title: { fontFamily: fonts.display, fontSize: 22 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  sub: { fontFamily: fonts.medium, fontSize: 13, marginBottom: 4 },
  card: { flexDirection: "row", alignItems: "center", gap: 12, borderRadius: 16, padding: 12 },
  avatar: { width: 42, height: 42, borderRadius: 999, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: 42, height: 42 },
  avatarInit: { fontFamily: fonts.bold, fontSize: 18 },
  name: { fontFamily: fonts.semibold, fontSize: 15 },
  email: { fontFamily: fonts.regular, fontSize: 12, marginTop: 1 },
  roleChip: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999 },
  roleText: { fontFamily: fonts.semibold, fontSize: 12, textTransform: "capitalize" },
  hint: { fontFamily: fonts.regular, fontSize: 12, textAlign: "center", marginTop: 8 },
  inviteCard: { borderRadius: 16, borderWidth: 1, padding: 16, gap: 12, marginBottom: 4 },
  inviteHead: { flexDirection: "row", alignItems: "center", gap: 8 },
  inviteTitle: { fontFamily: fonts.semibold, fontSize: 15 },
  inviteUrl: { fontFamily: fonts.regular, fontSize: 12, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10 },
  inviteBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderRadius: 12, paddingVertical: 12 },
  inviteBtnText: { fontFamily: fonts.semibold, fontSize: 13 },
  inviteCreate: { borderRadius: 12, paddingVertical: 14, alignItems: "center" },
  inviteCreateText: { fontFamily: fonts.semibold, fontSize: 15 },
});
