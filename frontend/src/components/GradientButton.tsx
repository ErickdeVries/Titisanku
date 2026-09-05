import React from "react";
import { ActivityIndicator, Pressable, StyleProp, Text, View, ViewStyle } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Feather from "@react-native-vector-icons/feather";
import { brandGradient, fonts, makeStyles, useTheme } from "@/src/theme";

type Props = {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  icon?: string;
  variant?: "primary" | "secondary";
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
  text: { fontFamily: fonts.semibold, fontSize: 16, color: c.onBrandPrimary },
  textSecondary: { fontFamily: fonts.semibold, fontSize: 16, color: c.onSurface },
  disabled: { opacity: 0.5 },
}));

export function GradientButton({ title, onPress, loading, disabled, icon, variant = "primary", style, testID }: Props) {
  const styles = useStyles();
  const { colors } = useTheme();
  const isDisabled = disabled || loading;

  if (variant === "secondary") {
    return (
      <Pressable
        testID={testID}
        onPress={onPress}
        disabled={isDisabled}
        style={[styles.secondary, isDisabled && styles.disabled, style]}
      >
        {loading ? (
          <ActivityIndicator color={colors.onSurface} />
        ) : (
          <>
            {icon ? <Feather name={icon as any} size={18} color={colors.onSurface} /> : null}
            <Text style={styles.textSecondary}>{title}</Text>
          </>
        )}
      </Pressable>
    );
  }

  return (
    <Pressable testID={testID} onPress={onPress} disabled={isDisabled} style={[styles.wrap, isDisabled && styles.disabled, style]}>
      <LinearGradient colors={brandGradient} start={{ x: 0, y: 0 }} end={{ x: 0, y: 1 }} style={styles.grad}>
        {loading ? (
          <ActivityIndicator color={colors.onBrandPrimary} />
        ) : (
          <>
            {icon ? <Feather name={icon as any} size={18} color={colors.onBrandPrimary} /> : null}
            <Text style={styles.text}>{title}</Text>
          </>
        )}
      </LinearGradient>
    </Pressable>
  );
}
