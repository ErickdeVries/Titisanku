import { useCallback } from "react";
import { View, Text, Pressable, FlatList } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { getNotifications, markNotificationsRead, AppNotification } from "@/src/api";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12 },
  back: { width: 36, height: 36, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  row: { flexDirection: "row", gap: 12, paddingHorizontal: 16, paddingVertical: 14, alignItems: "center" },
  iconWrap: { width: 42, height: 42, borderRadius: 999, alignItems: "center", justifyContent: "center", backgroundColor: c.brandTertiary },
  mid: { flex: 1 },
  ntitle: { fontFamily: fonts.semibold, fontSize: 15, color: c.onSurface },
  nbody: { fontFamily: fonts.regular, fontSize: 13, color: c.muted, marginTop: 2 },
  time: { fontFamily: fonts.regular, fontSize: 11, color: c.muted, marginTop: 4 },
  dot: { width: 9, height: 9, borderRadius: 999, backgroundColor: c.brandPrimary },
  sep: { height: 1, backgroundColor: c.divider, marginLeft: 70 },
  empty: { alignItems: "center", justifyContent: "center", paddingTop: 80, gap: 12 },
  emptyText: { fontFamily: fonts.regular, fontSize: 14, color: c.muted },
}));

function timeAgo(iso: string) {
  try {
    const d = new Date(iso).getTime();
    const diff = Date.now() - d;
    const m = Math.floor(diff / 60000);
    if (m < 1) return "baru saja";
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}j`;
    return `${Math.floor(h / 24)}h`;
  } catch {
    return "";
  }
}

export default function NotificationsScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();

  const { data } = useQuery({ queryKey: ["notifications"], queryFn: getNotifications });
  const items: AppNotification[] = data?.items ?? [];

  useFocusEffect(
    useCallback(() => {
      return () => {
        markNotificationsRead().then(() => qc.invalidateQueries({ queryKey: ["notifications"] }));
      };
    }, [qc]),
  );

  const iconFor = (type: string) => (type === "chat" ? "message-circle" : type === "mention" ? "at-sign" : type === "member" ? "user-plus" : "bell");

  const onTap = (n: AppNotification) => {
    if (n.type === "chat" || n.type === "mention") router.push("/(tabs)/chat");
    else router.push("/(tabs)");
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.back} onPress={() => router.back()} testID="notif-back">
          <Feather name="arrow-left" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("notifications")}</Text>
      </View>

      <FlatList
        data={items}
        keyExtractor={(n) => n.id}
        ItemSeparatorComponent={() => <View style={styles.sep} />}
        renderItem={({ item }) => (
          <Pressable style={styles.row} onPress={() => onTap(item)} testID={`notif-${item.id}`}>
            <View style={styles.iconWrap}>
              <Feather name={iconFor(item.type)} size={19} color={colors.brandSecondary} />
            </View>
            <View style={styles.mid}>
              <Text style={styles.ntitle} numberOfLines={1}>{item.title}</Text>
              {item.body ? <Text style={styles.nbody} numberOfLines={2}>{item.body}</Text> : null}
              <Text style={styles.time}>{timeAgo(item.created_at)}</Text>
            </View>
            {!item.read ? <View style={styles.dot} /> : null}
          </Pressable>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Feather name="bell" size={36} color={colors.muted} />
            <Text style={styles.emptyText}>{t("no_notifications")}</Text>
          </View>
        }
      />
    </View>
  );
}
