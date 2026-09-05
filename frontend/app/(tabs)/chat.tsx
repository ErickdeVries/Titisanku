import { useEffect, useMemo, useRef, useState } from "react";
import { View, Text, Pressable, TextInput, FlatList, Modal, Switch } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import * as ImagePicker from "expo-image-picker";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { brandGradient, fonts, makeStyles, useTheme } from "@/src/theme";
import { getChat, getTree, sendChat, uploadPhoto, fileUrl, markNotificationsRead } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surfaceSecondary },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, backgroundColor: c.surface },
  groupIcon: { width: 42, height: 42, borderRadius: 999, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  groupName: { fontFamily: fonts.bold, fontSize: 16, color: c.onSurface },
  groupSub: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  adminBadge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: c.brandPrimary, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  adminBadgeText: { fontFamily: fonts.semibold, fontSize: 11, color: c.onBrandPrimary },
  filterBar: { backgroundColor: c.surface, paddingHorizontal: 16, paddingBottom: 12, gap: 10, borderBottomWidth: 1, borderBottomColor: c.divider },
  toggleRow: { borderRadius: 14, overflow: "hidden" },
  toggleGrad: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 12, gap: 10 },
  toggleLabel: { fontFamily: fonts.medium, fontSize: 13, color: c.onBrandPrimary, flex: 1 },
  toggleInactive: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 12, gap: 10, backgroundColor: c.surfaceTertiary, borderRadius: 14 },
  toggleLabelInactive: { fontFamily: fonts.medium, fontSize: 13, color: c.onSurfaceSecondary, flex: 1 },
  statsText: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  nameFilter: { flexDirection: "row", alignItems: "center", gap: 8, alignSelf: "flex-start", backgroundColor: c.surfaceTertiary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999 },
  nameFilterText: { fontFamily: fonts.medium, fontSize: 13, color: c.onSurface },
  row: { flexDirection: "row", marginVertical: 4, paddingHorizontal: 12, gap: 8, alignItems: "flex-end" },
  rowMine: { justifyContent: "flex-end" },
  avatar: { width: 30, height: 30, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: "100%", height: "100%" },
  bubble: { maxWidth: "76%", borderRadius: 16, padding: 10, gap: 4 },
  bubbleMine: { backgroundColor: c.brandPrimary, borderBottomRightRadius: 4 },
  bubbleOther: { backgroundColor: c.surface, borderBottomLeftRadius: 4 },
  deadBubble: { opacity: 0.6 },
  senderName: { fontFamily: fonts.semibold, fontSize: 12, color: c.brandSecondary },
  msgText: { fontFamily: fonts.regular, fontSize: 15 },
  mention: { fontFamily: fonts.semibold },
  footerRow: { flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: 4 },
  msgTime: { fontFamily: fonts.regular, fontSize: 10 },
  chatImg: { width: 200, height: 200, borderRadius: 10, backgroundColor: c.surfaceTertiary },
  replyPreview: { borderLeftWidth: 3, borderLeftColor: c.brandSecondary, paddingLeft: 8, paddingVertical: 2, marginBottom: 2, opacity: 0.9 },
  replyName: { fontFamily: fonts.semibold, fontSize: 11 },
  replyText: { fontFamily: fonts.regular, fontSize: 12 },
  inputBar: { flexDirection: "row", alignItems: "flex-end", gap: 6, paddingHorizontal: 12, paddingTop: 8, backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.divider },
  input: { flex: 1, backgroundColor: c.surfaceTertiary, borderRadius: 22, paddingHorizontal: 16, paddingVertical: 10, maxHeight: 110, fontFamily: fonts.regular, fontSize: 15, color: c.onSurface },
  iconBtn: { width: 42, height: 42, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  sendBtn: { backgroundColor: c.brandPrimary },
  readonly: { padding: 16, alignItems: "center", backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.divider },
  readonlyText: { fontFamily: fonts.medium, fontSize: 13, color: c.muted },
  replyBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: c.surfaceTertiary, marginHorizontal: 12, marginTop: 8, borderRadius: 10, padding: 8 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: 40, gap: 10 },
  emptyText: { fontFamily: fonts.regular, fontSize: 14, color: c.muted, textAlign: "center" },
  modalBg: { flex: 1, backgroundColor: "rgba(15,23,42,0.4)", justifyContent: "flex-end" },
  sheet: { backgroundColor: c.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: "70%" },
  sheetTitle: { fontFamily: fonts.bold, fontSize: 17, color: c.onSurface, padding: 20, paddingBottom: 8 },
  pickRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 20, paddingVertical: 14 },
  pickText: { fontFamily: fonts.medium, fontSize: 15, color: c.onSurface },
}));

function timeOf(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function MessageText({ text, color }: { text: string; color: string }) {
  const styles = useStyles();
  const parts = text.split(/(@\S+)/g);
  return (
    <Text style={[styles.msgText, { color }]}>
      {parts.map((p, i) =>
        p.startsWith("@") ? (
          <Text key={i} style={[styles.mention, { color }]}>
            {p}
          </Text>
        ) : (
          p
        ),
      )}
    </Text>
  );
}

export default function ChatScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const { user } = useAuth();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const listRef = useRef<FlatList>(null);

  const { data } = useQuery({ queryKey: ["chat"], queryFn: getChat, refetchInterval: 5000 });
  const { data: tree } = useQuery({ queryKey: ["tree"], queryFn: getTree });
  const [text, setText] = useState("");
  const [replyTo, setReplyTo] = useState<any>(null);
  const [sending, setSending] = useState(false);
  const [aliveOnly, setAliveOnly] = useState(true);
  const [filterPersonId, setFilterPersonId] = useState<string | null>(null);
  const [namePickerOpen, setNamePickerOpen] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentions, setMentions] = useState<string[]>([]);

  const isAdmin = user?.role === "admin";
  const canChat = user?.role === "admin" || user?.role === "editor";
  const allMessages = data?.messages ?? [];
  const members = data?.members ?? [];
  const alivePeople = (tree?.people ?? []).filter((p) => p.is_alive !== false);

  const visible = useMemo(() => {
    let v = allMessages;
    if (aliveOnly && !isAdmin) v = v.filter((m: any) => m.sender_is_alive !== false);
    if (filterPersonId) v = v.filter((m: any) => m.sender_person_id === filterPersonId);
    return v;
  }, [allMessages, aliveOnly, isAdmin, filterPersonId]);

  const filterName = filterPersonId ? alivePeople.find((p) => p.id === filterPersonId)?.name ?? t("all_members") : t("all_members");

  useEffect(() => {
    markNotificationsRead("chat").then(() => qc.invalidateQueries({ queryKey: ["notifications"] }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (visible.length) setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 200);
  }, [visible.length]);

  const resetInput = () => {
    setText("");
    setReplyTo(null);
    setMentions([]);
  };

  const doSend = async (attachments: string[] = []) => {
    if (!text.trim() && attachments.length === 0) return;
    setSending(true);
    try {
      await sendChat({ message: text.trim(), attachments, reply_to: replyTo?.id ?? null, mentions });
      resetInput();
      await qc.invalidateQueries({ queryKey: ["chat"] });
    } catch (e) {
      console.log("send error", e);
    } finally {
      setSending(false);
    }
  };

  const sendPhoto = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.6 });
    if (res.canceled || !res.assets?.length) return;
    setSending(true);
    try {
      const path = await uploadPhoto(res.assets[0].uri);
      await sendChat({ message: text.trim(), attachments: [path], reply_to: replyTo?.id ?? null, mentions });
      resetInput();
      await qc.invalidateQueries({ queryKey: ["chat"] });
    } catch (e) {
      console.log("photo send error", e);
    } finally {
      setSending(false);
    }
  };

  const addMention = (m: any) => {
    setText((prev) => `${prev}@${m.name} `);
    setMentions((prev) => Array.from(new Set([...prev, m.user_id])));
    setMentionOpen(false);
  };

  const renderItem = ({ item }: { item: any }) => {
    const mine = item.sender_id === user?.user_id;
    const onText = mine ? colors.onBrandPrimary : colors.onSurface;
    const dead = item.sender_is_alive === false;
    const readByOthers = (item.read_by ?? []).length > 0;
    return (
      <Pressable
        style={[styles.row, mine && styles.rowMine]}
        onLongPress={() => canChat && setReplyTo(item)}
        testID={`chat-msg-${item.id}`}
      >
        {!mine ? (
          <View style={styles.avatar}>
            {item.sender_picture ? (
              <Image source={{ uri: item.sender_picture }} style={styles.avatarImg} contentFit="cover" />
            ) : (
              <Feather name="user" size={16} color={colors.muted} />
            )}
          </View>
        ) : null}
        <View style={[styles.bubble, mine ? styles.bubbleMine : styles.bubbleOther, dead && styles.deadBubble]}>
          {!mine ? (
            <Text style={styles.senderName}>
              {item.sender_name}
              {dead ? " ✝" : ""}
            </Text>
          ) : null}
          {item.reply_to ? (
            <View style={styles.replyPreview}>
              <Text style={[styles.replyName, { color: mine ? colors.onBrandPrimary : colors.brandSecondary }]}>{item.reply_to.sender_name}</Text>
              <Text style={[styles.replyText, { color: onText }]} numberOfLines={1}>
                {item.reply_to.has_attachment ? "📷 " : ""}
                {item.reply_to.message || t("photo")}
              </Text>
            </View>
          ) : null}
          {item.attachments?.length ? (
            <Image source={{ uri: fileUrl(item.attachments[0]) }} style={styles.chatImg} contentFit="cover" />
          ) : null}
          {item.message ? <MessageText text={item.message} color={onText} /> : null}
          <View style={styles.footerRow}>
            <Text style={[styles.msgTime, { color: mine ? colors.onBrandPrimary : colors.muted }]}>{timeOf(item.created_at)}</Text>
            {mine ? (
              <View style={{ flexDirection: "row", marginLeft: 2 }}>
                <Feather name="check" size={13} color={colors.onBrandPrimary} />
                {readByOthers ? <Feather name="check" size={13} color={colors.info} style={{ marginLeft: -6 }} /> : null}
              </View>
            ) : null}
          </View>
        </View>
      </Pressable>
    );
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <View style={styles.groupIcon}>
          <Feather name="users" size={20} color={colors.brandPrimary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.groupName}>
            {t("family_group")} {data?.room_name ?? ""}
          </Text>
          <Text style={styles.groupSub}>{allMessages.length} pesan</Text>
        </View>
        {isAdmin && aliveOnly ? (
          <View style={styles.adminBadge} testID="admin-view-badge">
            <Feather name="eye" size={12} color={colors.onBrandPrimary} />
            <Text style={styles.adminBadgeText}>{t("admin_view")}</Text>
          </View>
        ) : null}
      </View>

      <View style={styles.filterBar}>
        {aliveOnly ? (
          <View style={styles.toggleRow}>
            <LinearGradient colors={brandGradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.toggleGrad}>
              <Feather name="heart" size={16} color={colors.onBrandPrimary} />
              <Text style={styles.toggleLabel}>{t("alive_only_filter")}</Text>
              <Switch value={aliveOnly} onValueChange={setAliveOnly} testID="alive-toggle" />
            </LinearGradient>
          </View>
        ) : (
          <View style={styles.toggleInactive}>
            <Feather name="users" size={16} color={colors.muted} />
            <Text style={styles.toggleLabelInactive}>{t("alive_only_filter")}</Text>
            <Switch value={aliveOnly} onValueChange={setAliveOnly} testID="alive-toggle" />
          </View>
        )}
        <Text style={styles.statsText}>
          {data?.alive_count ?? 0} {t("living_count_a")} {data?.total_count ?? 0} {t("living_count_b")}
        </Text>
        <Pressable style={styles.nameFilter} onPress={() => setNamePickerOpen(true)} testID="name-filter">
          <Feather name="filter" size={14} color={colors.onSurfaceSecondary} />
          <Text style={styles.nameFilterText}>{filterName}</Text>
          {filterPersonId ? <Feather name="x" size={14} color={colors.muted} onPress={() => setFilterPersonId(null)} /> : <Feather name="chevron-down" size={14} color={colors.muted} />}
        </Pressable>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior="translate-with-padding" keyboardVerticalOffset={0}>
        {visible.length === 0 ? (
          <View style={styles.empty}>
            <Feather name="message-circle" size={36} color={colors.muted} />
            <Text style={styles.emptyText}>{canChat ? t("type_message") : t("viewer_readonly")}</Text>
          </View>
        ) : (
          <FlatList
            ref={listRef}
            data={visible}
            keyExtractor={(m) => m.id}
            renderItem={renderItem}
            contentContainerStyle={{ paddingVertical: 12 }}
            onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
          />
        )}

        {replyTo ? (
          <View style={styles.replyBar}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.replyName, { color: colors.brandSecondary }]}>
                {t("replying_to")} {replyTo.sender_name}
              </Text>
              <Text style={[styles.replyText, { color: colors.onSurfaceSecondary }]} numberOfLines={1}>
                {replyTo.message || t("photo")}
              </Text>
            </View>
            <Pressable onPress={() => setReplyTo(null)} testID="cancel-reply">
              <Feather name="x" size={18} color={colors.muted} />
            </Pressable>
          </View>
        ) : null}

        {canChat ? (
          <View style={[styles.inputBar, { paddingBottom: insets.bottom + 8 }]}>
            <Pressable style={styles.iconBtn} onPress={sendPhoto} testID="chat-photo-button">
              <Feather name="image" size={22} color={colors.muted} />
            </Pressable>
            <Pressable style={styles.iconBtn} onPress={() => setMentionOpen(true)} testID="chat-mention-button">
              <Feather name="at-sign" size={20} color={colors.muted} />
            </Pressable>
            <TextInput
              testID="chat-input"
              style={styles.input}
              placeholder={t("type_message")}
              placeholderTextColor={colors.muted}
              value={text}
              onChangeText={setText}
              multiline
            />
            <Pressable style={[styles.iconBtn, styles.sendBtn]} onPress={() => doSend()} disabled={sending} testID="chat-send-button">
              <Feather name="send" size={20} color={colors.onBrandPrimary} />
            </Pressable>
          </View>
        ) : (
          <View style={[styles.readonly, { paddingBottom: insets.bottom + 12 }]}>
            <Text style={styles.readonlyText}>{t("viewer_readonly")}</Text>
          </View>
        )}
      </KeyboardAvoidingView>

      {/* Name filter picker */}
      <Modal visible={namePickerOpen} transparent animationType="slide" onRequestClose={() => setNamePickerOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setNamePickerOpen(false)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <Text style={styles.sheetTitle}>{t("filter_by_name")}</Text>
            <FlatList
              data={[{ id: "__all__", name: t("all_members") }, ...alivePeople]}
              keyExtractor={(p) => p.id}
              renderItem={({ item }) => (
                <Pressable
                  style={styles.pickRow}
                  onPress={() => {
                    setFilterPersonId(item.id === "__all__" ? null : item.id);
                    setNamePickerOpen(false);
                  }}
                  testID={`namefilter-${item.id}`}
                >
                  <Feather name={item.id === "__all__" ? "users" : "user"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.pickText}>{item.name}</Text>
                </Pressable>
              )}
            />
          </Pressable>
        </Pressable>
      </Modal>

      {/* Mention picker */}
      <Modal visible={mentionOpen} transparent animationType="slide" onRequestClose={() => setMentionOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setMentionOpen(false)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <Text style={styles.sheetTitle}>{t("mention")}</Text>
            <FlatList
              data={members.filter((m: any) => m.user_id !== user?.user_id)}
              keyExtractor={(m) => m.user_id}
              renderItem={({ item }) => (
                <Pressable style={styles.pickRow} onPress={() => addMention(item)} testID={`mention-${item.user_id}`}>
                  <Feather name="at-sign" size={18} color={colors.brandSecondary} />
                  <Text style={styles.pickText}>{item.name}</Text>
                </Pressable>
              )}
              ListEmptyComponent={<Text style={[styles.emptyText, { padding: 20 }]}>-</Text>}
            />
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}
