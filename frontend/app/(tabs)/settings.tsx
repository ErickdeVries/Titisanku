import { useEffect, useState } from "react";
import { View, Text, Pressable, TextInput, ScrollView, Switch, Platform } from "react-native";
import { Image } from "expo-image";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import * as DocumentPicker from "expo-document-picker";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getTree, getBackup, restoreBackup, createInvite, acceptInvite, listInvites, fileUrl } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { GradientButton } from "@/src/components/GradientButton";
import { ensureNotificationPermission, scheduleBirthdayReminders } from "@/src/notifications";
import { storage } from "@/src/utils/storage";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 20, paddingBottom: 12, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: fonts.bold, fontSize: 20, color: c.onSurface },
  profile: { flexDirection: "row", alignItems: "center", gap: 14, padding: 20 },
  avatar: { width: 56, height: 56, borderRadius: 999, overflow: "hidden", backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  avatarImg: { width: "100%", height: "100%" },
  name: { fontFamily: fonts.semibold, fontSize: 17, color: c.onSurface },
  email: { fontFamily: fonts.regular, fontSize: 13, color: c.muted },
  roleBadge: { alignSelf: "flex-start", marginTop: 4, backgroundColor: c.brandTertiary, paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999 },
  roleText: { fontFamily: fonts.semibold, fontSize: 11, color: c.onBrandTertiary },
  section: { paddingHorizontal: 20, marginTop: 20 },
  sectionTitle: { fontFamily: fonts.semibold, fontSize: 13, color: c.muted, marginBottom: 10, textTransform: "uppercase", letterSpacing: 0.5 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 16, overflow: "hidden" },
  rowItem: { flexDirection: "row", alignItems: "center", gap: 12, padding: 16 },
  rowTextWrap: { flex: 1 },
  rowLabel: { fontFamily: fonts.medium, fontSize: 15, color: c.onSurface },
  rowDesc: { fontFamily: fonts.regular, fontSize: 12, color: c.muted, marginTop: 2 },
  langToggle: { flexDirection: "row", backgroundColor: c.surfaceTertiary, borderRadius: 999, padding: 3 },
  langBtn: { paddingHorizontal: 16, paddingVertical: 6, borderRadius: 999 },
  langBtnActive: { backgroundColor: c.brandPrimary },
  langText: { fontFamily: fonts.semibold, fontSize: 13, color: c.muted },
  langTextActive: { color: c.onBrandPrimary },
  divider: { height: 1, backgroundColor: c.divider, marginLeft: 16 },
  inputRow: { padding: 16, gap: 10 },
  input: { backgroundColor: c.surfaceTertiary, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontFamily: fonts.regular, fontSize: 15, color: c.onSurface },
  msg: { fontFamily: fonts.medium, fontSize: 13, color: c.success, marginTop: 4 },
  err: { fontFamily: fonts.medium, fontSize: 13, color: c.error, marginTop: 4 },
  inviteItem: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 16, paddingVertical: 10 },
  inviteEmail: { fontFamily: fonts.regular, fontSize: 13, color: c.onSurfaceSecondary },
  inviteCode: { fontFamily: fonts.semibold, fontSize: 13, color: c.brandPrimary },
  logout: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, padding: 16, marginHorizontal: 20, marginTop: 24, borderRadius: 16, backgroundColor: c.surfaceTertiary },
  logoutText: { fontFamily: fonts.semibold, fontSize: 15, color: c.error },
}));

const REMINDER_KEY = "birthday_reminders_on";

export default function SettingsScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { lang, setLang, t } = useI18n();
  const { user, logout, refresh } = useAuth();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();

  const isAdmin = user?.role === "admin";
  const { data } = useQuery({ queryKey: ["tree"], queryFn: getTree });
  const { data: invites } = useQuery({ queryKey: ["invites"], queryFn: listInvites, enabled: isAdmin });

  const [reminders, setReminders] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteMsg, setInviteMsg] = useState("");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [joinCode, setJoinCode] = useState("");
  const [joinMsg, setJoinMsg] = useState("");
  const [joinErr, setJoinErr] = useState("");
  const [backupMsg, setBackupMsg] = useState("");
  const [restoreMsg, setRestoreMsg] = useState("");
  const [restoreBusy, setRestoreBusy] = useState(false);

  useEffect(() => {
    storage.getItem<boolean>(REMINDER_KEY, false).then((v) => setReminders(!!v));
  }, []);

  const toggleReminders = async (val: boolean) => {
    if (val) {
      const ok = await ensureNotificationPermission();
      if (!ok) {
        setReminders(false);
        return;
      }
      await scheduleBirthdayReminders(data?.people ?? []);
    }
    setReminders(val);
    storage.setItem(REMINDER_KEY, val);
  };

  const doBackup = async () => {
    setBackupMsg("");
    const dump = await getBackup();
    const json = JSON.stringify(dump, null, 2);
    const filename = `keturunanku_backup_${new Date().toISOString().slice(0, 10)}.json`;
    if (Platform.OS === "web") {
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setBackupMsg(t("saved"));
      return;
    }
    const uri = FileSystem.documentDirectory + filename;
    await FileSystem.writeAsStringAsync(uri, json);
    if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(uri, { mimeType: "application/json" });
    setBackupMsg(t("saved"));
  };

  const doRestore = async () => {
    setRestoreMsg("");
    const res = await DocumentPicker.getDocumentAsync({ type: "application/json", copyToCacheDirectory: true });
    if (res.canceled || !res.assets?.length) return;
    const uri = res.assets[0].uri;
    setRestoreBusy(true);
    try {
      let text: string;
      if (Platform.OS === "web") text = await (await fetch(uri)).text();
      else text = await FileSystem.readAsStringAsync(uri);
      const parsed = JSON.parse(text);
      if (!parsed || !Array.isArray(parsed.people)) {
        setRestoreMsg(t("restore_invalid"));
        return;
      }
      await restoreBackup({ people: parsed.people, relations: parsed.relations ?? [] });
      await qc.invalidateQueries({ queryKey: ["tree"] });
      setRestoreMsg(t("restore_success"));
    } catch {
      setRestoreMsg(t("restore_invalid"));
    } finally {
      setRestoreBusy(false);
    }
  };

  const sendInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviteBusy(true);
    setInviteMsg("");
    try {
      const res = await createInvite(inviteEmail.trim());
      setInviteMsg(`${t("invite_sent")} ${res.code}`);
      setInviteEmail("");
      qc.invalidateQueries({ queryKey: ["invites"] });
    } catch (e: any) {
      setInviteMsg(e.message || t("error_generic"));
    } finally {
      setInviteBusy(false);
    }
  };

  const doJoin = async () => {
    if (!joinCode.trim()) return;
    setJoinMsg("");
    setJoinErr("");
    try {
      await acceptInvite(joinCode.trim());
      await refresh();
      setJoinMsg(t("joined"));
      setJoinCode("");
    } catch (e: any) {
      setJoinErr(e.message || t("error_generic"));
    }
  };

  const roleLabel = user?.role === "admin" ? t("admin") : user?.role === "editor" ? t("editor") : t("viewer");
  const avatar = fileUrl(user?.picture);

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Text style={styles.title}>{t("settings")}</Text>
      </View>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 40 }}>
        <View style={styles.profile}>
          <View style={styles.avatar}>
            {user?.picture ? <Image source={{ uri: user.picture }} style={styles.avatarImg} contentFit="cover" /> : <Feather name="user" size={26} color={colors.muted} />}
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{user?.name}</Text>
            <Text style={styles.email}>{user?.email}</Text>
            <View style={styles.roleBadge}>
              <Text style={styles.roleText}>{roleLabel}</Text>
            </View>
          </View>
        </View>

        {/* Preferences */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("settings")}</Text>
          <View style={styles.card}>
            <View style={styles.rowItem}>
              <Feather name="globe" size={20} color={colors.onSurfaceSecondary} />
              <View style={styles.rowTextWrap}>
                <Text style={styles.rowLabel}>{t("language")}</Text>
              </View>
              <View style={styles.langToggle}>
                <Pressable style={[styles.langBtn, lang === "id" && styles.langBtnActive]} onPress={() => setLang("id")} testID="lang-id">
                  <Text style={[styles.langText, lang === "id" && styles.langTextActive]}>ID</Text>
                </Pressable>
                <Pressable style={[styles.langBtn, lang === "en" && styles.langBtnActive]} onPress={() => setLang("en")} testID="lang-en">
                  <Text style={[styles.langText, lang === "en" && styles.langTextActive]}>EN</Text>
                </Pressable>
              </View>
            </View>
            <View style={styles.divider} />
            <View style={styles.rowItem}>
              <Feather name="bell" size={20} color={colors.onSurfaceSecondary} />
              <View style={styles.rowTextWrap}>
                <Text style={styles.rowLabel}>{t("birthday_reminders")}</Text>
                <Text style={styles.rowDesc}>{t("birthday_reminders_desc")}</Text>
              </View>
              <Switch value={reminders} onValueChange={toggleReminders} trackColor={{ true: colors.brandPrimary }} testID="reminders-switch" />
            </View>
          </View>
        </View>

        {/* Backup */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("backup")}</Text>
          <View style={styles.card}>
            <Pressable style={styles.rowItem} onPress={doBackup} testID="backup-button">
              <Feather name="download-cloud" size={20} color={colors.onSurfaceSecondary} />
              <View style={styles.rowTextWrap}>
                <Text style={styles.rowLabel}>{t("backup")}</Text>
                <Text style={styles.rowDesc}>{t("backup_desc")}</Text>
              </View>
              <Feather name="chevron-right" size={20} color={colors.muted} />
            </Pressable>
            {isAdmin ? (
              <>
                <View style={styles.divider} />
                <Pressable style={styles.rowItem} onPress={doRestore} testID="restore-button">
                  <Feather name="upload-cloud" size={20} color={colors.onSurfaceSecondary} />
                  <View style={styles.rowTextWrap}>
                    <Text style={styles.rowLabel}>{t("restore")}</Text>
                    <Text style={styles.rowDesc}>{t("restore_desc")}</Text>
                  </View>
                  {restoreBusy ? (
                    <Feather name="loader" size={18} color={colors.muted} />
                  ) : (
                    <Feather name="chevron-right" size={20} color={colors.muted} />
                  )}
                </Pressable>
              </>
            ) : null}
          </View>
          {backupMsg ? <Text style={styles.msg}>{backupMsg}</Text> : null}
          {restoreMsg ? <Text style={restoreMsg === t("restore_success") ? styles.msg : styles.err}>{restoreMsg}</Text> : null}
        </View>

        {/* Collaboration */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("collaboration")}</Text>
          {isAdmin ? (
            <View style={styles.card}>
              <View style={styles.inputRow}>
                <Text style={styles.rowLabel}>{t("invite_email")}</Text>
                <TextInput
                  testID="invite-email-input"
                  style={styles.input}
                  placeholder={t("invite_placeholder")}
                  placeholderTextColor={colors.muted}
                  value={inviteEmail}
                  onChangeText={setInviteEmail}
                  autoCapitalize="none"
                  keyboardType="email-address"
                />
                <GradientButton testID="send-invite-button" title={t("send_invite")} icon="send" loading={inviteBusy} onPress={sendInvite} />
                {inviteMsg ? <Text style={styles.msg}>{inviteMsg}</Text> : null}
              </View>
              {invites && invites.length ? (
                <>
                  <View style={styles.divider} />
                  {invites.map((inv: any) => (
                    <View key={inv.id} style={styles.inviteItem}>
                      <Text style={styles.inviteEmail}>{inv.email}</Text>
                      <Text style={styles.inviteCode}>{inv.accepted ? "✓" : inv.code}</Text>
                    </View>
                  ))}
                </>
              ) : null}
            </View>
          ) : (
            <View style={styles.card}>
              <View style={styles.inputRow}>
                <Text style={styles.rowLabel}>{t("join_code")}</Text>
                <TextInput
                  testID="join-code-input"
                  style={styles.input}
                  placeholder={t("join_code_placeholder")}
                  placeholderTextColor={colors.muted}
                  value={joinCode}
                  onChangeText={setJoinCode}
                  autoCapitalize="characters"
                />
                <GradientButton testID="join-button" title={t("join")} icon="user-plus" onPress={doJoin} />
                {joinMsg ? <Text style={styles.msg}>{joinMsg}</Text> : null}
                {joinErr ? <Text style={styles.err}>{joinErr}</Text> : null}
              </View>
            </View>
          )}
        </View>

        <Pressable style={styles.logout} onPress={logout} testID="logout-button">
          <Feather name="log-out" size={18} color={colors.error} />
          <Text style={styles.logoutText}>{t("logout")}</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}
