import { useState } from "react";
import { View, Text, TextInput, Pressable, ScrollView } from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { fonts, makeStyles } from "@/src/theme";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { GradientButton } from "@/src/components/GradientButton";

const EMBLEM = require("../assets/images/titisanku-emblem.png");

// Tombol akun demo hanya muncul bila diaktifkan lewat env (dipakai untuk review Play).
const DEMO_ENABLED = process.env.EXPO_PUBLIC_ENABLE_DEMO_LOGIN === "true";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface, alignItems: "center" },
  scroll: { flexGrow: 1, width: "100%", alignItems: "center", justifyContent: "center" },
  inner: { width: "100%", maxWidth: 460, paddingHorizontal: 28, paddingBottom: 32, alignItems: "center" },
  emblem: { width: 112, height: 112, marginBottom: 18 },
  title: {
    fontFamily: fonts.bold,
    fontSize: 24,
    color: c.onSurface,
    textAlign: "center",
    letterSpacing: -0.4,
  },
  subtitle: {
    fontFamily: fonts.regular,
    fontSize: 14,
    lineHeight: 21,
    color: c.muted,
    textAlign: "center",
    marginTop: 8,
    marginBottom: 22,
  },
  form: { width: "100%", gap: 12 },
  input: {
    height: 52,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: c.border,
    backgroundColor: c.surfaceSecondary,
    paddingHorizontal: 16,
    fontFamily: fonts.regular,
    fontSize: 15,
    color: c.onSurface,
  },
  error: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: "#B3261E",
    textAlign: "center",
    marginTop: 4,
  },
  link: {
    fontFamily: fonts.semibold,
    fontSize: 14,
    color: c.brandSecondary,
    textAlign: "center",
    paddingVertical: 10,
  },
  dividerRow: { flexDirection: "row", alignItems: "center", gap: 12, marginVertical: 16, width: "100%" },
  dividerLine: { flex: 1, height: 1, backgroundColor: c.border },
  dividerText: { fontFamily: fonts.regular, fontSize: 12, color: c.muted },
  legal: {
    fontFamily: fonts.regular,
    fontSize: 12,
    color: c.muted,
    marginTop: 22,
    textAlign: "center",
  },
}));

export default function Login() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { t } = useI18n();
  const { login, loginWithPassword, register, loginDemo, signingIn, authError } = useAuth();

  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  const canSubmit = username.trim().length >= 3 && password.length >= 8;

  const submit = async () => {
    if (!canSubmit) return;
    if (mode === "login") {
      await loginWithPassword(username, password);
    } else {
      await register(username, password, name || username);
    }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.inner}>
          <Image source={EMBLEM} style={styles.emblem} contentFit="contain" />
          <Text style={styles.title}>{t("login_title")}</Text>
          <Text style={styles.subtitle}>{t("login_subtitle")}</Text>

          <View style={styles.form}>
            <TextInput
              style={styles.input}
              placeholder={t("login_username")}
              placeholderTextColor="#9A9488"
              value={username}
              onChangeText={setUsername}
              autoCapitalize="none"
              autoCorrect={false}
              testID="input-username"
            />
            <TextInput
              style={styles.input}
              placeholder={t("login_password")}
              placeholderTextColor="#9A9488"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              testID="input-password"
            />
            {mode === "register" && (
              <TextInput
                style={styles.input}
                placeholder={t("login_name")}
                placeholderTextColor="#9A9488"
                value={name}
                onChangeText={setName}
                testID="input-name"
              />
            )}
            {authError && <Text style={styles.error}>{authError}</Text>}
            <GradientButton
              title={mode === "login" ? t("login_submit") : t("login_register_submit")}
              icon="log-in"
              loading={signingIn}
              disabled={!canSubmit}
              onPress={submit}
              testID="submit-credentials"
            />
            <Pressable onPress={() => setMode(mode === "login" ? "register" : "login")}>
              <Text style={styles.link}>
                {mode === "login" ? t("login_to_register") : t("login_to_login")}
              </Text>
            </Pressable>
          </View>

          {DEMO_ENABLED && (
            <GradientButton
              title={t("login_demo")}
              icon="user"
              variant="secondary"
              loading={signingIn}
              onPress={loginDemo}
              style={{ marginTop: 14 }}
              testID="demo-login"
            />
          )}

          <View style={styles.dividerRow}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>{t("login_or")}</Text>
            <View style={styles.dividerLine} />
          </View>

          <GradientButton
            title={t("login_google")}
            icon="log-in"
            variant="secondary"
            loading={signingIn}
            onPress={login}
            testID="google-login"
          />
          <Text style={styles.legal}>© Titisanku · Warisan keluarga Anda</Text>
        </View>
      </ScrollView>
    </View>
  );
}
