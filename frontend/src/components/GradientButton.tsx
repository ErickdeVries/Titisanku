import React from "react";
import { ActivityIndicator, Pressable, StyleProp, Text, View, ViewStyle } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";

type Props = {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  icon?: string;
  variant?: "primary" | "secondary";
  /** "compact" = tinggi 44px + teks lebih kecil, untuk area yang lebih ringkas. */
  size?: "default" | "compact";
  style?: StyleProp<ViewStyle>;
  testID?: string;
};

const useStyles = makeStyles((c) => ({
  wrap: { borderRadius: 999, overflow: "hidden" },
  grad: {
    height: 54,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingHorizontal: 24,
  },
  secondary: {
    height: 54,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingHorizontal: 24,
    backgroundColor: c.surfaceTertiary,
    borderRadius: 999,
  },
  text: { fontFamily: fonts.semibold, fontSize: 16, color: "#FFFFFF" },
  textSecondary: { fontFamily: fonts.semibold, fontSize: 16, color: c.onSurface },
  disabled: { opacity: 0.5 },
  compact: { height: 44, paddingHorizontal: 18, gap: 6 },
  textCompact: { fontFamily: fonts.semibold, fontSize: 15, color: "#FFFFFF" },
  textCompactSecondary: { fontFamily: fonts.semibold, fontSize: 15, color: c.onSurface },
}));

export function GradientButton({ title, onPress, loading, disabled, icon, variant = "primary", size = "default", style, testID }: Props) {
  const styles = useStyles();
  const { colors, gradient } = useTheme();
  const isDisabled = disabled || loading;
  const compact = size === "compact";
  const iconSize = compact ? 16 : 18;

  if (variant === "secondary") {
    return (
      <Pressable
        testID={testID}
        onPress={onPress}
        disabled={isDisabled}
        style={[styles.secondary, compact && styles.compact, isDisabled && styles.disabled, style]}
      >
        {loading ? (
          <ActivityIndicator color={colors.onSurface} />
        ) : (
          <>
            {icon ? <Feather name={icon as any} size={iconSize} color={colors.onSurface} /> : null}
            <Text style={[compact ? styles.textCompactSecondary : styles.textSecondary, { flexShrink: 1 }]} numberOfLines={1} adjustsFontSizeToFit>{title}</Text>
          </>
        )}
      </Pressable>
    );
  }

  return (
    <Pressable testID={testID} onPress={onPress} disabled={isDisabled} style={[styles.wrap, isDisabled && styles.disabled, style]}>
      <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={[styles.grad, compact && styles.compact]}>
        {loading ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <>
            {icon ? <Feather name={icon as any} size={iconSize} color="#FFFFFF" /> : null}
            <Text style={[compact ? styles.textCompact : styles.text, { flexShrink: 1 }]} numberOfLines={1} adjustsFontSizeToFit>{title}</Text>
          </>
        )}
      </LinearGradient>
    </Pressable>
  );
}
