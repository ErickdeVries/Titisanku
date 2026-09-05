// Design tokens for KETURUNANKU. Light theme (white background) per brief.
import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  surface: "#FFFBF0",
  onSurface: "#1F2A44",
  surfaceSecondary: "#FFFFFF",
  onSurfaceSecondary: "#3A3F52",
  surfaceTertiary: "#F5EEDC",
  onSurfaceTertiary: "#6B5E3A",
  surfaceInverse: "#1E3A8A",
  onSurfaceInverse: "#FFFFFF",
  muted: "#8A8577",

  brand: "#D4AF37",
  onBrand: "#3A2E00",
  brandPrimary: "#D4AF37",
  onBrandPrimary: "#3A2E00",
  brandSecondary: "#1E3A8A",
  onBrandSecondary: "#FFFFFF",
  brandTertiary: "#FBF3D5",
  onBrandTertiary: "#8A6D1B",

  success: "#2E9E6B",
  onSuccess: "#FFFFFF",
  warning: "#D4AF37",
  onWarning: "#3A2E00",
  error: "#DC2626",
  onError: "#FFFFFF",
  info: "#1E3A8A",
  onInfo: "#FFFFFF",

  border: "#EAE0C8",
  borderStrong: "#D8CBA6",
  divider: "#F0E8D4",

  // Family-tree specific tokens
  maleNode: "#1E3A8A",
  femaleNode: "#B84A7A",
  adminNode: "#D4AF37",
  nodeAdoptedLine: "#B0A583",
  nodeDivorceLine: "#DC2626",
  nodeRelationLine: "#D8CBA6",
};

export type ThemeColors = typeof light;

export const defaultScheme = "light" satisfies ColorScheme;
export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

// Font family names (registered in app/_layout.tsx via expo-font).
export const fonts = {
  regular: "Poppins-Regular",
  medium: "Poppins-Medium",
  semibold: "Poppins-SemiBold",
  bold: "Poppins-Bold",
  // Playfair Display — used for headings / display titles ("Modern Heritage").
  display: "PlayfairDisplay-Bold",
  displaySemibold: "PlayfairDisplay-SemiBold",
};

// Gradient used for primary CTA buttons — Gold -> Royal Blue ("Modern Heritage").
export const brandGradient = ["#D4AF37", "#1E3A8A"] as const;

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
