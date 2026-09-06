import { useState } from "react";
import { View, Text, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery } from "@tanstack/react-query";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { adminOverview, adminUsers, adminFeedback } from "@/src/api";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  backBtn: { width: 36, height: 36, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  tabs: { flexDirection: "row", margin: 16, backgroundColor: c.surfaceTertiary, borderRadius: 14, padding: 4, gap: 4 },
  tab: { flex: 1, alignItems: "center", paddingVertical: 10, borderRadius: 10 },
  tabOn: { backgroundColor: c.surfaceSecondary },
  tabText: { fontFamily: fonts.semibold, fontSize: 13, color: c.muted },
  tabTextOn: { color: c.brandSecondary },
  sectionTitle: { fontFamily: fonts.semibold, fontSize: 15, color: c.onSurface, marginTop: 20, marginBottom: 10 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  stat: { width: "47%", backgroundColor: c.surfaceSecondary, borderRadius: 16, padding: 14, borderWidth: 1, borderColor: c.border },
  statVal: { fontFamily: fonts.display, fontSize: 24, color: c.onSurface },
  statLabel: { fontFamily: fonts.regular, fontSize: 12, color: c.muted, marginTop: 2 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: c.border, gap: 10 },
  rowLine: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  rowLabel: { fontFamily: fonts.medium, fontSize: 14, color: c.onSurface, flex: 1 },
  rowVal: { fontFamily: fonts.semibold, fontSize: 14, color: c.brandSecondary },
  bar: { height: 10, borderRadius: 999, backgroundColor: c.brandPrimary, marginTop: 4 },
  barBg: { height: 10, borderRadius: 999, backgroundColor: c.surfaceTertiary, marginTop: 4, overflow: "hidden" },
  funLabel: { fontFamily: fonts.medium, fontSize: 13, color: c.onSurface },
  errItem: { borderTopWidth: 1, borderTopColor: c.divider, paddingTop: 8 },
  errPath: { fontFamily: fonts.medium, fontSize: 12, color: c.error },
  errMeta: { fontFamily: fonts.regular, fontSize: 11, color: c.muted },
  uName: { fontFamily: fonts.semibold, fontSize: 14, color: c.onSurface },
  uMeta: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  fbCat: { fontFamily: fonts.semibold, fontSize: 11, color: c.onBrandTertiary, backgroundColor: c.brandTertiary, alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" },
  fbMsg: { fontFamily: fonts.regular, fontSize: 14, color: c.onSurface, marginTop: 6 },
  fbMeta: { fontFamily: fonts.regular, fontSize: 11, color: c.muted, marginTop: 4 },
  empty: { fontFamily: fonts.regular, fontSize: 14, color: c.muted, textAlign: "center", padding: 30 },
}));

const rupiah = (n: number) => "Rp" + (n || 0).toLocaleString("id-ID");
const dt = (s?: string) => { try { return new Date(s!).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); } catch { return "-"; } };

function Stat({ v, l }: { v: string | number; l: string }) {
  const styles = useStyles();
  return (
    <View style={styles.stat}>
      <Text style={styles.statVal}>{v}</Text>
      <Text style={styles.statLabel}>{l}</Text>
    </View>
  );
}

export default function AdminScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<"overview" | "users" | "feedback">("overview");

  const { data, isLoading } = useQuery({ queryKey: ["adminOverview"], queryFn: adminOverview, refetchInterval: 15000, enabled: tab === "overview" });
  const { data: usersData } = useQuery({ queryKey: ["adminUsers"], queryFn: adminUsers, enabled: tab === "users" });
  const { data: fbData } = useQuery({ queryKey: ["adminFeedback"], queryFn: adminFeedback, enabled: tab === "feedback" });

  const b = data?.business;
  const funnelMax = Math.max(1, ...(data?.funnel ?? []).map((f: any) => f.count));
  const featMax = Math.max(1, ...(data?.features ?? []).map((f: any) => f.count));

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.backBtn} onPress={() => router.back()} hitSlop={8} testID="admin-back">
          <Feather name="chevron-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Admin Dashboard</Text>
      </View>

      <View style={styles.tabs}>
        {(["overview", "users", "feedback"] as const).map((k) => (
          <Pressable key={k} style={[styles.tab, tab === k && styles.tabOn]} onPress={() => setTab(k)} testID={`admin-tab-${k}`}>
            <Text style={[styles.tabText, tab === k && styles.tabTextOn]}>
              {k === "overview" ? "Ringkasan" : k === "users" ? "User" : "Masukan"}
            </Text>
          </Pressable>
        ))}
      </View>

      <ScrollView contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: insets.bottom + 40 }}>
        {tab === "overview" ? (
          isLoading || !b ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
          ) : (
            <>
              <Text style={styles.sectionTitle}>📊 Bisnis</Text>
              <View style={styles.grid}>
                <Stat v={b.total_users} l="Total User" />
                <Stat v={`+${b.new_users_7d}`} l="User baru (7 hari)" />
                <Stat v={b.active_users_7d} l="Aktif (7 hari)" />
                <Stat v={b.total_trees} l="Total Pohon" />
                <Stat v={rupiah(b.revenue_total)} l="Pendapatan total" />
                <Stat v={rupiah(b.revenue_30d)} l="Pendapatan 30 hari" />
              </View>
              <View style={[styles.card, { marginTop: 12 }]}>
                <View style={styles.rowLine}><Text style={styles.rowLabel}>Paket Gratis</Text><Text style={styles.rowVal}>{b.plans.free}</Text></View>
                <View style={styles.rowLine}><Text style={styles.rowLabel}>Paket Pro</Text><Text style={styles.rowVal}>{b.plans.pro}</Text></View>
                <View style={styles.rowLine}><Text style={styles.rowLabel}>Paket Keluarga</Text><Text style={styles.rowVal}>{b.plans.family}</Text></View>
                <View style={styles.rowLine}><Text style={styles.rowLabel}>Transaksi berhasil</Text><Text style={styles.rowVal}>{b.paid_count}</Text></View>
              </View>

              <Text style={styles.sectionTitle}>🔻 Funnel</Text>
              <View style={styles.card}>
                {(data.funnel ?? []).map((f: any) => (
                  <View key={f.step}>
                    <View style={styles.rowLine}>
                      <Text style={styles.funLabel}>{f.step}</Text>
                      <Text style={styles.rowVal}>{f.count}</Text>
                    </View>
                    <View style={styles.barBg}>
                      <View style={[styles.bar, { width: `${(f.count / funnelMax) * 100}%` }]} />
                    </View>
                  </View>
                ))}
              </View>

              <Text style={styles.sectionTitle}>⭐ Fitur Terpakai</Text>
              <View style={styles.card}>
                {(data.features ?? []).map((f: any) => (
                  <View key={f.key}>
                    <View style={styles.rowLine}>
                      <Text style={styles.funLabel}>{f.key}</Text>
                      <Text style={styles.rowVal}>{f.count}</Text>
                    </View>
                    <View style={styles.barBg}>
                      <View style={[styles.bar, { width: `${(f.count / featMax) * 100}%`, backgroundColor: colors.brandSecondary }]} />
                    </View>
                  </View>
                ))}
              </View>

              <Text style={styles.sectionTitle}>🛠️ Teknis</Text>
              <View style={styles.grid}>
                <Stat v={`${data.tech.avg_response_ms} ms`} l="Rata-rata respons (1 jam)" />
                <Stat v={data.tech.requests_1h} l="Request (1 jam)" />
                <Stat v={data.tech.errors_24h} l="Error (24 jam)" />
                <Stat v={data.tech.db_counts.messages} l="Total pesan" />
              </View>
              <View style={[styles.card, { marginTop: 12 }]}>
                <Text style={styles.rowLabel}>Dokumen Database</Text>
                {Object.entries(data.tech.db_counts).map(([k, v]) => (
                  <View key={k} style={styles.rowLine}>
                    <Text style={styles.uMeta}>{k}</Text>
                    <Text style={styles.rowVal}>{v as number}</Text>
                  </View>
                ))}
              </View>
              <View style={[styles.card, { marginTop: 12 }]}>
                <Text style={styles.rowLabel}>Error API Terbaru</Text>
                {data.tech.recent_errors.length === 0 ? (
                  <Text style={styles.uMeta}>Tidak ada error 🎉</Text>
                ) : (
                  data.tech.recent_errors.map((e: any) => (
                    <View key={e.id} style={styles.errItem}>
                      <Text style={styles.errPath}>{e.status} · {e.method} {e.path}</Text>
                      <Text style={styles.errMeta}>{dt(e.created_at)} {e.detail ? `· ${e.detail}` : ""}</Text>
                    </View>
                  ))
                )}
              </View>
            </>
          )
        ) : tab === "users" ? (
          <View style={{ marginTop: 12, gap: 10 }}>
            {(usersData?.users ?? []).map((u: any) => (
              <View key={u.user_id} style={styles.card}>
                <Text style={styles.uName}>{u.name}</Text>
                <Text style={styles.uMeta}>{u.email}</Text>
                <Text style={styles.uMeta}>Daftar: {dt(u.created_at)} · {u.tree_count} pohon</Text>
              </View>
            ))}
            {usersData && usersData.users.length === 0 ? <Text style={styles.empty}>Belum ada user</Text> : null}
          </View>
        ) : (
          <View style={{ marginTop: 12, gap: 10 }}>
            {(fbData?.feedback ?? []).map((f: any) => (
              <View key={f.id} style={styles.card}>
                <Text style={styles.fbCat}>{f.category}</Text>
                <Text style={styles.fbMsg}>{f.message}</Text>
                <Text style={styles.fbMeta}>{f.name} · {f.email} · {dt(f.created_at)}</Text>
              </View>
            ))}
            {fbData && fbData.feedback.length === 0 ? <Text style={styles.empty}>Belum ada masukan</Text> : null}
          </View>
        )}
      </ScrollView>
    </View>
  );
}
