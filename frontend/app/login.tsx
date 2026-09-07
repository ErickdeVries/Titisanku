import { View, Text, ImageBackground } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles } from "@/src/theme";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { GradientButton } from "@/src/components/GradientButton";

const HERO =
  "https://images.unsplash.com/photo-1706200637521-b446bd05df0d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzJ8MHwxfHNlYXJjaHwxfHxmYW1pbHklMjBjb25uZWN0aW9uJTIwZ2VuZWFsb2d5fGVufDB8fHx8MTc4ODYxODU3OHww&ixlib=rb-4.1.0&q=85";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  hero: { width: "100%", height: "58%" },
  scrim: { flex: 1, justifyContent: "flex-end" },
  logoBadge: {
    position: "absolute",
    top: 60,
    left: 24,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "rgba(255,255,255,0.9)",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
  },
  logoText: { fontFamily: fonts.bold, fontSize: 14, color: c.brandPrimary, letterSpacing: 1 },
  body: { paddingHorizontal: 24, paddingTop: 28, flex: 1 },
  title: { fontFamily: fonts.bold, fontSize: 28, color: c.onSurface, lineHeight: 34 },
  subtitle: { fontFamily: fonts.regular, fontSize: 15, color: c.muted, marginTop: 12, lineHeight: 22 },
}));

export default function Login() {
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const { login, signingIn } = useAuth();
  const { t } = useI18n();

  return (
    <View style={styles.root}>
      <ImageBackground source={{ uri: HERO }} style={styles.hero}>
        <LinearGradient colors={["transparent", "rgba(255,255,255,0.4)", "#FFFFFF"]} style={styles.scrim} />
        <View style={styles.logoBadge}>
          <Feather name="git-merge" size={16} color="#F59E0B" />
          <Text style={styles.logoText}>TITISANKU</Text>
        </View>
      </ImageBackground>
      <View style={styles.body}>
        <Text style={styles.title}>{t("login_title")}</Text>
        <Text style={styles.subtitle}>{t("login_subtitle")}</Text>
        <View style={{ flex: 1 }} />
        <GradientButton
          testID="google-login-button"
          title={signingIn ? t("logging_in") : t("login_google")}
          icon="log-in"
          loading={signingIn}
          onPress={login}
          style={{ marginBottom: insets.bottom + 24 }}
        />
      </View>
    </View>
  );
}
