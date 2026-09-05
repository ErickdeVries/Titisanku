import { View, Text, Pressable, StyleSheet } from "react-native";
import { Image } from "expo-image";
import { User, Crown, Info } from "lucide-react-native";
import { fonts, useTheme } from "@/src/theme";
import { fileUrl, Person } from "@/src/api";
import { nodeColor } from "@/src/components/PersonNode";

function birthYear(p: Person): string | null {
  if (!p.birth_date) return null;
  const y = new Date(p.birth_date).getFullYear();
  return isNaN(y) ? null : String(y);
}

export function BigPersonCard({
  person,
  scale = 1,
  highlight,
  label,
  onPress,
  onInfo,
  testID,
}: {
  person: Person;
  scale?: number;
  highlight?: boolean;
  label?: string | null;
  onPress?: () => void;
  onInfo?: () => void;
  testID?: string;
}) {
  const { colors } = useTheme();
  const color = nodeColor(person, colors);
  const photo = fileUrl(person.photo_url);
  const avatarSize = 78 * scale;
  const cardW = 118 * scale;
  const yr = birthYear(person);

  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={[
        styles.card,
        {
          width: cardW,
          paddingVertical: 12 * scale,
          backgroundColor: highlight ? colors.brandTertiary : colors.surfaceSecondary,
          borderColor: highlight ? colors.brandPrimary : colors.border,
          borderWidth: highlight ? 2 : 1,
        },
      ]}
    >
      {label ? (
        <View style={[styles.badge, { backgroundColor: colors.brandSecondary }]}>
          <Text style={[styles.badgeText, { fontSize: 9 * scale }]}>{label}</Text>
        </View>
      ) : null}
      <View
        style={[
          styles.avatar,
          { width: avatarSize, height: avatarSize, borderRadius: avatarSize / 2, borderColor: color, backgroundColor: colors.surfaceTertiary },
        ]}
      >
        {photo ? (
          <Image source={{ uri: photo }} style={{ width: "100%", height: "100%" }} contentFit="cover" />
        ) : person.is_root ? (
          <Crown size={avatarSize * 0.45} color={color} />
        ) : (
          <User size={avatarSize * 0.45} color={color} />
        )}
        {person.note_count ? <View style={[styles.noteDot, { backgroundColor: colors.warning }]} /> : null}
      </View>
      <Text style={[styles.name, { fontSize: 14 * scale, color: colors.onSurface }]} numberOfLines={2}>
        {person.name}
      </Text>
      {yr ? <Text style={[styles.year, { fontSize: 11 * scale, color: colors.muted }]}>{yr}{person.death_date ? ` †` : ""}</Text> : null}
      {onInfo ? (
        <Pressable onPress={onInfo} hitSlop={10} style={styles.info} testID={testID ? `${testID}-info` : undefined}>
          <Info size={16 * scale} color={colors.brandSecondary} />
        </Pressable>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { alignItems: "center", borderRadius: 18, paddingHorizontal: 8, gap: 6 },
  badge: { position: "absolute", top: -8, alignSelf: "center", paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, zIndex: 2 },
  badgeText: { fontFamily: fonts.bold, color: "#FFFFFF", letterSpacing: 0.5 },
  avatar: { borderWidth: 3, overflow: "hidden", alignItems: "center", justifyContent: "center" },
  noteDot: { position: "absolute", top: 2, right: 2, width: 12, height: 12, borderRadius: 999, borderWidth: 2, borderColor: "#FFFFFF" },
  name: { fontFamily: fonts.semibold, textAlign: "center" },
  year: { fontFamily: fonts.regular },
  info: { position: "absolute", top: 6, right: 6 },
});
