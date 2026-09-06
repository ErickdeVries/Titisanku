import { useEffect } from "react";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { QueryClientProvider } from "@tanstack/react-query";
import { Stack, useRouter, useSegments } from "expo-router";
import { LogBox } from "react-native";
import { useFonts } from "expo-font";
import * as SplashScreen from "expo-splash-screen";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { AuthProvider, useAuth } from "@/src/auth";
import { TreeProvider, useTree } from "@/src/tree-context";
import { LanguageProvider } from "@/src/i18n";
import { ThemeProvider } from "@/src/theme";
import { storage } from "@/src/utils/storage";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync().catch(() => {});

function RootNav() {
  const { user, loading } = useAuth();
  const { trees, loading: treesLoading } = useTree();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    const inAuth = segments[0] === "login";
    const inInvite = segments[0] === "invite";
    const inWelcome = segments[0] === "welcome";
    const inJoin = segments[0] === "join";
    if (!user && !inAuth && !inInvite) {
      router.replace("/login");
      return;
    }
    if (user && inAuth) {
      router.replace("/(tabs)");
      return;
    }
    // New user with no tree yet → onboarding. Allow welcome/join/invite to stay.
    if (user && !treesLoading && trees.length === 0 && !inWelcome && !inJoin && !inInvite) {
      router.replace("/welcome");
    }
  }, [user, loading, treesLoading, trees.length, segments, router]);

  // Resume a pending invite once the user is authenticated (works on web + native).
  useEffect(() => {
    if (loading || !user) return;
    if (segments[0] === "invite") return;
    storage.getItem<string>("pending_invite", "").then((tok) => {
      if (tok) {
        storage.removeItem("pending_invite");
        router.replace(`/invite/${tok}`);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, loading]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#D4AF37" />
      </View>
    );
  }

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="login" />
      <Stack.Screen name="welcome" />
      <Stack.Screen name="join" />
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="person/[id]" options={{ presentation: "modal" }} />
      <Stack.Screen name="add-relative" options={{ presentation: "modal" }} />
      <Stack.Screen name="trees" options={{ presentation: "modal" }} />
      <Stack.Screen name="subscription" />
      <Stack.Screen name="payment-history" />
      <Stack.Screen name="themes" />
      <Stack.Screen name="members" />
      <Stack.Screen name="claim-branch" />
      <Stack.Screen name="chat/[roomId]" />
      <Stack.Screen name="chat/new" />
      <Stack.Screen name="chat/manage/[roomId]" />
      <Stack.Screen name="privacy" />
      <Stack.Screen name="feedback" />
      <Stack.Screen name="explorer/[id]" />
      <Stack.Screen name="invite/[token]" />
    </Stack>
  );
}

export default function RootLayout() {
  const [fontsLoaded] = useFonts({
    "Poppins-Regular": require("../assets/fonts/Poppins-Regular.ttf"),
    "Poppins-Medium": require("../assets/fonts/Poppins-Medium.ttf"),
    "Poppins-SemiBold": require("../assets/fonts/Poppins-SemiBold.ttf"),
    "Poppins-Bold": require("../assets/fonts/Poppins-Bold.ttf"),
    "PlayfairDisplay-Bold": require("../assets/fonts/PlayfairDisplay-Bold.ttf"),
    "PlayfairDisplay-SemiBold": require("../assets/fonts/PlayfairDisplay-SemiBold.ttf"),
    Feather: require("../node_modules/@react-native-vector-icons/feather/fonts/Feather.ttf"),
  });

  useEffect(() => {
    if (fontsLoaded) SplashScreen.hideAsync().catch(() => {});
  }, [fontsLoaded]);

  if (!fontsLoaded) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#D4AF37" />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <KeyboardProvider>
        <SafeAreaProvider>
          <ThemeProvider>
            <ErrorBoundary>
              <QueryClientProvider client={queryClient}>
                <AuthProvider>
                  <TreeProvider>
                    <LanguageProvider>
                      <RootNav />
                    </LanguageProvider>
                  </TreeProvider>
                </AuthProvider>
              </QueryClientProvider>
            </ErrorBoundary>
          </ThemeProvider>
        </SafeAreaProvider>
      </KeyboardProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#FFFBF0" },
});
