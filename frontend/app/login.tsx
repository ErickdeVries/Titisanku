import { View, Text } from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { fonts, makeStyles } from "@/src/theme";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { GradientButton } from "@/src/components/GradientButton";

const EMBLEM = require("../assets/images/titisanku-emblem.png");

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface, alignItems: "center" },
  frameOuter: { position: "absolute", top: 16, left: 16, right: 16, bottom: 16, borderWidth: 1.5, borderColor: c.brandPrimary, borderRadius: 10 },
  frameInner: { position: "absolute", top: 22, left: 22, right: 22, bottom: 22, borderWidth: 0.75, borderColor: c.brandPrimary, borderRadius: 6, opacity: 0.6 },
  content: { flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 40, gap: 6 },
  emblem: { width: 210, height: 210 },
  kicker: { fontFamily: fonts.medium, fontSize: 12, color: c.brandPrimary, letterSpacing: 4, marginTop: 4 },
  brand: { fontFamily: fonts.display, fontSize: 46, color: c.brandSecondary, letterSpacing: 1, marginTop: 2 },
  divider: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 10, marginBottom: 6 },
  dline: { width: 46, height: 1, backgroundColor: c.brandPrimary, opacity: 0.7 },
  diamond: { width: 8, height: 8, backgroundColor: c.brandPrimary, transform: [{ rotate: "45deg" }] },
  subtitle: { fontFamily: fonts.regular, fontSize: 14.5, color: c.muted, textAlign: "center", lineHeight: 22, marginTop: 4 },
  footer: { width: "100%", paddingHorizontal: 40 },
  legal: { fontFamily: fonts.regular, fontSize: 11, color: c.muted, textAlign: "center", marginTop: 14, opacity: 0.8 },
}));

export default function Login() {
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const { login, signingIn } = useAuth();
  const { t } = useI18n();

  return (
    <View style={styles.root}>
      <View style={styles.frameOuter} pointerEvents="none" />
      <View style={styles.frameInner} pointerEvents="none" />

      <View style={[styles.content, { paddingTop: insets.top }]}>
        <Image source={EMBLEM} style={styles.emblem} contentFit="contain" />
        <Text style={styles.kicker}>SILSILAH KELUARGA</Text>
        <Text style={styles.brand}>Titisanku</Text>
        <View style={styles.divider}>
          <View style={styles.dline} />
          <View style={styles.diamond} />
          <View style={styles.dline} />
        </View>
        <Text style={styles.subtitle}>{t("login_subtitle")}</Text>
      </View>

      <View style={[styles.footer, { paddingBottom: insets.bottom + 30 }]}>
        <GradientButton
          testID="google-login-button"
          title={signingIn ? t("logging_in") : t("login_google")}
          icon="log-in"
          loading={signingIn}
          onPress={login}
        />
        <Text style={styles.legal}>© Titisanku · Warisan keluarga Anda</Text>
      </View>
    </View>
  );
}

