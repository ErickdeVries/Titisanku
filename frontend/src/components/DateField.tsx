import { useState } from "react";
import { TextInput, StyleSheet } from "react-native";
import { fonts, useTheme } from "@/src/theme";

// Store dates internally as ISO (YYYY-MM-DD); display/edit as DD/MM/YYYY.
function digitsToDisplay(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 8);
  let out = d.slice(0, 2);
  if (d.length > 2) out += "/" + d.slice(2, 4);
  if (d.length > 4) out += "/" + d.slice(4, 8);
  return out;
}

function displayToISO(s: string): string | null {
  const m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!m) return null;
  const dd = +m[1], mm = +m[2];
  if (mm < 1 || mm > 12 || dd < 1 || dd > 31) return null;
  return `${m[3]}-${m[2]}-${m[1]}`;
}

export function isoToDisplay(iso?: string | null): string {
  if (!iso) return "";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  return `${m[3]}/${m[2]}/${m[1]}`;
}

export function DateField({
  value,
  onChange,
  testID,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
  testID?: string;
}) {
  const { colors } = useTheme();
  const [text, setText] = useState(() => isoToDisplay(value));

  const handle = (t: string) => {
    const disp = digitsToDisplay(t);
    setText(disp);
    if (disp === "") onChange(null);
    else onChange(displayToISO(disp));
  };

  return (
    <TextInput
      testID={testID}
      style={[styles.input, { backgroundColor: colors.surfaceTertiary, color: colors.onSurface, borderColor: colors.border }]}
      placeholder="DD/MM/YYYY"
      placeholderTextColor={colors.muted}
      value={text}
      onChangeText={handle}
      keyboardType="number-pad"
      maxLength={10}
    />
  );
}

const styles = StyleSheet.create({
  input: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontFamily: fonts.regular, fontSize: 15 },
});
