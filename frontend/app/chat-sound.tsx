import { useEffect, useState } from "react";
import { View, Text, Pressable, FlatList } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAudioPlayer } from "expo-audio";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { storage } from "@/src/utils/storage";
import {
  CHAT_SOUNDS,
  CHAT_SOUND_STORAGE_KEY,
  ChatSound,
  ChatSoundKey,
  DEFAULT_CHAT_SOUND,
  soundByKey,
} from "@/src/utils/chat-sounds";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  back: { width: 36, height: 36, borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  hint: { fontFamily: fonts.regular, fontSize: 13, color: c.muted, paddingHorizontal: 16, paddingTop: 14, paddingBottom: 4 },
  row: { flexDirection: "row", alignItems: "center", gap: 14, paddingHorizontal: 16, paddingVertical: 16 },
  playBtn: { width: 40, height: 40, borderRadius: 999, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  label: { fontFamily: fonts.semibold, fontSize: 16, color: c.onSurface, flex: 1 },
  radio: { width: 24, height: 24, borderRadius: 999, borderWidth: 2, borderColor: c.borderStrong, alignItems: "center", justifyContent: "center" },
  radioOn: { borderColor: c.brandPrimary },
  radioDot: { width: 12, height: 12, borderRadius: 999, backgroundColor: c.brandPrimary },
  sep: { height: 1, backgroundColor: c.divider, marginLeft: 70 },
}));

export default function ChatSoundScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [selected, setSelected] = useState<ChatSoundKey>(DEFAULT_CHAT_SOUND);
  const player = useAudioPlayer(soundByKey(DEFAULT_CHAT_SOUND).asset ?? undefined);

  useEffect(() => {
    storage.getItem<string>(CHAT_SOUND_STORAGE_KEY, DEFAULT_CHAT_SOUND).then((v) => setSelected((v as ChatSoundKey) || DEFAULT_CHAT_SOUND));
  }, []);

  const preview = (s: ChatSound) => {
    if (!s.asset) return;
    try {
      player.replace(s.asset);
      player.seekTo(0);
      player.play();
    } catch {}
  };

  const choose = (s: ChatSound) => {
    setSelected(s.key);
    storage.setItem(CHAT_SOUND_STORAGE_KEY, s.key);
    preview(s);
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.back} onPress={() => router.back()} testID="sound-back">
          <Feather name="arrow-left" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("chat_sound")}</Text>
      </View>
      <Text style={styles.hint}>{t("chat_sound_hint")}</Text>
      <FlatList
        data={CHAT_SOUNDS}
        keyExtractor={(s) => s.key}
        ItemSeparatorComponent={() => <View style={styles.sep} />}
        renderItem={({ item }) => {
          const on = item.key === selected;
          return (
            <Pressable style={styles.row} onPress={() => choose(item)} testID={`sound-${item.key}`}>
              <Pressable style={styles.playBtn} onPress={() => preview(item)} testID={`sound-play-${item.key}`}>
                <Feather name={item.asset ? "play" : "volume-x"} size={18} color={colors.brandSecondary} />
              </Pressable>
              <Text style={styles.label}>{item.label}</Text>
              <View style={[styles.radio, on && styles.radioOn]}>{on ? <View style={styles.radioDot} /> : null}</View>
            </Pressable>
          );
        }}
      />
    </View>
  );
}
