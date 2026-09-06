import { useCallback } from "react";
import { View, Text, Pressable, FlatList } from "react-native";
import { Image } from "expo-image";
import { useRouter, useFocusEffect } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { listChatRooms, fileUrl, ChatRoom, markNotificationsRead } from "@/src/api";
import { useI18n } from "@/src/i18n";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20, paddingBottom: 12, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: fonts.display, fontSize: 26, color: c.onSurface },
  newBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: c.brandPrimary, paddingHorizontal: 14, height: 40, borderRadius: 999 },
  newBtnText: { fontFamily: fonts.semibold, fontSize: 14, color: c.onBrandPrimary },
  row: { flexDirection: "row", alignItems: "center", gap: 14, paddingHorizontal: 16, paddingVertical: 12 },
  avatar: { width: 52, height: 52, borderRadius: 999, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: "100%", height: "100%" },
  rowMid: { flex: 1, gap: 3 },
  rowTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  name: { fontFamily: fonts.semibold, fontSize: 16, color: c.onSurface, flex: 1 },
  time: { fontFamily: fonts.regular, fontSize: 11, color: c.muted, marginLeft: 8 },
  preview: { fontFamily: fonts.regular, fontSize: 13, color: c.muted, flex: 1 },
  badge: { minWidth: 20, height: 20, borderRadius: 999, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: 6, marginLeft: 8 },
  badgeText: { fontFamily: fonts.bold, fontSize: 11, color: c.onBrandPrimary },
  sep: { height: 1, backgroundColor: c.divider, marginLeft: 82 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: 40, gap: 10 },
  emptyText: { fontFamily: fonts.regular, fontSize: 14, color: c.muted, textAlign: "center" },
}));

function shortTime(iso?: string | null) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return d.toLocaleDateString([], { day: "2-digit", month: "2-digit" });
  } catch {
    return "";
  }
}

export default function ChatListScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();

  const { data } = useQuery({ queryKey: ["chatRooms"], queryFn: listChatRooms, refetchInterval: 4000 });
  const rooms = data?.rooms ?? [];

  useFocusEffect(
    useCallback(() => {
      qc.invalidateQueries({ queryKey: ["chatRooms"] });
      markNotificationsRead("chat").then(() => qc.invalidateQueries({ queryKey: ["notifications"] }));
    }, [qc]),
  );

  const renderItem = ({ item }: { item: ChatRoom }) => (
    <Pressable style={styles.row} onPress={() => router.push(`/chat/${item.id}`)} testID={`room-${item.id}`}>
      <View style={styles.avatar}>
        {item.picture ? (
          <Image source={{ uri: fileUrl(item.picture) }} style={styles.avatarImg} contentFit="cover" />
        ) : (
          <Feather name={item.type === "direct" ? "user" : item.type === "family" ? "home" : "users"} size={22} color={colors.brandPrimary} />
        )}
      </View>
      <View style={styles.rowMid}>
        <View style={styles.rowTop}>
          <Text style={styles.name} numberOfLines={1}>{item.name}</Text>
          <Text style={styles.time}>{shortTime(item.last_message_at)}</Text>
        </View>
        <View style={styles.rowTop}>
          <Text style={styles.preview} numberOfLines={1}>{item.last_message || t("tap_to_chat")}</Text>
          {item.unread > 0 ? (
            <View style={styles.badge} testID={`unread-${item.id}`}>
              <Text style={styles.badgeText}>{item.unread > 99 ? "99+" : item.unread}</Text>
            </View>
          ) : null}
        </View>
      </View>
    </Pressable>
  );

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Text style={styles.title}>{t("chats")}</Text>
        <Pressable style={styles.newBtn} onPress={() => router.push("/chat/new")} testID="new-chat-button">
          <Feather name="edit" size={16} color={colors.onBrandPrimary} />
          <Text style={styles.newBtnText}>{t("new_chat")}</Text>
        </Pressable>
      </View>

      <FlatList
        data={rooms}
        keyExtractor={(r) => r.id}
        renderItem={renderItem}
        ItemSeparatorComponent={() => <View style={styles.sep} />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Feather name="message-circle" size={36} color={colors.muted} />
            <Text style={styles.emptyText}>{t("no_chats_yet")}</Text>
          </View>
        }
      />
    </View>
  );
}
