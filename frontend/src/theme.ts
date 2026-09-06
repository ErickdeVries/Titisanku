// Design tokens for KETURUNANKU. "Modern Heritage" light theme + premium themes.
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { StyleSheet } from "react-native";
import { storage } from "@/src/utils/storage";

export type ColorScheme = "light";

const base = {
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

export type ThemeColors = typeof base;

export type PremiumThemeId = "heritage" | "emerald" | "rose" | "midnight" | "terracotta";

type PremiumTheme = {
  id: PremiumThemeId;
  name: string;
  premium: boolean;
  overrides: Partial<ThemeColors>;
  gradient: readonly [string, string];
  swatch: readonly [string, string, string];
};

export const PREMIUM_THEMES: PremiumTheme[] = [
  {
    id: "heritage",
    name: "Modern Heritage",
    premium: false,
    overrides: {},
    gradient: ["#D4AF37", "#1E3A8A"],
    swatch: ["#D4AF37", "#1E3A8A", "#FBF3D5"],
  },
  {
    id: "emerald",
    name: "Zamrud Kerajaan",
    premium: true,
    overrides: {
      brand: "#0F7B5F", onBrand: "#FFFFFF",
      brandPrimary: "#0F7B5F", onBrandPrimary: "#FFFFFF",
      brandSecondary: "#C9A227", onBrandSecondary: "#3A2E00",
      brandTertiary: "#DDF3EC", onBrandTertiary: "#0B5C47",
      warning: "#0F7B5F", onWarning: "#FFFFFF", info: "#0F7B5F",
      maleNode: "#0F7B5F", femaleNode: "#B84A7A", adminNode: "#C9A227",
      nodeRelationLine: "#B9DCCF",
    },
    gradient: ["#0F7B5F", "#C9A227"],
    swatch: ["#0F7B5F", "#C9A227", "#DDF3EC"],
  },
  {
    id: "rose",
    name: "Mawar Vintage",
    premium: true,
    overrides: {
      brand: "#B03A6E", onBrand: "#FFFFFF",
      brandPrimary: "#B03A6E", onBrandPrimary: "#FFFFFF",
      brandSecondary: "#D4AF37", onBrandSecondary: "#3A2E00",
      brandTertiary: "#F8E4EC", onBrandTertiary: "#8A2A55",
      warning: "#B03A6E", onWarning: "#FFFFFF", info: "#B03A6E",
      maleNode: "#3B4A8A", femaleNode: "#B03A6E", adminNode: "#D4AF37",
      nodeRelationLine: "#E7C6D5",
    },
    gradient: ["#D4AF37", "#B03A6E"],
    swatch: ["#B03A6E", "#D4AF37", "#F8E4EC"],
  },
  {
    id: "midnight",
    name: "Tengah Malam",
    premium: true,
    overrides: {
      brand: "#3B4CC0", onBrand: "#FFFFFF",
      brandPrimary: "#3B4CC0", onBrandPrimary: "#FFFFFF",
      brandSecondary: "#7C8AE0", onBrandSecondary: "#0B1440",
      brandTertiary: "#E4E8FB", onBrandTertiary: "#2A379E",
      warning: "#3B4CC0", onWarning: "#FFFFFF", info: "#3B4CC0",
      maleNode: "#3B4CC0", femaleNode: "#8A5AB8", adminNode: "#7C8AE0",
      nodeRelationLine: "#C7CEF3",
    },
    gradient: ["#3B4CC0", "#7C8AE0"],
    swatch: ["#3B4CC0", "#7C8AE0", "#E4E8FB"],
  },
  {
    id: "terracotta",
    name: "Terakota",
    premium: true,
    overrides: {
      brand: "#C4622D", onBrand: "#FFFFFF",
      brandPrimary: "#C4622D", onBrandPrimary: "#FFFFFF",
      brandSecondary: "#8A4B1F", onBrandSecondary: "#FFFFFF",
      brandTertiary: "#F7E6DA", onBrandTertiary: "#9A4A1F",
      warning: "#C4622D", onWarning: "#FFFFFF", info: "#C4622D",
      maleNode: "#4A6B8A", femaleNode: "#C4622D", adminNode: "#8A4B1F",
      nodeRelationLine: "#E9CBB6",
    },
    gradient: ["#E0894A", "#C4622D"],
    swatch: ["#C4622D", "#E0894A", "#F7E6DA"],
  },
];

function paletteFor(id: PremiumThemeId): { colors: ThemeColors; gradient: readonly [string, string] } {
  const t = PREMIUM_THEMES.find((x) => x.id === id) ?? PREMIUM_THEMES[0];
  return { colors: { ...base, ...t.overrides }, gradient: t.gradient };
}

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

// Default gradient (Modern Heritage). Prefer `useTheme().gradient` for premium-aware UI.
export const brandGradient = PREMIUM_THEMES[0].gradient;

const THEME_KEY = "premium_theme";

type ThemeState = {
  colors: ThemeColors;
  gradient: readonly [string, string];
  themeId: PremiumThemeId;
  setThemeId: (id: PremiumThemeId) => void;
};

const fallback = paletteFor("heritage");
const ThemeContext = createContext<ThemeState | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [themeId, setThemeIdState] = useState<PremiumThemeId>("heritage");

  useEffect(() => {
    storage.getItem<PremiumThemeId>(THEME_KEY, "heritage").then((v) => {
      if (v && PREMIUM_THEMES.some((t) => t.id === v)) setThemeIdState(v);
    });
  }, []);

  const setThemeId = (id: PremiumThemeId) => {
    setThemeIdState(id);
    storage.setItem(THEME_KEY, id);
  };

  const { colors, gradient } = useMemo(() => paletteFor(themeId), [themeId]);
  const value = useMemo<ThemeState>(() => ({ colors, gradient, themeId, setThemeId }), [colors, gradient, themeId]);

  return React.createElement(ThemeContext.Provider, { value }, children);
}

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors; gradient: readonly [string, string] } {
  const ctx = useContext(ThemeContext);
  if (ctx) return { scheme: "light", colors: ctx.colors, gradient: ctx.gradient };
  return { scheme: "light", colors: fallback.colors, gradient: fallback.gradient };
}

export function usePremiumTheme(): ThemeState {
  const ctx = useContext(ThemeContext);
  return ctx ?? { ...fallback, themeId: "heritage", setThemeId: () => {} };
}

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}
