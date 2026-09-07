import { View, Text, Pressable, FlatList, Switch, Alert, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getChat, fileUrl, muteRoom, leaveGroup } from "@/src/api";
import { useI18n } from "@/src/i18n";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  back: { width: 36, height: 36, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  hero: { alignItems: "center", paddingVertical: 24, gap: 10 },
  photo: { width: 110, height: 110, borderRadius: 999, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  photoImg: { width: "100%", height: "100%" },
  name: { fontFamily: fonts.bold, fontSize: 22, color: c.onSurface, textAlign: "center", paddingHorizontal: 24 },
  sub: { fontFamily: fonts.regular, fontSize: 14, color: c.muted },
  actionsCard: { marginHorizontal: 16, backgroundColor: c.surfaceSecondary, borderRadius: 16, overflow: "hidden" },
  actionRow: { flexDirection: "row", alignItems: "center", gap: 14, paddingHorizontal: 16, paddingVertical: 15 },
  actionText: { fontFamily: fonts.medium, fontSize: 15, color: c.onSurface, flex: 1 },
  rowDivider: { height: 1, backgroundColor: c.divider, marginLeft: 50 },
  sectionLabel: { fontFamily: fonts.medium, fontSize: 12, color: c.muted, paddingHorizontal: 20, paddingTop: 22, paddingBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 },
  memberRow: { flexDirection: "row", alignItems: "center", gap: 14, paddingHorizontal: 16, paddingVertical: 12 },
  avatar: { width: 46, height: 46, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: "100%", height: "100%" },
  mname: { fontFamily: fonts.semibold, fontSize: 15, color: c.onSurface, flex: 1 },
  badge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999, backgroundColor: c.brandTertiary },
  badgeText: { fontFamily: fonts.semibold, fontSize: 11, color: c.brandSecondary },
}));

export default function GroupInfoScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { roomId } = useLocalSearchParams<{ roomId: string }>();

  const { data: room } = useQuery({ queryKey: ["chat", roomId], queryFn: () => getChat(roomId) });

  if (!room) {
    return <View style={[styles.root, { alignItems: "center", justifyContent: "center" }]}><ActivityIndicator color={colors.brandPrimary} /></View>;
  }

  const members = room.members ?? [];
  const isGroup = room.room_type === "group";
  const muted = !!room.muted;

  const toggleMute = async (val: boolean) => {
    try {
      await muteRoom(roomId, val);
      await qc.invalidateQueries({ queryKey: ["chat", roomId] });
      qc.invalidateQueries({ queryKey: ["chatRooms"] });
    } catch {}
  };

  const doLeave = () => {
    Alert.alert(t("leave_group"), t("leave_group_confirm"), [
      { text: t("cancel"), style: "cancel" },
      {
        text: t("leave_group"),
        style: "destructive",
        onPress: async () => {
          try {
            await leaveGroup(roomId);
            qc.invalidateQueries({ queryKey: ["chatRooms"] });
            router.replace("/(tabs)/chat");
          } catch {}
        },
      },
    ]);
  };

  const badgeFor = (m: any) => {
    if (m.is_creator) return t("group_creator");
    if (m.role === "admin") return t("badge_admin");
    if (m.role === "editor") return t("badge_editor");
    return null;
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.back} onPress={() => router.back()} testID="info-back">
          <Feather name="arrow-left" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("group_info")}</Text>
      </View>

      <FlatList
        data={members}
        keyExtractor={(m: any) => m.user_id}
        ListHeaderComponent={
          <View>
            <View style={styles.hero}>
              <View style={styles.photo}>
                {room.room_picture ? (
                  <Image source={{ uri: fileUrl(room.room_picture) }} style={styles.photoImg} contentFit="cover" />
                ) : (
                  <Feather name={isGroup ? "users" : "home"} size={44} color={colors.brandPrimary} />
                )}
              </View>
              <Text style={styles.name}>{room.room_name}</Text>
              <Text style={styles.sub}>{members.length} {t("members_count")}</Text>
            </View>

            <View style={styles.actionsCard}>
              <View style={styles.actionRow}>
                <Feather name={muted ? "bell-off" : "bell"} size={20} color={colors.brandSecondary} />
                <Text style={styles.actionText}>{t("mute_chat")}</Text>
                <Switch value={muted} onValueChange={toggleMute} trackColor={{ true: colors.brandPrimary, false: colors.border }} thumbColor="#FFFFFF" testID="info-mute" />
              </View>
              {room.can_manage ? (
                <>
                  <View style={styles.rowDivider} />
                  <Pressable style={styles.actionRow} onPress={() => router.push(`/chat/manage/${roomId}`)} testID="info-manage">
                    <Feather name="settings" size={20} color={colors.brandSecondary} />
                    <Text style={styles.actionText}>{t("manage_group")}</Text>
                    <Feather name="chevron-right" size={20} color={colors.muted} />
                  </Pressable>
                </>
              ) : null}
              {isGroup ? (
                <>
                  <View style={styles.rowDivider} />
                  <Pressable style={styles.actionRow} onPress={doLeave} testID="info-leave">
                    <Feather name="log-out" size={20} color={colors.error} />
                    <Text style={[styles.actionText, { color: colors.error }]}>{t("leave_group")}</Text>
                  </Pressable>
                </>
              ) : null}
            </View>

            <Text style={styles.sectionLabel}>{t("group_members")} · {members.length}</Text>
          </View>
        }
        renderItem={({ item }: { item: any }) => {
          const badge = badgeFor(item);
          return (
            <View style={styles.memberRow} testID={`info-member-${item.user_id}`}>
              <View style={styles.avatar}>
                {item.picture ? (
                  <Image source={{ uri: fileUrl(item.picture) }} style={styles.avatarImg} contentFit="cover" />
                ) : (
                  <Feather name="user" size={20} color={colors.muted} />
                )}
              </View>
              <Text style={styles.mname} numberOfLines={1}>{item.name}</Text>
              {badge ? (
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{badge}</Text>
                </View>
              ) : null}
            </View>
          );
        }}
        contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}
      />
    </View>
  );
}
