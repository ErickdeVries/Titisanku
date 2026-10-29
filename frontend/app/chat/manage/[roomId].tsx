import { useState } from "react";
import { View, Text, Pressable, FlatList, TextInput, ActivityIndicator, Alert } from "react-native";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useGoBack } from "@/src/hooks/useGoBack";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getChat, chatContacts, updateGroup, fileUrl, uploadPhoto, ChatContact } from "@/src/api";
import { compressImage } from "@/src/utils/image";
import { useI18n } from "@/src/i18n";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  backBtn: { width: 36, height: 36, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  label: { fontFamily: fonts.medium, fontSize: 12, color: c.muted, paddingHorizontal: 16, paddingTop: 14, paddingBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 },
  input: { backgroundColor: c.surfaceTertiary, marginHorizontal: 16, marginTop: 12, borderRadius: 14, paddingHorizontal: 16, paddingVertical: 14, fontFamily: fonts.regular, fontSize: 15, color: c.onSurface },
  photoWrap: { alignItems: "center", paddingTop: 20, paddingBottom: 4 },
  groupPhotoPick: { width: 88, height: 88, borderRadius: 999, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  photoEditBadge: { position: "absolute", bottom: 2, right: 2, width: 26, height: 26, borderRadius: 999, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: c.surface },
  row: { flexDirection: "row", alignItems: "center", gap: 14, paddingHorizontal: 16, paddingVertical: 12 },
  avatar: { width: 46, height: 46, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: "100%", height: "100%" },
  name: { fontFamily: fonts.semibold, fontSize: 15, color: c.onSurface, flex: 1 },
  check: { width: 24, height: 24, borderRadius: 999, borderWidth: 2, borderColor: c.borderStrong, alignItems: "center", justifyContent: "center" },
  checkOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  footer: { padding: 16, borderTopWidth: 1, borderTopColor: c.divider },
  saveBtn: { height: 52, borderRadius: 16, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  saveText: { fontFamily: fonts.semibold, fontSize: 16, color: c.onBrandPrimary },
}));

export default function ManageGroupScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const goBack = useGoBack("/");
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { roomId } = useLocalSearchParams<{ roomId: string }>();

  const { data: room } = useQuery({ queryKey: ["chat", roomId], queryFn: () => getChat(roomId) });
  const { data: contactsData } = useQuery({ queryKey: ["chatContacts"], queryFn: chatContacts });
  const contacts = contactsData?.contacts ?? [];

  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  // Edits made in this screen. Until the user touches a field the value is
  // derived from the loaded room, so no state has to be written from an effect.
  const [edits, setEdits] = useState<{
    name?: string;
    photo?: string | null;
    selected?: Set<string>;
  }>({});

  const nameValue = edits.name ?? room?.room_name ?? "";
  const photoValue = edits.photo !== undefined ? edits.photo : room?.room_picture ?? null;
  const selected =
    edits.selected ?? new Set<string>((room?.members ?? []).map((m: any) => m.user_id));

  const pickPhoto = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.8 });
    if (res.canceled || !res.assets?.length) return;
    setUploadingPhoto(true);
    try {
      const compressed = await compressImage(res.assets[0].uri, 512);
      const path = await uploadPhoto(compressed);
      setEdits((s) => ({ ...s, photo: path }));
    } catch (e: any) {
      Alert.alert(t("error_generic"), e?.message || "");
    } finally {
      setUploadingPhoto(false);
    }
  };

  const saveMut = useMutation({
    mutationFn: () => updateGroup(roomId, { name: nameValue.trim(), member_ids: Array.from(selected), picture: photoValue }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chat", roomId] });
      qc.invalidateQueries({ queryKey: ["chatRooms"] });
      goBack();
    },
    onError: () => Alert.alert(t("error_generic")),
  });

  const toggle = (uid: string) =>
    setEdits((s) => {
      const n = new Set(s.selected ?? selected);
      if (n.has(uid)) n.delete(uid);
      else n.add(uid);
      return { ...s, selected: n };
    });

  const renderContact = ({ item }: { item: ChatContact }) => {
    const on = selected.has(item.user_id);
    return (
      <Pressable style={styles.row} onPress={() => toggle(item.user_id)} testID={`manage-contact-${item.user_id}`}>
        <View style={styles.avatar}>
          {item.picture ? (
            <Image source={{ uri: fileUrl(item.picture) }} style={styles.avatarImg} contentFit="cover" />
          ) : (
            <Feather name="user" size={20} color={colors.muted} />
          )}
        </View>
        <Text style={styles.name} numberOfLines={1}>{item.name}</Text>
        <View style={[styles.check, on && styles.checkOn]}>
          {on ? <Feather name="check" size={14} color={colors.onBrandPrimary} /> : null}
        </View>
      </Pressable>
    );
  };

  if (!room) {
    return <View style={[styles.root, { alignItems: "center", justifyContent: "center" }]}><ActivityIndicator color={colors.brandPrimary} /></View>;
  }

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.backBtn} onPress={() => goBack()} hitSlop={8} testID="manage-back">
          <Feather name="chevron-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("manage_group")}</Text>
      </View>

      <FlatList
        data={contacts}
        keyExtractor={(c) => c.user_id}
        renderItem={renderContact}
        ListHeaderComponent={
          <View>
            <View style={styles.photoWrap}>
              <Pressable style={styles.groupPhotoPick} onPress={pickPhoto} testID="manage-photo-pick">
                {uploadingPhoto ? (
                  <ActivityIndicator color={colors.brandPrimary} />
                ) : photoValue ? (
                  <Image source={{ uri: fileUrl(photoValue) }} style={styles.avatarImg} contentFit="cover" />
                ) : (
                  <Feather name="camera" size={26} color={colors.brandSecondary} />
                )}
                <View style={styles.photoEditBadge}>
                  <Feather name="edit-2" size={12} color={colors.onBrandPrimary} />
                </View>
              </Pressable>
            </View>
            <Text style={styles.label}>{t("group_name")}</Text>
            <TextInput
              testID="manage-name-input"
              style={styles.input}
              value={nameValue}
              onChangeText={(v) => setEdits((s) => ({ ...s, name: v }))}
              placeholder={t("group_name_placeholder")}
              placeholderTextColor={colors.muted}
            />
            <Text style={styles.label}>{t("select_members")} · {selected.size}</Text>
          </View>
        }
      />

      <View style={[styles.footer, { paddingBottom: insets.bottom + 16 }]}>
        <Pressable
          testID="manage-save"
          style={[styles.saveBtn, { opacity: !nameValue.trim() || saveMut.isPending ? 0.6 : 1 }]}
          disabled={!nameValue.trim() || saveMut.isPending}
          onPress={() => saveMut.mutate()}
        >
          {saveMut.isPending ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.saveText}>{t("save_changes")}</Text>}
        </Pressable>
      </View>
    </View>
  );
}
