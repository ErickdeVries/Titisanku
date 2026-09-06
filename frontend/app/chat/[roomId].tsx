import { useEffect, useMemo, useRef, useState } from "react";
import { View, Text, Pressable, TextInput, FlatList, Modal } from "react-native";
import { Image } from "expo-image";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import * as ImagePicker from "expo-image-picker";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getChat, sendChat, deleteChat, setTyping, uploadPhoto, fileUrl, markNotificationsRead } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surfaceSecondary },
  header: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 12, paddingBottom: 12, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider },
  backBtn: { width: 36, height: 36, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  roomIcon: { width: 40, height: 40, borderRadius: 999, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  roomIconImg: { width: "100%", height: "100%" },
  roomName: { fontFamily: fonts.bold, fontSize: 16, color: c.onSurface },
  roomSub: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  typingText: { fontFamily: fonts.regular, fontSize: 12, color: c.brandSecondary, fontStyle: "italic", paddingHorizontal: 16, paddingTop: 6 },
  row: { flexDirection: "row", marginVertical: 4, paddingHorizontal: 12, gap: 8, alignItems: "flex-end" },
  rowMine: { justifyContent: "flex-end" },
  avatar: { width: 30, height: 30, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: "100%", height: "100%" },
  bubble: { maxWidth: "76%", borderRadius: 16, padding: 10, gap: 4 },
  bubbleMine: { backgroundColor: c.brandPrimary, borderBottomRightRadius: 4 },
  bubbleOther: { backgroundColor: c.surface, borderBottomLeftRadius: 4 },
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

function MessageText({ text, color, styles }: { text: string; color: string; styles: any }) {
  const parts = text.split(/(@\S+)/g);
  return (
    <Text style={[styles.msgText, { color }]}>
      {parts.map((p, i) =>
        p.startsWith("@") ? (
          <Text key={i} style={[styles.mention, { color }]}>{p}</Text>
        ) : (
          p
        ),
      )}
    </Text>
  );
}

export default function ChatRoomScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const listRef = useRef<FlatList>(null);
  const { roomId } = useLocalSearchParams<{ roomId: string }>();

  const { data } = useQuery({ queryKey: ["chat", roomId], queryFn: () => getChat(roomId), refetchInterval: 3000 });
  const [text, setText] = useState("");
  const [replyTo, setReplyTo] = useState<any>(null);
  const [sending, setSending] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentions, setMentions] = useState<string[]>([]);
  const [actionMsg, setActionMsg] = useState<any>(null);
  const lastTyped = useRef(0);

  const messages = data?.messages ?? [];
  const members = data?.members ?? [];
  const typing = (data?.typing ?? []) as string[];
  const canChat = data?.can_send ?? false;
  const roomType = data?.room_type ?? "family";
  const roomName = data?.room_name ?? t("family_group");
  const isAdmin = user?.role === "admin";

  const onType = (v: string) => {
    setText(v);
    const now = Date.now();
    if (now - lastTyped.current > 2000) {
      lastTyped.current = now;
      setTyping(roomId).catch(() => {});
    }
  };

  const removeMessage = async (msgId: string) => {
    setActionMsg(null);
    try {
      await deleteChat(msgId);
      await qc.invalidateQueries({ queryKey: ["chat", roomId] });
    } catch (e) {
      console.log("delete chat error", e);
    }
  };

  useEffect(() => {
    markNotificationsRead("chat").then(() => qc.invalidateQueries({ queryKey: ["notifications"] }));
    qc.invalidateQueries({ queryKey: ["chatRooms"] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (messages.length) setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 200);
  }, [messages.length]);

  const resetInput = () => {
    setText("");
    setReplyTo(null);
    setMentions([]);
  };

  const doSend = async (attachments: string[] = []) => {
    if (!text.trim() && attachments.length === 0) return;
    setSending(true);
    try {
      await sendChat({ message: text.trim(), attachments, reply_to: replyTo?.id ?? null, mentions }, roomId);
      resetInput();
      await qc.invalidateQueries({ queryKey: ["chat", roomId] });
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
      await sendChat({ message: text.trim(), attachments: [path], reply_to: replyTo?.id ?? null, mentions }, roomId);
      resetInput();
      await qc.invalidateQueries({ queryKey: ["chat", roomId] });
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
    const readByOthers = (item.read_by ?? []).length > 0;
    return (
      <Pressable
        style={[styles.row, mine && styles.rowMine]}
        onLongPress={() => canChat && setActionMsg(item)}
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
        <View style={[styles.bubble, mine ? styles.bubbleMine : styles.bubbleOther]}>
          {!mine && roomType !== "direct" ? <Text style={styles.senderName}>{item.sender_name}</Text> : null}
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
          {item.message ? <MessageText text={item.message} color={onText} styles={styles} /> : null}
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
        <Pressable style={styles.backBtn} onPress={() => router.back()} hitSlop={8} testID="chat-back">
          <Feather name="chevron-left" size={24} color={colors.onSurface} />
        </Pressable>
        <View style={styles.roomIcon}>
          {data?.room_picture ? (
            <Image source={{ uri: fileUrl(data.room_picture) }} style={styles.roomIconImg} contentFit="cover" />
          ) : (
            <Feather name={roomType === "direct" ? "user" : "users"} size={18} color={colors.brandPrimary} />
          )}
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.roomName} numberOfLines={1}>{roomName}</Text>
          <Text style={styles.roomSub}>
            {roomType === "direct" ? t("direct_chat") : `${data?.members?.length ?? 0} ${t("members_count")}`}
          </Text>
        </View>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior="translate-with-padding" keyboardVerticalOffset={0}>
        {messages.length === 0 ? (
          <View style={styles.empty}>
            <Feather name="message-circle" size={36} color={colors.muted} />
            <Text style={styles.emptyText}>{canChat ? t("type_message") : t("viewer_readonly")}</Text>
          </View>
        ) : (
          <FlatList
            ref={listRef}
            data={messages}
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

        {typing.length ? (
          <Text style={styles.typingText} testID="typing-indicator">
            {typing.join(", ")} {t("is_typing")}
          </Text>
        ) : null}

        {canChat ? (
          <View style={[styles.inputBar, { paddingBottom: insets.bottom + 8 }]}>
            <Pressable style={styles.iconBtn} onPress={sendPhoto} testID="chat-photo-button">
              <Feather name="image" size={22} color={colors.muted} />
            </Pressable>
            {roomType !== "direct" ? (
              <Pressable style={styles.iconBtn} onPress={() => setMentionOpen(true)} testID="chat-mention-button">
                <Feather name="at-sign" size={20} color={colors.muted} />
              </Pressable>
            ) : null}
            <TextInput
              testID="chat-input"
              style={styles.input}
              placeholder={t("type_message")}
              placeholderTextColor={colors.muted}
              value={text}
              onChangeText={onType}
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

      {/* Message action sheet (reply / delete) */}
      <Modal visible={!!actionMsg} transparent animationType="slide" onRequestClose={() => setActionMsg(null)}>
        <Pressable style={styles.modalBg} onPress={() => setActionMsg(null)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <Text style={styles.sheetTitle}>{actionMsg?.sender_name}</Text>
            <Pressable
              style={styles.pickRow}
              onPress={() => { setReplyTo(actionMsg); setActionMsg(null); }}
              testID="action-reply"
            >
              <Feather name="corner-up-left" size={18} color={colors.brandSecondary} />
              <Text style={styles.pickText}>{t("reply")}</Text>
            </Pressable>
            {actionMsg && (isAdmin || actionMsg.sender_id === user?.user_id) ? (
              <Pressable style={styles.pickRow} onPress={() => removeMessage(actionMsg.id)} testID="action-delete">
                <Feather name="trash-2" size={18} color={colors.error} />
                <Text style={[styles.pickText, { color: colors.error }]}>{t("delete")}</Text>
              </Pressable>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}
