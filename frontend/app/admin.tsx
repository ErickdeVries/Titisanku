import { useEffect, useMemo, useState } from "react";
import {
  View,
  Text,
  Pressable,
  ScrollView,
  ActivityIndicator,
  TextInput,
  RefreshControl,
} from "react-native";
import { useRouter } from "expo-router";
import { useGoBack } from "@/src/hooks/useGoBack";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import {
  adminOverview,
  adminUsers,
  adminFeedback,
  adminGrowth,
  adminFinance,
  adminActivity,
  adminErrors,
  adminTrees,
  adminSystem,
  type AdminActivityItem,
  type AdminErrorItem,
  type AdminFinanceOrder,
} from "@/src/api";
import { BarRow, Bars, Sparkline } from "@/src/components/AdminCharts";

type TabKey =
  | "overview"
  | "growth"
  | "finance"
  | "activity"
  | "errors"
  | "trees"
  | "users"
  | "feedback"
  | "system";

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "overview", label: "Ringkasan", icon: "grid" },
  { key: "growth", label: "Pertumbuhan", icon: "trending-up" },
  { key: "finance", label: "Keuangan", icon: "credit-card" },
  { key: "activity", label: "Aktivitas", icon: "activity" },
  { key: "errors", label: "Error", icon: "alert-triangle" },
  { key: "trees", label: "Pohon", icon: "git-branch" },
  { key: "users", label: "User", icon: "users" },
  { key: "feedback", label: "Masukan", icon: "message-square" },
  { key: "system", label: "Sistem", icon: "server" },
];

// Dashboard admin: data disimpan 60 detik dan data lama tetap tampil saat
// refetch. Tanpa ini setiap pindah tab / interval refetch layar jadi spinner
// penuh, sehingga terasa lambat walau request-nya sebenarnya cepat.
const ADMIN_QUERY = {
  staleTime: 60_000,
  gcTime: 10 * 60_000,
  placeholderData: keepPreviousData,
} as const;

const ACTION_LABEL: Record<string, string> = {
  "auth.login": "Masuk",
  "auth.register": "Daftar akun",
  "auth.logout": "Keluar",
  "tree.create": "Buat pohon",
  "tree.delete": "Hapus pohon",
  "tree.restore": "Pulihkan pohon",
  "invite.create": "Buat tautan undangan",
  "member.join": "Gabung pohon",
  "member.role_change": "Ubah peran anggota",
  "member.remove": "Keluarkan anggota",
  "person.add": "Tambah anggota keluarga",
  "person.delete": "Hapus anggota keluarga",
  "plan.manual_override": "Ubah paket manual",
  "plan.expired": "Paket kedaluwarsa",
  "payment.created": "Buat tagihan",
  "payment.paid": "Pembayaran berhasil",
  "payment.failed": "Pembayaran gagal",
  "feedback.submit": "Kirim masukan",
};

const ACTION_ICON: Record<string, string> = {
  "auth.login": "log-in",
  "auth.register": "user-plus",
  "auth.logout": "log-out",
  "tree.create": "git-branch",
  "tree.delete": "trash-2",
  "invite.create": "mail",
  "member.join": "user-check",
  "member.role_change": "shield",
  "member.remove": "user-minus",
  "person.add": "user-plus",
  "person.delete": "user-x",
  "plan.manual_override": "zap",
  "payment.created": "file-text",
  "payment.paid": "check-circle",
  "payment.failed": "x-circle",
  "feedback.submit": "message-square",
};

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  backBtn: { width: 36, height: 36, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface, flex: 1 },
  headerBtn: { width: 36, height: 36, borderRadius: 999, alignItems: "center", justifyContent: "center", backgroundColor: c.surfaceTertiary },
  tabs: { paddingVertical: 10, paddingHorizontal: 12 },
  tab: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, marginRight: 8, backgroundColor: c.surfaceTertiary },
  tabOn: { backgroundColor: c.brandPrimary },
  tabText: { fontFamily: fonts.semibold, fontSize: 12, color: c.muted },
  tabTextOn: { color: c.onBrandPrimary },
  sectionTitle: { fontFamily: fonts.semibold, fontSize: 15, color: c.onSurface, marginTop: 18, marginBottom: 10 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  stat: { width: "47%", backgroundColor: c.surfaceSecondary, borderRadius: 16, padding: 14, borderWidth: 1, borderColor: c.border },
  statVal: { fontFamily: fonts.display, fontSize: 24, color: c.onSurface },
  statLabel: { fontFamily: fonts.regular, fontSize: 12, color: c.muted, marginTop: 2 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: c.border, gap: 10, marginBottom: 12 },
  cardTitle: { fontFamily: fonts.semibold, fontSize: 14, color: c.onSurface },
  rowLine: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  rowLabel: { fontFamily: fonts.medium, fontSize: 14, color: c.onSurface, flex: 1 },
  rowVal: { fontFamily: fonts.semibold, fontSize: 14, color: c.brandSecondary },
  rowValMuted: { fontFamily: fonts.regular, fontSize: 13, color: c.muted },
  bar: { height: 10, borderRadius: 999, backgroundColor: c.brandPrimary, marginTop: 4 },
  barBg: { height: 10, borderRadius: 999, backgroundColor: c.surfaceTertiary, marginTop: 4, overflow: "hidden" },
  funLabel: { fontFamily: fonts.medium, fontSize: 13, color: c.onSurface },
  errItem: { borderTopWidth: 1, borderTopColor: c.divider, paddingTop: 8, gap: 2 },
  errPath: { fontFamily: fonts.medium, fontSize: 12, color: c.error },
  errMeta: { fontFamily: fonts.regular, fontSize: 11, color: c.muted },
  uName: { fontFamily: fonts.semibold, fontSize: 14, color: c.onSurface },
  uMeta: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  fbCat: { fontFamily: fonts.semibold, fontSize: 11, color: c.onBrandTertiary, backgroundColor: c.brandTertiary, alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" },
  fbMsg: { fontFamily: fonts.regular, fontSize: 14, color: c.onSurface, marginTop: 6 },
  fbMeta: { fontFamily: fonts.regular, fontSize: 11, color: c.muted, marginTop: 4 },
  empty: { fontFamily: fonts.regular, fontSize: 14, color: c.muted, textAlign: "center", padding: 30 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 12 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: c.surfaceTertiary },
  chipOn: { backgroundColor: c.brandTertiary },
  chipText: { fontFamily: fonts.medium, fontSize: 12, color: c.muted },
  chipTextOn: { color: c.onBrandTertiary, fontFamily: fonts.semibold },
  search: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8, marginBottom: 12 },
  searchInput: { flex: 1, fontFamily: fonts.regular, fontSize: 13, color: c.onSurface, padding: 0 },
  badge: { fontFamily: fonts.semibold, fontSize: 10, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" },
  listItem: { borderTopWidth: 1, borderTopColor: c.divider, paddingTop: 10, gap: 3 },
  listHead: { flexDirection: "row", alignItems: "center", gap: 8 },
  listTitle: { fontFamily: fonts.semibold, fontSize: 13, color: c.onSurface, flex: 1 },
  listMeta: { fontFamily: fonts.regular, fontSize: 11, color: c.muted },
  italic: { fontFamily: fonts.regular, fontSize: 12, color: c.muted, fontStyle: "italic" },
  pillOn: { backgroundColor: c.brandTertiary },
  kvRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 3 },
  kvKey: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  kvVal: { fontFamily: fonts.semibold, fontSize: 12, color: c.onSurface },
}));

const rupiah = (n: number) => "Rp" + (n || 0).toLocaleString("id-ID");
const num = (n: number) => (n || 0).toLocaleString("id-ID");
const dt = (s?: string | null) => {
  if (!s) return "-";
  try {
    return new Date(s).toLocaleString("id-ID", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "-";
  }
};
const shortDate = (s?: string) => {
  if (!s) return "-";
  try {
    return new Date(`${s}T00:00:00`).toLocaleDateString("id-ID", { day: "2-digit", month: "short" });
  } catch {
    return s;
  }
};
const bytes = (n: number) => {
  const v = n || 0;
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  if (v < 1024 * 1024 * 1024) return `${(v / 1024 / 1024).toFixed(1)} MB`;
  return `${(v / 1024 / 1024 / 1024).toFixed(2)} GB`;
};
const pct = (v: number) => `${Math.round((v || 0) * 100)}%`;
const metaSummary = (meta?: Record<string, unknown>) => {
  if (!meta) return "";
  return Object.entries(meta)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .slice(0, 3)
    .map(([k, v]) => `${k}: ${typeof v === "number" && k.toLowerCase().includes("amount") ? rupiah(v) : String(v)}`)
    .join(" · ");
};

/** Debounce sederhana supaya kotak pencarian tidak membanjiri backend. */
function useDebounced<T>(value: T, ms = 400): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function Stat({ v, l }: { v: string | number; l: string }) {
  const styles = useStyles();
  return (
    <View style={styles.stat}>
      <Text style={styles.statVal} numberOfLines={1} adjustsFontSizeToFit>
        {v}
      </Text>
      <Text style={styles.statLabel}>{l}</Text>
    </View>
  );
}

function RangeChips({ days, onChange }: { days: number; onChange: (d: number) => void }) {
  const styles = useStyles();
  return (
    <View style={styles.chipRow}>
      {[7, 30, 90].map((d) => (
        <Pressable
          key={d}
          onPress={() => onChange(d)}
          style={[styles.chip, days === d && styles.chipOn]}
          testID={`admin-range-${d}`}
        >
          <Text style={[styles.chipText, days === d && styles.chipTextOn]}>{d} hari</Text>
        </Pressable>
      ))}
    </View>
  );
}

function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <View style={styles.search}>
      <Feather name="search" size={15} color={colors.muted} />
      <TextInput
        style={styles.searchInput}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        autoCapitalize="none"
        autoCorrect={false}
      />
      {value ? (
        <Pressable onPress={() => onChange("")} hitSlop={8}>
          <Feather name="x" size={15} color={colors.muted} />
        </Pressable>
      ) : null}
    </View>
  );
}

function Loading() {
  const { colors } = useTheme();
  return <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />;
}

// ---------------------------------------------------------------- Ringkasan
function OverviewTab() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { data, isLoading } = useQuery({
    queryKey: ["adminOverview"],
    queryFn: adminOverview,
    refetchInterval: 30000,
    ...ADMIN_QUERY,
  });

  if (isLoading || !data) return <Loading />;

  const b = data.business ?? {};
  const tech = data.tech ?? {};
  const funnel = data.funnel ?? [];
  const features = data.features ?? [];
  const funnelMax = Math.max(1, ...funnel.map((f: any) => f.count));
  const featMax = Math.max(1, ...features.map((f: any) => f.count));

  return (
    <>
      <Text style={styles.sectionTitle}>Bisnis</Text>
      <View style={styles.grid}>
        <Stat v={num(b.total_users)} l="Total pengguna" />
        <Stat v={num(b.new_users_7d)} l="Pengguna baru 7 hari" />
        <Stat v={num(b.total_trees)} l="Total pohon" />
        <Stat v={num(b.active_users_7d)} l="Aktif 7 hari" />
        <Stat v={rupiah(b.revenue_total)} l="Pendapatan total" />
        <Stat v={rupiah(b.revenue_30d)} l="Pendapatan 30 hari" />
        <Stat v={num(b.paid_count)} l="Transaksi lunas" />
        <Stat v={pct(b.paid_count / Math.max(1, b.total_trees))} l="Rasio berbayar" />
      </View>

      <Text style={styles.sectionTitle}>Paket langganan</Text>
      <View style={styles.card}>
        <BarRow label="Free" value={b.plans?.free ?? 0} max={Math.max(1, b.total_trees ?? 1)} color={colors.muted} />
        <BarRow label="Pro" value={b.plans?.pro ?? 0} max={Math.max(1, b.total_trees ?? 1)} color={colors.brandPrimary} />
        <BarRow label="Family" value={b.plans?.family ?? 0} max={Math.max(1, b.total_trees ?? 1)} color={colors.success} />
      </View>

      <Text style={styles.sectionTitle}>Corong pemakaian</Text>
      <View style={styles.card}>
        {funnel.map((f: any) => (
          <BarRow key={f.step} label={f.step} value={f.count} max={funnelMax} color={colors.brandSecondary} />
        ))}
        {funnel.length === 0 ? <Text style={styles.empty}>Belum ada data</Text> : null}
      </View>

      <Text style={styles.sectionTitle}>Fitur terpakai</Text>
      <View style={styles.card}>
        {features.map((f: any) => (
          <BarRow key={f.key} label={f.key} value={f.count} max={featMax} color={colors.brandPrimary} />
        ))}
        {features.length === 0 ? <Text style={styles.empty}>Belum ada data</Text> : null}
      </View>

      <Text style={styles.sectionTitle}>Kesehatan teknis</Text>
      <View style={styles.grid}>
        <Stat v={`${tech.avg_response_ms ?? 0} ms`} l="Rata-rata respons" />
        <Stat v={num(tech.requests_1h)} l="Request 1 jam" />
        <Stat v={num(tech.errors_24h)} l="Error 24 jam" />
        <Stat v={num(tech.db_counts?.activity_log ?? 0)} l="Baris audit log" />
      </View>

      <Text style={styles.sectionTitle}>Error terakhir</Text>
      <View style={styles.card}>
        {(tech.recent_errors ?? []).slice(0, 8).map((e: any) => (
          <View key={e.id} style={styles.errItem}>
            <Text style={styles.errPath}>
              {e.status} · {e.path}
            </Text>
            <Text style={styles.errMeta}>
              {dt(e.created_at)}
              {e.detail ? ` · ${String(e.detail).slice(0, 80)}` : ""}
            </Text>
          </View>
        ))}
        {(tech.recent_errors ?? []).length === 0 ? <Text style={styles.empty}>Tidak ada error</Text> : null}
      </View>
    </>
  );
}

// -------------------------------------------------------------- Pertumbuhan
function GrowthTab() {
  const styles = useStyles();
  const { colors } = useTheme();
  const [days, setDays] = useState(30);
  const { data, isLoading } = useQuery({
    queryKey: ["adminGrowth", days],
    queryFn: () => adminGrowth(days),
    ...ADMIN_QUERY,
  });

  if (isLoading || !data) return <Loading />;
  const s = data.series;
  const t = data.totals;
  const e = data.engagement;

  return (
    <>
      <RangeChips days={days} onChange={setDays} />

      <Text style={styles.sectionTitle}>Pengguna aktif</Text>
      <View style={styles.grid}>
        <Stat v={num(e.dau)} l="DAU (hari ini)" />
        <Stat v={num(e.wau)} l="WAU (7 hari)" />
        <Stat v={num(e.mau)} l={`MAU (${data.days} hari)`} />
        <Stat v={pct(e.stickiness)} l="Stickiness DAU/MAU" />
      </View>

      <Text style={styles.sectionTitle}>Pendaftar baru</Text>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{num(t.new_users_30d)} pengguna dalam 30 hari</Text>
        <Sparkline values={s.map((p) => p.signups)} color={colors.brandPrimary} />
        <Bars values={s.map((p) => p.signups)} color={colors.brandPrimary} height={44} />
        <View style={styles.rowLine}>
          <Text style={styles.rowValMuted}>{shortDate(s[0]?.date)}</Text>
          <Text style={styles.rowValMuted}>Hari ini: {num(t.new_users_1d)}</Text>
        </View>
      </View>

      <Text style={styles.sectionTitle}>Pengguna aktif per hari</Text>
      <View style={styles.card}>
        <Sparkline values={s.map((p) => p.active_users)} color={colors.success} />
        <Bars values={s.map((p) => p.active_users)} color={colors.success} height={44} />
        <Text style={styles.rowValMuted}>
          Puncak: {num(Math.max(0, ...s.map((p) => p.active_users)))} · kembali aktif 7 hari: {num(e.returning_7d)}
        </Text>
      </View>

      <Text style={styles.sectionTitle}>Pohon & isi</Text>
      <View style={styles.card}>
        <Sparkline values={s.map((p) => p.trees)} color={colors.brandSecondary} />
        <Bars values={s.map((p) => p.trees)} color={colors.brandSecondary} height={40} />
        <View style={styles.kvRow}>
          <Text style={styles.kvKey}>Total pohon</Text>
          <Text style={styles.kvVal}>{num(t.total_trees)}</Text>
        </View>
        <View style={styles.kvRow}>
          <Text style={styles.kvKey}>Pohon baru 7 hari</Text>
          <Text style={styles.kvVal}>{num(t.new_trees_7d)}</Text>
        </View>
        <View style={styles.kvRow}>
          <Text style={styles.kvKey}>Anggota keluarga tercatat</Text>
          <Text style={styles.kvVal}>{num(t.total_people)}</Text>
        </View>
        <View style={styles.kvRow}>
          <Text style={styles.kvKey}>Pesan chat</Text>
          <Text style={styles.kvVal}>{num(t.total_messages)}</Text>
        </View>
      </View>

      <Text style={styles.sectionTitle}>Corong konversi</Text>
      <View style={styles.card}>
        <BarRow label="Terdaftar" value={data.funnel.users} max={Math.max(1, data.funnel.users)} color={colors.muted} />
        <BarRow label="Punya pohon" value={data.funnel.owners} max={Math.max(1, data.funnel.users)} color={colors.brandSecondary} />
        <BarRow label="Pernah bayar" value={data.funnel.payers} max={Math.max(1, data.funnel.users)} color={colors.success} />
        <Text style={styles.rowValMuted}>
          Konversi ke paket berbayar: {pct(data.funnel.conversion)} · {num(t.paid_trees)} pohon berbayar aktif
        </Text>
      </View>
    </>
  );
}

// ------------------------------------------------------------------ Keuangan
function FinanceTab() {
  const styles = useStyles();
  const { colors } = useTheme();
  const [days, setDays] = useState(30);
  const { data, isLoading } = useQuery({
    queryKey: ["adminFinance", days],
    queryFn: () => adminFinance(days),
    ...ADMIN_QUERY,
  });

  if (isLoading || !data) return <Loading />;
  const r = data.revenue;

  return (
    <>
      <RangeChips days={days} onChange={setDays} />

      <Text style={styles.sectionTitle}>Pendapatan</Text>
      <View style={styles.grid}>
        <Stat v={rupiah(r.total)} l="Total sepanjang waktu" />
        <Stat v={rupiah(r[dashboard30Key(days)])} l={`${days} hari terakhir`} />
        <Stat v={rupiah(r.today)} l="Hari ini" />
        <Stat v={rupiah(r.arpu)} l="ARPU (per pembayar)" />
        <Stat v={rupiah(r.avg_order_value)} l="Rata-rata transaksi" />
        <Stat v={num(data.subscriptions.active)} l="Langganan aktif" />
        <Stat v={num(data.subscriptions.expiring_30d)} l="Kedaluwarsa ≤30 hari" />
        <Stat v={pct(data.conversion)} l="Konversi pohon" />
      </View>

      <Text style={styles.sectionTitle}>Tren pendapatan</Text>
      <View style={styles.card}>
        <Sparkline values={data.series.map((p) => p.revenue)} color={colors.success} />
        <Bars values={data.series.map((p) => p.revenue)} color={colors.success} height={44} />
        <View style={styles.rowLine}>
          <Text style={styles.rowValMuted}>{shortDate(data.series[0]?.date)}</Text>
          <Text style={styles.rowValMuted}>
            Transaksi: {num(data.series.reduce((a, p) => a + p.orders, 0))}
          </Text>
        </View>
      </View>

      <Text style={styles.sectionTitle}>Per paket</Text>
      <View style={styles.card}>
        {data.by_plan.map((p) => (
          <BarRow
            key={p.plan}
            label={p.plan}
            value={p.revenue}
            max={Math.max(1, ...data.by_plan.map((x) => x.revenue))}
            color={colors.brandPrimary}
            caption={`${rupiah(p.revenue)} · ${num(p.count)}x`}
          />
        ))}
        {data.by_plan.length === 0 ? <Text style={styles.empty}>Belum ada transaksi lunas</Text> : null}
      </View>

      <Text style={styles.sectionTitle}>Per kanal pembayaran</Text>
      <View style={styles.card}>
        {data.by_provider.map((p) => (
          <BarRow
            key={p.provider}
            label={p.provider}
            value={p.revenue}
            max={Math.max(1, ...data.by_provider.map((x) => x.revenue))}
            color={colors.brandSecondary}
            caption={`${rupiah(p.revenue)} · ${num(p.count)}x`}
          />
        ))}
        {data.by_provider.length === 0 ? <Text style={styles.empty}>Belum ada data kanal</Text> : null}
      </View>

      <Text style={styles.sectionTitle}>Status transaksi</Text>
      <View style={styles.card}>
        {data.by_status.map((s) => (
          <BarRow
            key={s.status}
            label={s.status}
            value={s.count}
            max={Math.max(1, ...data.by_status.map((x) => x.count))}
            color={s.status === "paid" ? colors.success : s.status === "pending" ? colors.warning : colors.error}
            caption={`${num(s.count)}x · ${rupiah(s.amount)}`}
          />
        ))}
        {data.by_status.length === 0 ? <Text style={styles.empty}>Belum ada transaksi</Text> : null}
      </View>

      <Text style={styles.sectionTitle}>Pohon penyumbang terbesar</Text>
      <View style={styles.card}>
        {data.top_trees.map((t) => (
          <View key={t.tree_id} style={styles.listItem}>
            <View style={styles.listHead}>
              <Text style={styles.listTitle} numberOfLines={1}>
                {t.tree_name ?? "(tanpa nama)"}
              </Text>
              <Text style={styles.rowVal}>{rupiah(t.revenue)}</Text>
            </View>
            <Text style={styles.listMeta}>
              {t.owner_email ?? "-"} · {t.plan ?? "-"}
            </Text>
          </View>
        ))}
        {data.top_trees.length === 0 ? <Text style={styles.empty}>Belum ada data</Text> : null}
      </View>

      <Text style={styles.sectionTitle}>Transaksi terakhir</Text>
      <View style={styles.card}>
        {data.recent.map((o: AdminFinanceOrder, i) => (
          <View key={o.order_id ?? i} style={styles.listItem}>
            <View style={styles.listHead}>
              <Text style={styles.listTitle} numberOfLines={1}>
                {o.order_id ?? "-"}
              </Text>
              <Text style={styles.rowVal}>{rupiah(o.amount)}</Text>
            </View>
            <Text style={styles.listMeta}>
              {o.status ?? "-"} · {o.plan ?? "-"} · {o.provider ?? "-"} · {dt(o.paid_at ?? o.created_at)}
            </Text>
            <Text style={styles.listMeta} numberOfLines={1}>
              {o.tree_name ?? "-"} · {o.user_email ?? "-"}
            </Text>
          </View>
        ))}
        {data.recent.length === 0 ? <Text style={styles.empty}>Belum ada transaksi</Text> : null}
      </View>
    </>
  );
}

/** Overview memakai kunci "7d"/"30d"; untuk 90 hari pakai angka 30 hari. */
function dashboard30Key(days: number): "7d" | "30d" {
  return days === 7 ? "7d" : "30d";
}

// ----------------------------------------------------------------- Aktivitas
function ActivityTab() {
  const styles = useStyles();
  const { colors } = useTheme();
  const [days, setDays] = useState(30);
  const [action, setAction] = useState<string | undefined>(undefined);
  const [q, setQ] = useState("");
  const dq = useDebounced(q);

  const { data, isLoading } = useQuery({
    queryKey: ["adminActivity", days, action, dq],
    queryFn: () => adminActivity({ days, action, q: dq }),
    ...ADMIN_QUERY,
    refetchInterval: 20000,
  });

  if (isLoading || !data) return <Loading />;

  return (
    <>
      <RangeChips days={days} onChange={setDays} />
      <SearchBox value={q} onChange={setQ} placeholder="Cari email, aksi, atau target…" />

      <View style={styles.chipRow}>
        <Pressable
          onPress={() => setAction(undefined)}
          style={[styles.chip, !action && styles.chipOn]}
          testID="admin-activity-all"
        >
          <Text style={[styles.chipText, !action && styles.chipTextOn]}>Semua</Text>
        </Pressable>
        {data.actions.slice(0, 10).map((a) => (
          <Pressable
            key={a.action}
            onPress={() => setAction(action === a.action ? undefined : a.action)}
            style={[styles.chip, action === a.action && styles.chipOn]}
            testID={`admin-activity-${a.action}`}
          >
            <Text style={[styles.chipText, action === a.action && styles.chipTextOn]}>
              {ACTION_LABEL[a.action] ?? a.action} · {num(a.count)}
            </Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.sectionTitle}>{num(data.total)} aktivitas</Text>
      <View style={styles.card}>
        {data.items.map((it: AdminActivityItem) => (
          <View key={it.id} style={styles.listItem}>
            <View style={styles.listHead}>
              <Feather
                name={(ACTION_ICON[it.action] ?? "activity") as any}
                size={13}
                color={colors.brandSecondary}
              />
              <Text style={styles.listTitle} numberOfLines={1}>
                {ACTION_LABEL[it.action] ?? it.action}
              </Text>
              <Text style={styles.listMeta}>{dt(it.created_at)}</Text>
            </View>
            <Text style={styles.listMeta} numberOfLines={1}>
              {it.actor_email ?? it.actor_name ?? "sistem"}
              {it.tree_id ? ` · ${it.tree_id}` : ""}
            </Text>
            {metaSummary(it.meta) ? (
              <Text style={styles.listMeta} numberOfLines={2}>
                {metaSummary(it.meta)}
              </Text>
            ) : null}
          </View>
        ))}
        {data.items.length === 0 ? (
          <Text style={styles.empty}>
            Belum ada aktivitas pada rentang ini. Audit log mulai terisi sejak endpoint baru aktif.
          </Text>
        ) : null}
      </View>
    </>
  );
}

// -------------------------------------------------------------------- Error
function ErrorsTab() {
  const styles = useStyles();
  const { colors } = useTheme();
  const [days, setDays] = useState(7);
  const [status, setStatus] = useState<number | undefined>(undefined);
  const [path, setPath] = useState("");
  const dp = useDebounced(path);

  const { data, isLoading } = useQuery({
    queryKey: ["adminErrors", days, status, dp],
    queryFn: () => adminErrors({ days, status, path: dp }),
    ...ADMIN_QUERY,
    refetchInterval: 20000,
  });

  if (isLoading || !data) return <Loading />;

  return (
    <>
      <RangeChips days={days} onChange={setDays} />
      <SearchBox value={path} onChange={setPath} placeholder="Filter path, mis. /api/people" />

      <View style={styles.grid}>
        <Stat v={num(data.total)} l={`Error ${days} hari`} />
        <Stat v={num(data.count_24h)} l="Error 24 jam" />
      </View>

      <View style={styles.chipRow}>
        <Pressable
          onPress={() => setStatus(undefined)}
          style={[styles.chip, !status && styles.chipOn]}
          testID="admin-errors-all"
        >
          <Text style={[styles.chipText, !status && styles.chipTextOn]}>Semua status</Text>
        </Pressable>
        {data.by_status.map((s) => (
          <Pressable
            key={s.status}
            onPress={() => setStatus(status === s.status ? undefined : s.status)}
            style={[styles.chip, status === s.status && styles.chipOn]}
            testID={`admin-errors-status-${s.status}`}
          >
            <Text style={[styles.chipText, status === s.status && styles.chipTextOn]}>
              {s.status} · {num(s.count)}
            </Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.sectionTitle}>Endpoint paling sering gagal</Text>
      <View style={styles.card}>
        {data.by_path.map((p) => (
          <BarRow
            key={p.path}
            label={p.path}
            value={p.count}
            max={Math.max(1, ...data.by_path.map((x) => x.count))}
            color={colors.error}
            caption={`${num(p.count)}x`}
          />
        ))}
        {data.by_path.length === 0 ? <Text style={styles.empty}>Tidak ada error pada rentang ini</Text> : null}
      </View>

      <Text style={styles.sectionTitle}>Log terbaru</Text>
      <View style={styles.card}>
        {data.items.map((e: AdminErrorItem) => (
          <View key={e.id} style={styles.listItem}>
            <View style={styles.listHead}>
              <Text style={[styles.listTitle, { color: e.status >= 500 ? colors.error : colors.warning }]} numberOfLines={1}>
                {e.status} {e.method ?? ""} {e.path}
              </Text>
              <Text style={styles.listMeta}>{dt(e.created_at)}</Text>
            </View>
            <Text style={styles.listMeta}>
              {e.duration_ms ? `${Math.round(e.duration_ms)} ms` : "-"}
              {e.detail ? ` · ${String(e.detail).slice(0, 120)}` : ""}
            </Text>
          </View>
        ))}
        {data.items.length === 0 ? <Text style={styles.empty}>Tidak ada error</Text> : null}
      </View>
    </>
  );
}

// -------------------------------------------------------------------- Pohon
function TreesTab() {
  const styles = useStyles();
  const { colors } = useTheme();
  const [q, setQ] = useState("");
  const dq = useDebounced(q);
  const { data, isLoading } = useQuery({
    queryKey: ["adminTrees", dq],
    queryFn: () => adminTrees({ q: dq }),
    ...ADMIN_QUERY,
  });

  if (isLoading || !data) return <Loading />;

  const maxPeople = Math.max(1, ...data.trees.map((t) => t.people));

  return (
    <>
      <SearchBox value={q} onChange={setQ} placeholder="Cari nama pohon…" />
      <View style={styles.chipRow}>
        {data.plan_counts.map((p) => (
          <View key={p.plan} style={styles.chip}>
            <Text style={styles.chipText}>
              {p.plan} · {num(p.count)}
            </Text>
          </View>
        ))}
      </View>

      <Text style={styles.sectionTitle}>{num(data.total)} pohon (tenant)</Text>
      <View style={styles.card}>
        {data.trees.map((t) => (
          <View key={t.id} style={styles.listItem}>
            <View style={styles.listHead}>
              <Text style={styles.listTitle} numberOfLines={1}>
                {t.name}
              </Text>
              <Text
                style={[
                  styles.badge,
                  {
                    color: t.plan === "free" ? colors.muted : colors.onBrandTertiary,
                    backgroundColor: t.plan === "free" ? colors.surfaceTertiary : colors.brandTertiary,
                  },
                ]}
              >
                {t.plan}
              </Text>
            </View>
            <Text style={styles.listMeta} numberOfLines={1}>
              {t.owner_email ?? "-"} · dibuat {dt(t.created_at)}
            </Text>
            <Text style={styles.listMeta}>
              {num(t.people)} orang · {num(t.members)} anggota · {num(t.messages)} pesan · {bytes(t.storage_used)}
            </Text>
            <BarRow label="Ukuran keluarga" value={t.people} max={maxPeople} color={colors.brandPrimary} />
          </View>
        ))}
        {data.trees.length === 0 ? <Text style={styles.empty}>Belum ada pohon</Text> : null}
      </View>
    </>
  );
}

// --------------------------------------------------------------------- User
function UsersTab() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { data } = useQuery({ queryKey: ["adminUsers"], queryFn: adminUsers, ...ADMIN_QUERY });
  if (!data) return <Loading />;
  return (
    <View style={styles.card}>
      {(data.users ?? []).map((u: any) => (
        <View key={u.user_id} style={styles.listItem}>
          <View style={styles.listHead}>
            <Text style={styles.uName} numberOfLines={1}>
              {u.name ?? u.username ?? "-"}
            </Text>
            <Text
              style={[
                styles.badge,
                {
                  color: u.is_superadmin ? colors.onBrandTertiary : colors.muted,
                  backgroundColor: u.is_superadmin ? colors.brandTertiary : colors.surfaceTertiary,
                },
              ]}
            >
              {u.is_superadmin ? "superadmin" : u.role ?? "user"}
            </Text>
          </View>
          <Text style={styles.uMeta} numberOfLines={1}>
            {u.email ?? "-"}
          </Text>
          <Text style={styles.uMeta}>
            {num(u.tree_count)} pohon · dibuat {dt(u.created_at)}
            {u.demo ? " · akun demo" : ""}
          </Text>
        </View>
      ))}
      {(data.users ?? []).length === 0 ? <Text style={styles.empty}>Belum ada pengguna</Text> : null}
    </View>
  );
}

// ------------------------------------------------------------------ Masukan
function FeedbackTab() {
  const styles = useStyles();
  const { data } = useQuery({ queryKey: ["adminFeedback"], queryFn: adminFeedback, ...ADMIN_QUERY });
  if (!data) return <Loading />;
  return (
    <View style={styles.card}>
      {(data.feedback ?? []).map((f: any) => (
        <View key={f.id}>
          <Text style={styles.fbCat}>{f.category ?? "general"}</Text>
          <Text style={styles.fbMsg}>{f.message}</Text>
          <Text style={styles.fbMeta}>
            {f.name ?? "-"} · {f.email ?? "-"} · {dt(f.created_at)}
          </Text>
        </View>
      ))}
      {(data.feedback ?? []).length === 0 ? <Text style={styles.empty}>Belum ada masukan</Text> : null}
    </View>
  );
}

// ------------------------------------------------------------------ Sistem
function SystemTab() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { data, isLoading } = useQuery({
    queryKey: ["adminSystem"],
    queryFn: adminSystem,
    refetchInterval: 30000,
    ...ADMIN_QUERY,
  });
  if (isLoading || !data) return <Loading />;

  const s1 = data.request_stats["1h"];
  const s24 = data.request_stats["24h"];
  const collections = Object.entries(data.collections ?? {}).sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0));
  const hours = Math.floor((data.uptime_seconds || 0) / 3600);
  const minutes = Math.floor(((data.uptime_seconds || 0) % 3600) / 60);

  return (
    <>
      <Text style={styles.sectionTitle}>Proses</Text>
      <View style={styles.grid}>
        <Stat v={`${hours}j ${minutes}m`} l="Uptime proses" />
        <Stat v={num(s1?.requests)} l="Request 1 jam" />
        <Stat v={`${s24?.avg_ms ?? 0} ms`} l="Rata-rata 24 jam" />
        <Stat v={`${s24?.p95_ms ?? 0} ms`} l="p95 24 jam" />
        <Stat v={num(s24?.errors)} l="Error 5xx 24 jam" />
        <Stat v={num(data.collections?.users ?? 0)} l="Dokumen users" />
      </View>

      <Text style={styles.sectionTitle}>Integrasi</Text>
      <View style={styles.card}>
        {Object.entries(data.integrations ?? {}).map(([k, ok]) => (
          <View key={k} style={styles.kvRow}>
            <Text style={styles.kvKey}>{k}</Text>
            <Text style={[styles.kvVal, { color: ok ? colors.success : colors.error }]}>
              {ok ? "aktif" : "belum"}
            </Text>
          </View>
        ))}
        <View style={styles.kvRow}>
          <Text style={styles.kvKey}>Database</Text>
          <Text style={styles.kvVal}>{data.db_name}</Text>
        </View>
        <View style={styles.kvRow}>
          <Text style={styles.kvKey}>Audit log mulai</Text>
          <Text style={styles.kvVal}>{dt(data.activity_log_started)}</Text>
        </View>
      </View>

      <Text style={styles.sectionTitle}>Endpoint terlambat (1 jam)</Text>
      <View style={styles.card}>
        {(s1?.slowest ?? []).map((r, i) => (
          <View key={`${r.path}-${i}`} style={styles.rowLine}>
            <Text style={styles.rowLabel} numberOfLines={1}>
              {r.status} {r.path}
            </Text>
            <Text style={styles.rowVal}>{Math.round(r.ms)} ms</Text>
          </View>
        ))}
        {(s1?.slowest ?? []).length === 0 ? <Text style={styles.empty}>Belum ada request tercatat</Text> : null}
      </View>

      <Text style={styles.sectionTitle}>Ukuran koleksi</Text>
      <View style={styles.card}>
        {collections.map(([k, v]) => (
          <BarRow
            key={k}
            label={k}
            value={v ?? 0}
            max={Math.max(1, ...collections.map(([, x]) => x ?? 0))}
            color={colors.brandSecondary}
          />
        ))}
      </View>
    </>
  );
}

// -------------------------------------------------------------------- Layar
export default function AdminScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const goBack = useGoBack("/");
  const insets = useSafeAreaInsets();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabKey>("overview");
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      await queryClient.invalidateQueries();
    } finally {
      setRefreshing(false);
    }
  };

  const content = useMemo(() => {
    switch (tab) {
      case "growth":
        return <GrowthTab />;
      case "finance":
        return <FinanceTab />;
      case "activity":
        return <ActivityTab />;
      case "errors":
        return <ErrorsTab />;
      case "trees":
        return <TreesTab />;
      case "users":
        return <UsersTab />;
      case "feedback":
        return <FeedbackTab />;
      case "system":
        return <SystemTab />;
      default:
        return <OverviewTab />;
    }
  }, [tab]);

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.backBtn} onPress={() => goBack()} hitSlop={8} testID="admin-back">
          <Feather name="chevron-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Admin Dashboard</Text>
        <Pressable style={styles.headerBtn} onPress={onRefresh} hitSlop={8} testID="admin-refresh">
          <Feather name="refresh-cw" size={16} color={colors.onSurface} />
        </Pressable>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: 12, paddingVertical: 10 }}
        style={{ flexGrow: 0 }}
      >
        {TABS.map((t) => (
          <Pressable
            key={t.key}
            style={[styles.tab, tab === t.key && styles.tabOn]}
            onPress={() => setTab(t.key)}
            testID={`admin-tab-${t.key}`}
          >
            <Feather
              name={t.icon as any}
              size={13}
              color={tab === t.key ? colors.onBrandPrimary : colors.muted}
            />
            <Text style={[styles.tabText, tab === t.key && styles.tabTextOn]}>{t.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView
        contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: insets.bottom + 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
      >
        {content}
      </ScrollView>
    </View>
  );
}
