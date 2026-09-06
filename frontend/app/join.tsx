import { useState } from "react";
import {
  View, Text, Pressable, StyleSheet, TextInput, ActivityIndicator, ScrollView, Linking, Alert,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { CameraView, useCameraPermissions } from "expo-camera";
import { ArrowLeft, Link2, Search, ScanLine, Users, Check, Clock } from "lucide-react-native";
import { fonts, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { useTree } from "@/src/tree-context";
import { acceptInviteLink, searchTrees, requestJoin, PublicTree } from "@/src/api";

type Tab = "link" | "search" | "scan";

export default function JoinScreen() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { refreshTrees, setActive } = useTree();
  const [tab, setTab] = useState<Tab>("link");

  const TABS: { key: Tab; label: string; icon: any }[] = [
    { key: "link", label: t("tab_link"), icon: Link2 },
    { key: "search", label: t("tab_search"), icon: Search },
    { key: "scan", label: t("tab_scan"), icon: ScanLine },
  ];

  // Parse an invite token from a pasted link or raw code.
  const tokenFrom = (raw: string) => {
    const s = raw.trim();
    const m = s.match(/invite\/([A-Za-z0-9_-]+)/);
    return m ? m[1] : s;
  };

  const acceptToken = async (token: string) => {
    const r = await acceptInviteLink(token);
    await refreshTrees();
    await setActive(r.tree_id);
    router.replace("/(tabs)");
  };

  return (
    <View style={[styles.root, { backgroundColor: colors.surface }]}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={() => router.back()} hitSlop={10}>
          <ArrowLeft size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={[styles.title, { color: colors.onSurface }]}>{t("join_tree")}</Text>
        <View style={{ width: 24 }} />
      </View>

      <View style={[styles.tabs, { backgroundColor: colors.surfaceTertiary }]}>
        {TABS.map(({ key, label, icon: Icon }) => {
          const active = tab === key;
          return (
            <Pressable
              key={key}
              testID={`join-tab-${key}`}
              onPress={() => setTab(key)}
              style={[styles.tab, active && { backgroundColor: colors.surfaceSecondary }]}
            >
              <Icon size={16} color={active ? colors.brandSecondary : colors.muted} />
              <Text style={[styles.tabText, { color: active ? colors.brandSecondary : colors.muted }]}>{label}</Text>
            </Pressable>
          );
        })}
      </View>

      {tab === "link" ? (
        <LinkTab acceptToken={(tk) => acceptToken(tokenFrom(tk))} />
      ) : tab === "search" ? (
        <SearchTab />
      ) : (
        <ScanTab onToken={(tk) => acceptToken(tk)} />
      )}
    </View>
  );
}

// ---------------- Link / Code ----------------
function LinkTab({ acceptToken }: { acceptToken: (raw: string) => Promise<void> }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const [val, setVal] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    if (!val.trim()) return;
    setBusy(true);
    setErr("");
    try {
      await acceptToken(val);
    } catch {
      setErr(t("invalid_invite"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
      <Text style={[styles.hint, { color: colors.muted }]}>{t("paste_link_hint")}</Text>
      <TextInput
        testID="join-link-input"
        value={val}
        onChangeText={setVal}
        placeholder={t("enter_code_or_link")}
        placeholderTextColor={colors.muted}
        autoCapitalize="none"
        autoCorrect={false}
        style={[styles.input, { backgroundColor: colors.surfaceSecondary, color: colors.onSurface, borderColor: colors.border }]}
      />
      {err ? <Text style={[styles.err, { color: colors.error }]}>{err}</Text> : null}
      <Pressable
        testID="join-link-submit"
        onPress={submit}
        disabled={busy || !val.trim()}
        style={[styles.primary, { backgroundColor: colors.brandPrimary, opacity: busy || !val.trim() ? 0.6 : 1 }]}
      >
        {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={[styles.primaryText, { color: colors.onBrandPrimary }]}>{t("join")}</Text>}
      </Pressable>
    </ScrollView>
  );
}

// ---------------- Search public trees ----------------
function SearchTab() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<PublicTree[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  const runSearch = async (text: string) => {
    setQ(text);
    if (text.trim().length < 2) {
      setResults(null);
      return;
    }
    setLoading(true);
    try {
      setResults(await searchTrees(text.trim()));
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const join = async (tr: PublicTree) => {
    try {
      await requestJoin(tr.id);
      setPendingIds((s) => new Set(s).add(tr.id));
      Alert.alert(t("request_join"), t("join_request_sent"));
    } catch {
      Alert.alert(t("error_generic"));
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
      <TextInput
        testID="join-search-input"
        value={q}
        onChangeText={runSearch}
        placeholder={t("search_trees_placeholder")}
        placeholderTextColor={colors.muted}
        style={[styles.input, { backgroundColor: colors.surfaceSecondary, color: colors.onSurface, borderColor: colors.border }]}
      />
      {loading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 20 }} />
      ) : results === null ? (
        <Text style={[styles.hint, { color: colors.muted, marginTop: 8 }]}>{t("search_trees_hint")}</Text>
      ) : results.length === 0 ? (
        <Text style={[styles.hint, { color: colors.muted, marginTop: 8 }]}>{t("no_public_trees")}</Text>
      ) : (
        <View style={{ gap: 10, marginTop: 4 }}>
          {results.map((tr) => {
            const pending = tr.pending || pendingIds.has(tr.id);
            return (
              <View key={tr.id} style={[styles.card, { backgroundColor: colors.surfaceSecondary, borderColor: colors.border }]}>
                <View style={[styles.cardIcon, { backgroundColor: colors.brandTertiary }]}>
                  <Users size={20} color={colors.onBrandTertiary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.cardName, { color: colors.onSurface }]} numberOfLines={1}>{tr.name}</Text>
                  <Text style={[styles.cardMeta, { color: colors.muted }]} numberOfLines={1}>
                    {tr.owner_name} · {tr.member_count} {t("members_count")}
                  </Text>
                </View>
                {tr.is_member ? (
                  <View style={[styles.statusChip, { backgroundColor: colors.brandTertiary }]}>
                    <Check size={13} color={colors.onBrandTertiary} />
                    <Text style={[styles.statusText, { color: colors.onBrandTertiary }]}>{t("already_joined")}</Text>
                  </View>
                ) : pending ? (
                  <View style={[styles.statusChip, { backgroundColor: colors.surfaceTertiary }]}>
                    <Clock size={13} color={colors.muted} />
                    <Text style={[styles.statusText, { color: colors.muted }]}>{t("request_pending")}</Text>
                  </View>
                ) : (
                  <Pressable
                    testID={`join-request-${tr.id}`}
                    onPress={() => join(tr)}
                    style={[styles.joinBtn, { backgroundColor: colors.brandPrimary }]}
                  >
                    <Text style={[styles.joinBtnText, { color: colors.onBrandPrimary }]}>{t("request_join")}</Text>
                  </Pressable>
                )}
              </View>
            );
          })}
        </View>
      )}
    </ScrollView>
  );
}

// ---------------- QR Scan ----------------
function ScanTab({ onToken }: { onToken: (token: string) => Promise<void> }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const [permission, requestPermission] = useCameraPermissions();
  const [handled, setHandled] = useState(false);

  const handleScan = async ({ data }: { data: string }) => {
    if (handled) return;
    setHandled(true);
    const s = (data || "").trim();
    const m = s.match(/invite\/([A-Za-z0-9_-]+)/);
    try {
      if (m) {
        await onToken(m[1]);
      } else if (s.startsWith("tree_")) {
        await requestJoin(s);
        Alert.alert(t("request_join"), t("join_request_sent"));
        setTimeout(() => setHandled(false), 1200);
      } else {
        // Fallback: try the raw string as an invite token.
        await onToken(s);
      }
    } catch {
      Alert.alert(t("invalid_qr"));
      setTimeout(() => setHandled(false), 1200);
    }
  };

  if (!permission) {
    return <View style={styles.body}><ActivityIndicator color={colors.brandPrimary} /></View>;
  }

  if (!permission.granted) {
    return (
      <View style={[styles.body, { alignItems: "center", justifyContent: "center", flex: 1 }]}>
        <View style={[styles.cardIcon, { backgroundColor: colors.brandTertiary, width: 60, height: 60, borderRadius: 20 }]}>
          <ScanLine size={28} color={colors.onBrandTertiary} />
        </View>
        <Text style={[styles.permTitle, { color: colors.onSurface }]}>{t("camera_permission_title")}</Text>
        <Text style={[styles.hint, { color: colors.muted, textAlign: "center" }]}>{t("camera_permission_desc")}</Text>
        {permission.canAskAgain ? (
          <Pressable testID="grant-camera" onPress={requestPermission} style={[styles.primary, { backgroundColor: colors.brandPrimary, width: "100%" }]}>
            <Text style={[styles.primaryText, { color: colors.onBrandPrimary }]}>{t("grant_camera")}</Text>
          </Pressable>
        ) : (
          <Pressable testID="open-settings" onPress={() => Linking.openSettings()} style={[styles.primary, { backgroundColor: colors.brandSecondary, width: "100%" }]}>
            <Text style={[styles.primaryText, { color: colors.onBrandSecondary }]}>{t("open_settings")}</Text>
          </Pressable>
        )}
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }}>
      <CameraView
        style={{ flex: 1 }}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
        onBarcodeScanned={handleScan}
      />
      <View style={styles.scanOverlay} pointerEvents="none">
        <View style={[styles.scanFrame, { borderColor: colors.brandPrimary }]} />
      </View>
      <View style={[styles.scanHintBar, { backgroundColor: colors.surface }]}>
        <Text style={[styles.hint, { color: colors.muted, textAlign: "center" }]}>{t("scan_qr_hint")}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20, paddingBottom: 12 },
  title: { fontFamily: fonts.display, fontSize: 22 },
  tabs: { flexDirection: "row", marginHorizontal: 16, borderRadius: 14, padding: 4, gap: 4 },
  tab: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 10, borderRadius: 10 },
  tabText: { fontFamily: fonts.semibold, fontSize: 13 },
  body: { padding: 20, gap: 14 },
  hint: { fontFamily: fonts.regular, fontSize: 14, lineHeight: 20 },
  input: { borderRadius: 14, borderWidth: 1, paddingHorizontal: 16, paddingVertical: 14, fontFamily: fonts.regular, fontSize: 15 },
  err: { fontFamily: fonts.medium, fontSize: 13 },
  primary: { height: 52, borderRadius: 16, alignItems: "center", justifyContent: "center", marginTop: 6 },
  primaryText: { fontFamily: fonts.semibold, fontSize: 16 },
  card: { flexDirection: "row", alignItems: "center", gap: 12, borderRadius: 16, borderWidth: 1, padding: 12 },
  cardIcon: { width: 42, height: 42, borderRadius: 12, alignItems: "center", justifyContent: "center", marginBottom: 10 },
  cardName: { fontFamily: fonts.semibold, fontSize: 15 },
  cardMeta: { fontFamily: fonts.regular, fontSize: 12, marginTop: 2 },
  joinBtn: { paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10 },
  joinBtnText: { fontFamily: fonts.semibold, fontSize: 13 },
  statusChip: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 10 },
  statusText: { fontFamily: fonts.medium, fontSize: 12 },
  permTitle: { fontFamily: fonts.semibold, fontSize: 17, marginTop: 8, marginBottom: 4 },
  scanOverlay: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center" },
  scanFrame: { width: 240, height: 240, borderWidth: 3, borderRadius: 24 },
  scanHintBar: { position: "absolute", bottom: 0, left: 0, right: 0, padding: 20 },
});
