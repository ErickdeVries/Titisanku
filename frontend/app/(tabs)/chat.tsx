import { useEffect, useRef, useState } from "react";
import { View, Text, Pressable, TextInput, FlatList, Platform } from "react-native";
import { Image } from "expo-image";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import * as ImagePicker from "expo-image-picker";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getChat, sendChat, uploadPhoto, fileUrl, markNotificationsRead } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surfaceSecondary },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider },
  groupIcon: { width: 42, height: 42, borderRadius: 999, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  groupName: { fontFamily: fonts.bold, fontSize: 16, color: c.onSurface },
  groupSub: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  row: { flexDirection: "row", marginVertical: 4, paddingHorizontal: 12, gap: 8, alignItems: "flex-end" },
  rowMine: { justifyContent: "flex-end" },
  avatar: { width: 30, height: 30, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: "100%", height: "100%" },
  bubble: { maxWidth: "76%", borderRadius: 16, padding: 10, gap: 4 },
  bubbleMine: { backgroundColor: c.brandPrimary, borderBottomRightRadius: 4 },
  bubbleOther: { backgroundColor: c.surface, borderBottomLeftRadius: 4 },
  senderName: { fontFamily: fonts.semibold, fontSize: 12, color: c.brandSecondary },
  msgText: { fontFamily: fonts.regular, fontSize: 15 },
  msgTime: { fontFamily: fonts.regular, fontSize: 10, alignSelf: "flex-end" },
  chatImg: { width: 200, height: 200, borderRadius: 10, backgroundColor: c.surfaceTertiary },
  replyPreview: { borderLeftWidth: 3, borderLeftColor: c.brandSecondary, paddingLeft: 8, paddingVertical: 2, marginBottom: 2, opacity: 0.9 },
  replyName: { fontFamily: fonts.semibold, fontSize: 11 },
  replyText: { fontFamily: fonts.regular, fontSize: 12 },
  swipeHint: { position: "absolute", right: 8, top: 8 },
  inputBar: { flexDirection: "row", alignItems: "flex-end", gap: 8, paddingHorizontal: 12, paddingTop: 8, backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.divider },
  input: { flex: 1, backgroundColor: c.surfaceTertiary, borderRadius: 22, paddingHorizontal: 16, paddingVertical: 10, maxHeight: 110, fontFamily: fonts.regular, fontSize: 15, color: c.onSurface },
  iconBtn: { width: 44, height: 44, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  sendBtn: { backgroundColor: c.brandPrimary },
  readonly: { padding: 16, alignItems: "center", backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.divider },
  readonlyText: { fontFamily: fonts.medium, fontSize: 13, color: c.muted },
  replyBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: c.surfaceTertiary, marginHorizontal: 12, marginTop: 8, borderRadius: 10, padding: 8 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: 40, gap: 10 },
  emptyText: { fontFamily: fonts.regular, fontSize: 14, color: c.muted, textAlign: "center" },
}));

function timeOf(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
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
  const [text, setText] = useState("");
  const [replyTo, setReplyTo] = useState<any>(null);
  const [sending, setSending] = useState(false);

  const canChat = user?.role === "admin" || user?.role === "editor";
  const messages = data?.messages ?? [];

  useEffect(() => {
    markNotificationsRead("chat").then(() => qc.invalidateQueries({ queryKey: ["notifications"] }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (messages.length) setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 200);
  }, [messages.length]);

  const doSend = async (attachments: string[] = []) => {
    if (!text.trim() && attachments.length === 0) return;
    setSending(true);
    try {
      await sendChat({ message: text.trim(), attachments, reply_to: replyTo?.id ?? null });
      setText("");
      setReplyTo(null);
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
      await sendChat({ message: text.trim(), attachments: [path], reply_to: replyTo?.id ?? null });
      setText("");
      setReplyTo(null);
      await qc.invalidateQueries({ queryKey: ["chat"] });
    } catch (e) {
      console.log("photo send error", e);
    } finally {
      setSending(false);
    }
  };

  const renderItem = ({ item }: { item: any }) => {
    const mine = item.sender_id === user?.user_id;
    const onText = mine ? colors.onBrandPrimary : colors.onSurface;
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
        <View style={[styles.bubble, mine ? styles.bubbleMine : styles.bubbleOther]}>
          {!mine ? <Text style={styles.senderName}>{item.sender_name}</Text> : null}
          {item.reply_to ? (
            <View style={styles.replyPreview}>
              <Text style={[styles.replyName, { color: mine ? colors.onBrandPrimary : colors.brandSecondary }]}>
                {item.reply_to.sender_name}
              </Text>
              <Text style={[styles.replyText, { color: onText }]} numberOfLines={1}>
                {item.reply_to.has_attachment ? "📷 " : ""}
                {item.reply_to.message || t("photo")}
              </Text>
            </View>
          ) : null}
          {item.attachments?.length ? (
            <Image source={{ uri: fileUrl(item.attachments[0]) }} style={styles.chatImg} contentFit="cover" />
          ) : null}
          {item.message ? <Text style={[styles.msgText, { color: onText }]}>{item.message}</Text> : null}
          <Text style={[styles.msgTime, { color: mine ? colors.onBrandPrimary : colors.muted }]}>{timeOf(item.created_at)}</Text>
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
        <View>
          <Text style={styles.groupName}>
            {t("family_group")} {data?.room_name ?? ""}
          </Text>
          <Text style={styles.groupSub}>{messages.length} pesan</Text>
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

        {canChat ? (
          <View style={[styles.inputBar, { paddingBottom: insets.bottom + 8 }]}>
            <Pressable style={styles.iconBtn} onPress={sendPhoto} testID="chat-photo-button">
              <Feather name="image" size={22} color={colors.muted} />
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
    </View>
  );
}
