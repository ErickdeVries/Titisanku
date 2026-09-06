import React from "react";
import { Pressable, Text, View } from "react-native";
import { Image } from "expo-image";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { fileUrl, Person } from "@/src/api";
import { NODE_D } from "@/src/tree-layout";

type Props = {
  person: Person;
  onPress?: () => void;
  selected?: boolean;
  size?: number;
  ringColor?: string;
};

export function nodeColor(person: Person, colors: any): string {
  if (person.is_root) return colors.adminNode;
  if (person.gender === "female") return colors.femaleNode;
  if (person.gender === "male") return colors.maleNode;
  return colors.muted;
}

const useStyles = makeStyles((c) => ({
  wrap: { alignItems: "center", width: 96 },
  ring: {
    borderRadius: 999,
    padding: 3,
    backgroundColor: c.surface,
    shadowColor: "#0F172A",
    shadowOpacity: 0.18,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 5,
  },
  avatar: { borderRadius: 999, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  img: { width: "100%", height: "100%" },
  selectedRing: { borderWidth: 3, borderColor: c.brandPrimary },
  name: { fontFamily: fonts.medium, fontSize: 12, color: c.onSurface, marginTop: 6, textAlign: "center" },
  deceased: {
    position: "absolute",
    top: -2,
    right: -2,
    backgroundColor: c.surfaceInverse,
    borderRadius: 999,
    width: 20,
    height: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  noteDot: {
    position: "absolute",
    bottom: 0,
    right: 0,
    backgroundColor: c.warning,
    borderRadius: 999,
    width: 16,
    height: 16,
    borderWidth: 2,
    borderColor: c.surface,
  },
  genderDot: {
    position: "absolute",
    bottom: 0,
    left: 0,
    borderRadius: 999,
    width: 14,
    height: 14,
    borderWidth: 2,
    borderColor: c.surface,
  },
}));

export function PersonNode({ person, onPress, selected, size = NODE_D, ringColor }: Props) {
  const styles = useStyles();
  const { colors } = useTheme();
  const genderColor = nodeColor(person, colors);
  const color = ringColor ?? genderColor;
  const photo = fileUrl(person.photo_url);

  return (
    <Pressable testID={`node-${person.id}`} onPress={onPress} style={styles.wrap}>
      <View style={[styles.ring, { borderWidth: 3, borderColor: color }, selected && styles.selectedRing]}>
        <View style={[styles.avatar, { width: size, height: size }]}>
          {photo ? (
            <Image source={{ uri: photo }} style={styles.img} contentFit="cover" transition={200} />
          ) : (
            <Feather name="user" size={size * 0.5} color={color} />
          )}
        </View>
        {/* small gender dot so gender is still readable when ring shows lineage */}
        {ringColor && person.gender ? (
          <View style={[styles.genderDot, { backgroundColor: genderColor }]} />
        ) : null}
        {person.death_date ? (
          <View style={styles.deceased}>
            <Feather name="star" size={11} color={colors.onSurfaceInverse} />
          </View>
        ) : null}
        {(person.note_count && person.note_count > 0) || (person.notes && person.notes.trim()) ? (
          <View style={styles.noteDot} testID={`note-dot-${person.id}`} />
        ) : null}
      </View>
      <Text style={styles.name} numberOfLines={2}>
        {person.name}
      </Text>
    </Pressable>
  );
}
