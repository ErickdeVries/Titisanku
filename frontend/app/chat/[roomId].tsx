import { useEffect, useMemo, useRef, useState } from "react";
import { View, Text, Pressable, TextInput, FlatList, Modal, Switch, Alert, Platform } from "react-native";
import { Image } from "expo-image";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import * as ImagePicker from "expo-image-picker";
import * as Haptics from "expo-haptics";
import { useAudioPlayer } from "expo-audio";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, { useSharedValue, useAnimatedStyle, withSpring, runOnJS } from "react-native-reanimated";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getChat, sendChat, deleteChat, setTyping, uploadPhoto, fileUrl, markNotificationsRead, muteRoom, leaveGroup } from "@/src/api";
import { compressImage } from "@/src/utils/image";
import { storage } from "@/src/utils/storage";
import { CHAT_SOUND_STORAGE_KEY, ChatSound, DEFAULT_CHAT_SOUND, soundByKey } from "@/src/utils/chat-sounds";
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
  mentionBox: { maxHeight: 220, marginHorizontal: 12, marginBottom: 6, backgroundColor: c.surface, borderRadius: 14, borderWidth: 1, borderColor: c.divider, overflow: "hidden" },
  mentionRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 14, paddingVertical: 10 },
  mentionAvatar: { width: 32, height: 32, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  mentionName: { fontFamily: fonts.medium, fontSize: 14, color: c.onSurface, flex: 1 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: 40, gap: 10 },
  emptyText: { fontFamily: fonts.regular, fontSize: 14, color: c.muted, textAlign: "center" },
  modalBg: { flex: 1, backgroundColor: "rgba(15,23,42,0.4)", justifyContent: "flex-end" },
  sheet: { backgroundColor: c.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: "70%" },
  sheetTitle: { fontFamily: fonts.bold, fontSize: 17, color: c.onSurface, padding: 20, paddingBottom: 8 },
  pickRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 20, paddingVertical: 14 },
  pickText: { fontFamily: fonts.medium, fontSize: 15, color: c.onSurface },
  readHeadRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 20, paddingTop: 8, paddingBottom: 6 },
  readHead: { fontFamily: fonts.semibold, fontSize: 13, color: c.onSurfaceSecondary, textTransform: "uppercase", letterSpacing: 0.5 },
  readEmpty: { fontFamily: fonts.regular, fontSize: 13, color: c.muted, paddingHorizontal: 20, paddingBottom: 4 },
  readRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 20, paddingVertical: 8 },
  readAvatar: { width: 34, height: 34, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  readAvatarImg: { width: "100%", height: "100%" },
  readName: { fontFamily: fonts.medium, fontSize: 15, color: c.onSurface },
}));

function timeOf(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function replyHaptic() {
  if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
}

function SwipeableMessage({
  children,
  onReply,
  enabled,
  accent,
}: {
  children: React.ReactNode;
  onReply: () => void;
  enabled: boolean;
  accent: string;
}) {
  const tx = useSharedValue(0);
  const fired = useSharedValue(false);
  const pan = Gesture.Pan()
    .enabled(enabled)
    .activeOffsetX(16)
    .failOffsetY([-12, 12])
    .onUpdate((e) => {
      tx.value = Math.max(0, Math.min(e.translationX, 84));
      if (tx.value > 56 && !fired.value) {
        fired.value = true;
        runOnJS(replyHaptic)();
        runOnJS(onReply)();
      }
    })
    .onEnd(() => {
      tx.value = withSpring(0, { damping: 18 });
      fired.value = false;
    });
  const rowStyle = useAnimatedStyle(() => ({ transform: [{ translateX: tx.value }] }));
  const iconStyle = useAnimatedStyle(() => ({ opacity: Math.min(1, tx.value / 56) }));
  return (
    <GestureDetector gesture={pan}>
      <Animated.View>
        <Animated.View style={[{ position: "absolute", left: 18, top: 0, bottom: 0, justifyContent: "center" }, iconStyle]}>
          <Feather name="corner-up-left" size={20} color={accent} />
        </Animated.View>
        <Animated.View style={rowStyle}>{children}</Animated.View>
      </Animated.View>
    </GestureDetector>
  );
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
  const dingPlayer = useAudioPlayer(require("../../assets/ding.wav"));
  const soundRef = useRef<ChatSound>(soundByKey(DEFAULT_CHAT_SOUND));
  const lastMsgId = useRef<string | null>(null);
  const initialized = useRef(false);

  useEffect(() => {
    storage.getItem<string>(CHAT_SOUND_STORAGE_KEY, DEFAULT_CHAT_SOUND).then((v) => {
      const s = soundByKey(v);
      soundRef.current = s;
      if (s.asset) {
        try {
          dingPlayer.replace(s.asset);
        } catch {}
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { data } = useQuery({ queryKey: ["chat", roomId], queryFn: () => getChat(roomId), refetchInterval: 3000 });
  const [text, setText] = useState("");
  const [replyTo, setReplyTo] = useState<any>(null);
  const [sending, setSending] = useState(false);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentions, setMentions] = useState<string[]>([]);
  const [actionMsg, setActionMsg] = useState<any>(null);
  const [readInfoMsg, setReadInfoMsg] = useState<any>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const lastTyped = useRef(0);

  const messages = data?.messages ?? [];
  const members = data?.members ?? [];
  const typing = (data?.typing ?? []) as string[];
  const canChat = data?.can_send ?? false;
  const roomType = data?.room_type ?? "family";
  const roomName = data?.room_name ?? t("family_group");
  const canManage = data?.can_manage ?? false;
  const muted = data?.muted ?? false;
  const isAdmin = user?.role === "admin";

  const toggleMute = async (val: boolean) => {
    try {
      await muteRoom(roomId, val);
      await qc.invalidateQueries({ queryKey: ["chat", roomId] });
      qc.invalidateQueries({ queryKey: ["chatRooms"] });
    } catch (e) {
      console.log("mute error", e);
    }
  };

  const doLeaveGroup = async () => {
    try {
      await leaveGroup(roomId);
      qc.invalidateQueries({ queryKey: ["chatRooms"] });
      setSettingsOpen(false);
      router.replace("/(tabs)/chat");
    } catch (e) {
      console.log("leave group error", e);
    }
  };

  const onType = (v: string) => {
    setText(v);
    if (roomType !== "direct") {
      const m = /(^|\s)@([^\s@]*)$/.exec(v);
      setMentionQuery(m ? m[2] : null);
    }
    const now = Date.now();
    if (now - lastTyped.current > 2000) {
      lastTyped.current = now;
      setTyping(roomId).catch(() => {});
    }
  };

  const mentionCandidates =
    mentionQuery === null
      ? []
      : members
          .filter((m: any) => m.user_id !== user?.user_id)
          .filter((m: any) => m.name.toLowerCase().includes(mentionQuery.toLowerCase()));

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

  // Haptic + "ding" sound when a NEW incoming message arrives (not mine, not muted).
  useEffect(() => {
    if (!messages.length) return;
    const last = messages[messages.length - 1];
    if (!initialized.current) {
      initialized.current = true;
      lastMsgId.current = last.id;
      return;
    }
    if (last.id !== lastMsgId.current) {
      lastMsgId.current = last.id;
      if (last.sender_id !== user?.user_id && !muted) {
        if (Platform.OS !== "web") {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        }
        if (soundRef.current.asset) {
          try {
            dingPlayer.seekTo(0);
            dingPlayer.play();
          } catch {}
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  const resetInput = () => {
    setText("");
    setReplyTo(null);
    setMentions([]);
    setMentionQuery(null);
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
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.8 });
    if (res.canceled || !res.assets?.length) return;
    setSending(true);
    try {
      const compressed = await compressImage(res.assets[0].uri);
      const path = await uploadPhoto(compressed);
      await sendChat({ message: text.trim(), attachments: [path], reply_to: replyTo?.id ?? null, mentions }, roomId);
      resetInput();
      await qc.invalidateQueries({ queryKey: ["chat", roomId] });
    } catch (e: any) {
      console.log("photo send error", e);
      Alert.alert(t("photo"), e?.message || "Upload failed");
    } finally {
      setSending(false);
    }
  };

  const insertMention = (m: any) => {
    setText((prev) => prev.replace(/(^|\s)@([^\s@]*)$/, (_full, pre) => `${pre}@${m.name} `));
    setMentions((prev) => Array.from(new Set([...prev, m.user_id])));
    setMentionQuery(null);
  };

  const renderItem = ({ item }: { item: any }) => {
    const mine = item.sender_id === user?.user_id;
    const onText = mine ? colors.onBrandPrimary : colors.onSurface;
    const readByOthers = (item.read_by ?? []).length > 0;
    return (
      <SwipeableMessage enabled={canChat} onReply={() => setReplyTo(item)} accent={colors.brandSecondary}>
        <Pressable
          style={[styles.row, mine && styles.rowMine]}
          onLongPress={() => canChat && setActionMsg(item)}
          testID={`chat-msg-${item.id}`}
        >
        {!mine ? (
          <View style={styles.avatar}>
            {item.sender_picture ? (
              <Image source={{ uri: fileUrl(item.sender_picture) }} style={styles.avatarImg} contentFit="cover" />
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
      </SwipeableMessage>
    );
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.backBtn} onPress={() => router.back()} hitSlop={8} testID="chat-back">
          <Feather name="chevron-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Pressable
          style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: 10 }}
          onPress={() => { if (roomType !== "direct") router.push(`/chat/info/${roomId}`); }}
          disabled={roomType === "direct"}
          testID="chat-header-info"
        >
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
              {muted ? `${t("muted_label")} · ` : ""}
              {roomType === "direct" ? t("direct_chat") : `${data?.members?.length ?? 0} ${t("members_count")}`}
            </Text>
          </View>
        </Pressable>
        <Pressable style={styles.backBtn} onPress={() => setSettingsOpen(true)} hitSlop={8} testID="chat-settings">
          <Feather name="more-vertical" size={22} color={colors.onSurface} />
        </Pressable>
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

        {mentionCandidates.length > 0 ? (
          <View style={styles.mentionBox}>
            <FlatList
              data={mentionCandidates}
              keyExtractor={(m) => m.user_id}
              keyboardShouldPersistTaps="handled"
              renderItem={({ item }) => (
                <Pressable style={styles.mentionRow} onPress={() => insertMention(item)} testID={`mention-${item.user_id}`}>
                  <View style={styles.mentionAvatar}>
                    {item.picture ? (
                      <Image source={{ uri: fileUrl(item.picture) }} style={styles.avatarImg} contentFit="cover" />
                    ) : (
                      <Feather name="user" size={15} color={colors.muted} />
                    )}
                  </View>
                  <Text style={styles.mentionName} numberOfLines={1}>{item.name}</Text>
                </Pressable>
              )}
            />
          </View>
        ) : null}

        {canChat ? (
          <View style={[styles.inputBar, { paddingBottom: insets.bottom + 8 }]}>
            <Pressable style={styles.iconBtn} onPress={sendPhoto} testID="chat-photo-button">
              <Feather name="image" size={22} color={colors.muted} />
            </Pressable>
            {roomType !== "direct" ? (
              <Pressable
                style={styles.iconBtn}
                onPress={() => onType(text.length === 0 || text.endsWith(" ") ? `${text}@` : `${text} @`)}
                testID="chat-mention-button"
              >
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
            {actionMsg && actionMsg.sender_id === user?.user_id && roomType !== "direct" ? (
              <Pressable
                style={styles.pickRow}
                onPress={() => { setReadInfoMsg(actionMsg); setActionMsg(null); }}
                testID="action-info"
              >
                <Feather name="info" size={18} color={colors.brandSecondary} />
                <Text style={styles.pickText}>{t("message_info")}</Text>
              </Pressable>
            ) : null}
            {actionMsg && (isAdmin || actionMsg.sender_id === user?.user_id) ? (
              <Pressable style={styles.pickRow} onPress={() => removeMessage(actionMsg.id)} testID="action-delete">
                <Feather name="trash-2" size={18} color={colors.error} />
                <Text style={[styles.pickText, { color: colors.error }]}>{t("delete")}</Text>
              </Pressable>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>

      {/* Message read-info (who read this message) */}
      <Modal visible={!!readInfoMsg} transparent animationType="slide" onRequestClose={() => setReadInfoMsg(null)}>
        <Pressable style={styles.modalBg} onPress={() => setReadInfoMsg(null)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <Text style={styles.sheetTitle}>{t("message_info")}</Text>
            {(() => {
              const readBy: string[] = readInfoMsg?.read_by ?? [];
              const others = members.filter((m: any) => m.user_id !== readInfoMsg?.sender_id);
              const readers = others.filter((m: any) => readBy.includes(m.user_id));
              const pending = others.filter((m: any) => !readBy.includes(m.user_id));
              return (
                <View style={{ paddingBottom: insets.bottom + 16 }}>
                  <View style={styles.readHeadRow}>
                    <Feather name="check-circle" size={15} color={colors.info} />
                    <Text style={styles.readHead}>{t("read_by")} · {readers.length}</Text>
                  </View>
                  {readers.length === 0 ? <Text style={styles.readEmpty}>-</Text> : null}
                  {readers.map((m: any) => (
                    <View key={m.user_id} style={styles.readRow}>
                      <View style={styles.readAvatar}>
                        {m.picture ? <Image source={{ uri: fileUrl(m.picture) }} style={styles.readAvatarImg} contentFit="cover" /> : <Feather name="user" size={14} color={colors.muted} />}
                      </View>
                      <Text style={styles.readName}>{m.name}</Text>
                    </View>
                  ))}
                  <View style={[styles.readHeadRow, { marginTop: 14 }]}>
                    <Feather name="clock" size={15} color={colors.muted} />
                    <Text style={styles.readHead}>{t("delivered_to")} · {pending.length}</Text>
                  </View>
                  {pending.map((m: any) => (
                    <View key={m.user_id} style={styles.readRow}>
                      <View style={styles.readAvatar}>
                        {m.picture ? <Image source={{ uri: fileUrl(m.picture) }} style={styles.readAvatarImg} contentFit="cover" /> : <Feather name="user" size={14} color={colors.muted} />}
                      </View>
                      <Text style={styles.readName}>{m.name}</Text>
                    </View>
                  ))}
                </View>
              );
            })()}
          </Pressable>
        </Pressable>
      </Modal>

      {/* Chat settings sheet (mute + manage group) */}
      <Modal visible={settingsOpen} transparent animationType="slide" onRequestClose={() => setSettingsOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setSettingsOpen(false)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <Text style={styles.sheetTitle}>{t("chat_settings")}</Text>
            <View style={styles.pickRow}>
              <Feather name={muted ? "bell-off" : "bell"} size={18} color={colors.brandSecondary} />
              <Text style={[styles.pickText, { flex: 1 }]}>{t("mute_chat")}</Text>
              <Switch
                testID="mute-toggle"
                value={muted}
                onValueChange={toggleMute}
                trackColor={{ true: colors.brandPrimary, false: colors.border }}
                thumbColor="#FFFFFF"
              />
            </View>
            {canManage ? (
              <Pressable
                style={styles.pickRow}
                testID="manage-group-btn"
                onPress={() => { setSettingsOpen(false); router.push(`/chat/manage/${roomId}`); }}
              >
                <Feather name="settings" size={18} color={colors.brandSecondary} />
                <Text style={styles.pickText}>{t("manage_group")}</Text>
              </Pressable>
            ) : null}
            {roomType === "group" ? (
              <Pressable style={styles.pickRow} testID="leave-group-btn" onPress={doLeaveGroup}>
                <Feather name="log-out" size={18} color={colors.error} />
                <Text style={[styles.pickText, { color: colors.error }]}>{t("leave_group")}</Text>
              </Pressable>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}
