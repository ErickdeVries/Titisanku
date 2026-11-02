import { useState } from "react";
import { Platform, View, Text, TextInput, Pressable, ScrollView } from "react-native";
import { Image } from "expo-image";
import * as AppleAuthentication from "expo-apple-authentication";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { fonts, makeStyles } from "@/src/theme";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { GradientButton } from "@/src/components/GradientButton";

const EMBLEM = require("../assets/images/titisanku-emblem.png");

// Tombol akun demo hanya muncul bila diaktifkan lewat env (dipakai untuk review Play).
const DEMO_ENABLED = process.env.EXPO_PUBLIC_ENABLE_DEMO_LOGIN === "true";

/**
 * Halaman masuk.
 *
 * Bagian branding (emblem, eyebrow, nama aplikasi, garis pemisah, subjudul)
 * memakai skala desain acuan: emblem 168pt, judul Playfair Display.
 * Bagian cara masuk sengaja dibuat kompak dan ditempel ke bawah layar agar
 * branding tetap dominan seperti desain acuan.
 */
const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  scrollOuter: { flex: 1, width: "100%" },
  scroll: { flexGrow: 1, width: "100%", justifyContent: "space-between" },

  // Branding
  brand: {
    flexGrow: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 28,
    paddingTop: 16,
  },
  emblem: { width: 168, height: 168 },
  eyebrow: {
    fontFamily: fonts.semibold,
    fontSize: 12,
    letterSpacing: 2.6,
    color: c.brandSecondary,
    textAlign: "center",
    marginTop: 22,
  },
  brandName: {
    fontFamily: fonts.display,
    fontSize: 46,
    lineHeight: 58,
    color: c.brandSecondary,
    textAlign: "center",
    marginTop: 4,
  },
  rule: { flexDirection: "row", alignItems: "center", gap: 12, marginTop: 4 },
  ruleLine: { width: 62, height: 1, backgroundColor: c.borderStrong },
  ruleDot: { width: 7, height: 7, backgroundColor: c.brand, transform: [{ rotate: "45deg" }] },
  subtitle: {
    fontFamily: fonts.regular,
    fontSize: 15,
    lineHeight: 24,
    color: c.muted,
    textAlign: "center",
    marginTop: 16,
    maxWidth: 330,
  },

  // Cara masuk (kompak, di bawah)
  login: { width: "100%", maxWidth: 460, alignSelf: "center", paddingHorizontal: 28 },
  form: { width: "100%", gap: 10, marginBottom: 12 },
  input: {
    height: 46,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: c.border,
    backgroundColor: c.surfaceSecondary,
    paddingHorizontal: 14,
    fontFamily: fonts.regular,
    fontSize: 14,
    color: c.onSurface,
  },
  error: {
    fontFamily: fonts.regular,
    fontSize: 13,
    color: "#B3261E",
    textAlign: "center",
    marginBottom: 10,
  },
  link: {
    fontFamily: fonts.semibold,
    fontSize: 13,
    color: c.brandSecondary,
    textAlign: "center",
    paddingVertical: 8,
  },
  linkSmall: {
    fontFamily: fonts.medium,
    fontSize: 13,
    color: c.brandSecondary,
    textAlign: "center",
    paddingVertical: 9,
  },
  legal: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: c.muted,
    marginTop: 2,
    textAlign: "center",
  },
  appleWrap: { marginTop: 10, alignItems: "center" },
  // Ukuran minimum 44pt sesuai HIG; lebar mengikuti tombol Google.
  appleButton: { width: "100%", height: 44 },
}));

export default function Login() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { t } = useI18n();
  const { login, loginWithApple, appleAvailable, loginWithPassword, register, loginDemo, signingIn, authError } = useAuth();

  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [showCredentials, setShowCredentials] = useState(false);

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
      <ScrollView
        style={styles.scrollOuter}
        contentContainerStyle={[styles.scroll, { paddingBottom: Math.max(insets.bottom, 10) + 8 }]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.brand}>
          <Image source={EMBLEM} style={styles.emblem} contentFit="contain" />
          <Text style={styles.eyebrow}>{t("login_eyebrow")}</Text>
          <Text style={styles.brandName}>{t("login_brand")}</Text>
          <View style={styles.rule}>
            <View style={styles.ruleLine} />
            <View style={styles.ruleDot} />
            <View style={styles.ruleLine} />
          </View>
          <Text style={styles.subtitle}>{t("login_subtitle")}</Text>
        </View>

        <View style={styles.login}>
          {showCredentials && (
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
              <GradientButton
                title={mode === "login" ? t("login_submit") : t("login_register_submit")}
                icon="log-in"
                size="compact"
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
          )}

          {authError && <Text style={styles.error}>{authError}</Text>}

          <GradientButton
            title={t("login_google")}
            icon="log-in"
            size="compact"
            loading={signingIn}
            onPress={login}
            testID="google-login"
          />

          {/* Guideline 4.8 App Store: Sign in with Apple wajib ditawarkan
              setara dengan login pihak ketiga lain (Google). Tombol memakai
              komponen resmi Apple agar lolos review desain. */}
          {appleAvailable && (
            <View style={styles.appleWrap}>
              <AppleAuthentication.AppleAuthenticationButton
                buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
                buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.BLACK}
                cornerRadius={12}
                style={styles.appleButton}
                onPress={loginWithApple}
              />
            </View>
          )}

          <Pressable
            onPress={() => setShowCredentials((v) => !v)}
            testID="toggle-credentials"
            hitSlop={6}
          >
            <Text style={styles.linkSmall}>
              {showCredentials ? t("login_hide_credentials") : t("login_show_credentials")}
            </Text>
          </Pressable>

          {DEMO_ENABLED && (
            <Pressable onPress={loginDemo} disabled={signingIn} testID="demo-login" hitSlop={6}>
              <Text style={styles.linkSmall}>{t("login_demo")}</Text>
            </Pressable>
          )}

          <Text style={styles.legal}>© Titisanku · Warisan keluarga Anda</Text>
        </View>
      </ScrollView>
    </View>
  );
}
