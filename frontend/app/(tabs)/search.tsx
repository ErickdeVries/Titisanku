import { useMemo, useState } from "react";
import { View, Text, TextInput, FlatList, Pressable } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { getTree, fileUrl, Person } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { nodeColor } from "@/src/components/PersonNode";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 20, paddingBottom: 12, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: fonts.bold, fontSize: 20, color: c.onSurface, marginBottom: 14 },
  searchBar: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: c.surfaceTertiary, borderRadius: 999, paddingHorizontal: 16, height: 48 },
  input: { flex: 1, fontFamily: fonts.regular, fontSize: 15, color: c.onSurface },
  row: { flexDirection: "row", alignItems: "center", gap: 14, paddingVertical: 12, paddingHorizontal: 20, borderBottomWidth: 1, borderBottomColor: c.divider },
  avatar: { width: 48, height: 48, borderRadius: 999, alignItems: "center", justifyContent: "center", overflow: "hidden", borderWidth: 2 },
  avatarImg: { width: "100%", height: "100%" },
  name: { fontFamily: fonts.semibold, fontSize: 15, color: c.onSurface },
  sub: { fontFamily: fonts.regular, fontSize: 13, color: c.muted, marginTop: 2 },
  empty: { alignItems: "center", padding: 40, gap: 12 },
  emptyImg: { width: 140, height: 140, borderRadius: 16 },
  emptyText: { fontFamily: fonts.medium, fontSize: 15, color: c.muted, textAlign: "center" },
}));

const EMPTY =
  "https://images.unsplash.com/photo-1695131020187-d3dcdab5016b?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NDh8MHwxfHNlYXJjaHwxfHxlbXB0eSUyMGxpc3QlMjBkb2N1bWVudCUyMGFic3RyYWN0fGVufDB8fHx8MTc4ODYxODU3OHww&ixlib=rb-4.1.0&q=85";

export default function SearchScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [q, setQ] = useState("");

  const { data } = useQuery({ queryKey: ["tree"], queryFn: getTree });
  const people = data?.people ?? [];

  const filtered = useMemo(() => {
    if (!q.trim()) return people;
    return people.filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));
  }, [q, people]);

  const renderRow = ({ item }: { item: Person }) => {
    const photo = fileUrl(item.photo_url);
    const color = nodeColor(item, colors);
    return (
      <Pressable style={styles.row} onPress={() => router.push(`/person/${item.id}`)} testID={`search-row-${item.id}`}>
        <View style={[styles.avatar, { borderColor: color }]}>
          {photo ? <Image source={{ uri: photo }} style={styles.avatarImg} contentFit="cover" /> : <Feather name="user" size={22} color={color} />}
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.name}>{item.name}</Text>
          <Text style={styles.sub}>{item.job || item.birth_place || (item.gender === "male" ? t("male") : item.gender === "female" ? t("female") : "-")}</Text>
        </View>
        <Feather name="chevron-right" size={20} color={colors.muted} />
      </Pressable>
    );
  };

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Text style={styles.title}>{t("search")}</Text>
        <View style={styles.searchBar}>
          <Feather name="search" size={18} color={colors.muted} />
          <TextInput
            testID="search-input"
            style={styles.input}
            placeholder={t("search_placeholder")}
            placeholderTextColor={colors.muted}
            value={q}
            onChangeText={setQ}
          />
          {q ? (
            <Pressable onPress={() => setQ("")}>
              <Feather name="x" size={18} color={colors.muted} />
            </Pressable>
          ) : null}
        </View>
      </View>
      <FlatList
        data={filtered}
        keyExtractor={(p) => p.id}
        renderItem={renderRow}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Image source={{ uri: EMPTY }} style={styles.emptyImg} contentFit="cover" />
            <Text style={styles.emptyText}>{q ? t("no_results") : t("search_hint")}</Text>
          </View>
        }
      />
    </View>
  );
}
