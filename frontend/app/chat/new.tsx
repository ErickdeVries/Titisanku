import { useState } from "react";
import { View, Text, Pressable, FlatList, TextInput, ActivityIndicator, Alert } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { chatContacts, openDirect, createGroup, fileUrl, ChatContact } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useTree } from "@/src/tree-context";
import { useI18n } from "@/src/i18n";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  backBtn: { width: 36, height: 36, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  groupCta: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingVertical: 16 },
  groupIcon: { width: 46, height: 46, borderRadius: 999, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  groupCtaText: { fontFamily: fonts.semibold, fontSize: 15, color: c.brandSecondary },
  sectionLabel: { fontFamily: fonts.medium, fontSize: 12, color: c.muted, paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 },
  row: { flexDirection: "row", alignItems: "center", gap: 14, paddingHorizontal: 16, paddingVertical: 12 },
  avatar: { width: 46, height: 46, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: "100%", height: "100%" },
  name: { fontFamily: fonts.semibold, fontSize: 15, color: c.onSurface, flex: 1 },
  check: { width: 24, height: 24, borderRadius: 999, borderWidth: 2, borderColor: c.borderStrong, alignItems: "center", justifyContent: "center" },
  checkOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  input: { backgroundColor: c.surfaceTertiary, marginHorizontal: 16, marginVertical: 12, borderRadius: 14, paddingHorizontal: 16, paddingVertical: 14, fontFamily: fonts.regular, fontSize: 15, color: c.onSurface },
  searchBar: { flexDirection: "row", alignItems: "center", gap: 10, marginHorizontal: 16, marginTop: 8, marginBottom: 4, backgroundColor: c.surfaceTertiary, borderRadius: 12, paddingHorizontal: 14, height: 44 },
  searchInput: { flex: 1, fontFamily: fonts.regular, fontSize: 15, color: c.onSurface },
  chipsWrap: { paddingTop: 4 },
  chipsRow: { paddingHorizontal: 16, gap: 14, paddingVertical: 6 },
  chip: { alignItems: "center", width: 56, gap: 4 },
  chipAvatar: { width: 46, height: 46, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  chipRemove: { position: "absolute", top: -2, right: -2, width: 18, height: 18, borderRadius: 999, backgroundColor: c.muted, alignItems: "center", justifyContent: "center", borderWidth: 1.5, borderColor: c.surface },
  chipName: { fontFamily: fonts.regular, fontSize: 11, color: c.onSurfaceSecondary },
  footer: { padding: 16, borderTopWidth: 1, borderTopColor: c.divider },
  createBtn: { height: 52, borderRadius: 16, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  createText: { fontFamily: fonts.semibold, fontSize: 16, color: c.onBrandPrimary },
  empty: { padding: 40, alignItems: "center" },
  emptyText: { fontFamily: fonts.regular, fontSize: 14, color: c.muted, textAlign: "center" },
}));

export default function NewChatScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const { user } = useAuth();
  const { activeTree } = useTree();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();

  const { data } = useQuery({ queryKey: ["chatContacts"], queryFn: chatContacts });
  const contacts = data?.contacts ?? [];
  const role = activeTree?.role ?? user?.role;
  const canGroup = role === "admin" || role === "editor" || !!user?.is_superadmin;

  const [groupMode, setGroupMode] = useState(false);
  const [groupName, setGroupName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");

  const q = search.trim().toLowerCase();
  const filtered = q ? contacts.filter((c) => c.name.toLowerCase().includes(q)) : contacts;
  const selectedContacts = contacts.filter((c) => selected.has(c.user_id));

  const directMut = useMutation({
    mutationFn: (uid: string) => openDirect(uid),
    onSuccess: (room) => {
      qc.invalidateQueries({ queryKey: ["chatRooms"] });
      router.replace(`/chat/${room.id}`);
    },
    onError: () => Alert.alert(t("error_generic")),
  });

  const groupMut = useMutation({
    mutationFn: () => createGroup(groupName.trim(), Array.from(selected)),
    onSuccess: (room) => {
      qc.invalidateQueries({ queryKey: ["chatRooms"] });
      router.replace(`/chat/${room.id}`);
    },
    onError: () => Alert.alert(t("error_generic")),
  });

  const toggle = (uid: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(uid)) n.delete(uid); else n.add(uid);
      return n;
    });

  const renderContact = ({ item }: { item: ChatContact }) => {
    const on = selected.has(item.user_id);
    return (
      <Pressable
        style={styles.row}
        testID={`contact-${item.user_id}`}
        onPress={() => (groupMode ? toggle(item.user_id) : directMut.mutate(item.user_id))}
      >
        <View style={styles.avatar}>
          {item.picture ? (
            <Image source={{ uri: fileUrl(item.picture) }} style={styles.avatarImg} contentFit="cover" />
          ) : (
            <Feather name="user" size={20} color={colors.muted} />
          )}
        </View>
        <Text style={styles.name} numberOfLines={1}>{item.name}</Text>
        {groupMode ? (
          <View style={[styles.check, on && styles.checkOn]}>
            {on ? <Feather name="check" size={14} color={colors.onBrandPrimary} /> : null}
          </View>
        ) : (
          <Feather name="message-circle" size={18} color={colors.brandSecondary} />
        )}
      </Pressable>
    );
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.backBtn} onPress={() => router.back()} hitSlop={8} testID="new-chat-back">
          <Feather name="chevron-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{groupMode ? t("new_group") : t("new_chat")}</Text>
      </View>

      {!groupMode && canGroup ? (
        <Pressable style={styles.groupCta} onPress={() => setGroupMode(true)} testID="start-group">
          <View style={styles.groupIcon}>
            <Feather name="users" size={22} color={colors.onBrandPrimary} />
          </View>
          <Text style={styles.groupCtaText}>{t("new_group")}</Text>
        </Pressable>
      ) : null}

      {groupMode ? (
        <TextInput
          testID="group-name-input"
          style={styles.input}
          placeholder={t("group_name_placeholder")}
          placeholderTextColor={colors.muted}
          value={groupName}
          onChangeText={setGroupName}
        />
      ) : null}

      {groupMode && selectedContacts.length ? (
        <View style={styles.chipsWrap}>
          <FlatList
            horizontal
            data={selectedContacts}
            keyExtractor={(c) => c.user_id}
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chipsRow}
            renderItem={({ item }) => (
              <Pressable style={styles.chip} onPress={() => toggle(item.user_id)} testID={`chip-${item.user_id}`}>
                <View style={styles.chipAvatar}>
                  {item.picture ? (
                    <Image source={{ uri: fileUrl(item.picture) }} style={styles.avatarImg} contentFit="cover" />
                  ) : (
                    <Feather name="user" size={16} color={colors.muted} />
                  )}
                  <View style={styles.chipRemove}>
                    <Feather name="x" size={11} color={colors.onBrandPrimary} />
                  </View>
                </View>
                <Text style={styles.chipName} numberOfLines={1}>{item.name.split(" ")[0]}</Text>
              </Pressable>
            )}
          />
        </View>
      ) : null}

      <View style={styles.searchBar}>
        <Feather name="search" size={18} color={colors.muted} />
        <TextInput
          testID="contact-search"
          style={styles.searchInput}
          placeholder={t("search_contacts")}
          placeholderTextColor={colors.muted}
          value={search}
          onChangeText={setSearch}
        />
        {search ? (
          <Pressable onPress={() => setSearch("")} hitSlop={8}>
            <Feather name="x" size={18} color={colors.muted} />
          </Pressable>
        ) : null}
      </View>

      <Text style={styles.sectionLabel}>
        {groupMode ? `${t("select_members")} · ${selected.size} ${t("members_selected")}` : t("contacts")}
      </Text>

      <FlatList
        data={filtered}
        keyExtractor={(c) => c.user_id}
        renderItem={renderContact}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>{t("no_contacts")}</Text>
          </View>
        }
      />

      {groupMode ? (
        <View style={[styles.footer, { paddingBottom: insets.bottom + 16 }]}>
          <Pressable
            testID="create-group-submit"
            style={[styles.createBtn, { opacity: !groupName.trim() || selected.size === 0 || groupMut.isPending ? 0.6 : 1 }]}
            disabled={!groupName.trim() || selected.size === 0 || groupMut.isPending}
            onPress={() => groupMut.mutate()}
          >
            {groupMut.isPending ? (
              <ActivityIndicator color={colors.onBrandPrimary} />
            ) : (
              <Text style={styles.createText}>{t("create_group")}</Text>
            )}
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}
