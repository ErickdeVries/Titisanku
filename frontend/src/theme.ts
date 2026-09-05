// Design tokens for KETURUNANKU. Light theme (white background) per brief.
import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  surface: "#FFFFFF",
  onSurface: "#0F172A",
  surfaceSecondary: "#F8FAFC",
  onSurfaceSecondary: "#334155",
  surfaceTertiary: "#F1F5F9",
  onSurfaceTertiary: "#475569",
  surfaceInverse: "#0F172A",
  onSurfaceInverse: "#FFFFFF",
  muted: "#64748B",

  brand: "#F59E0B",
  onBrand: "#FFFFFF",
  brandPrimary: "#F59E0B",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#3B82F6",
  onBrandSecondary: "#FFFFFF",
  brandTertiary: "#FEF3C7",
  onBrandTertiary: "#B45309",

  success: "#10B981",
  onSuccess: "#FFFFFF",
  warning: "#F59E0B",
  onWarning: "#FFFFFF",
  error: "#EF4444",
  onError: "#FFFFFF",
  info: "#3B82F6",
  onInfo: "#FFFFFF",

  border: "#E2E8F0",
  borderStrong: "#CBD5E1",
  divider: "#F1F5F9",

  // Family-tree specific tokens
  maleNode: "#3B82F6",
  femaleNode: "#EC4899",
  adminNode: "#F59E0B",
  nodeAdoptedLine: "#94A3B8",
  nodeDivorceLine: "#EF4444",
  nodeRelationLine: "#CBD5E1",
};

export type ThemeColors = typeof light;

export const defaultScheme = "light" satisfies ColorScheme;
export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

// Poppins font family names (registered in app/_layout.tsx via expo-font).
export const fonts = {
  regular: "Poppins-Regular",
  medium: "Poppins-Medium",
  semibold: "Poppins-SemiBold",
  bold: "Poppins-Bold",
};

// Gradient used for primary CTA buttons (no border / shadow per brief).
export const brandGradient = ["#F59E0B", "#EA580C"] as const;

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme);
}

setColorScheme?.(themes.dark ? null : defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme = system && themes[system] ? system : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.light };
}

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}
