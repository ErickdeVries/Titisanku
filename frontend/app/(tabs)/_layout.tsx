import { Tabs } from "expo-router";
import { Platform } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { Network, MessageCircle, Search, User } from "lucide-react-native";
import { useTheme, fonts } from "@/src/theme";
import { useI18n } from "@/src/i18n";
import { getNotifications } from "@/src/api";

export default function TabsLayout() {
  const { colors } = useTheme();
  const { t } = useI18n();
  const { data: notif } = useQuery({ queryKey: ["notifications"], queryFn: getNotifications, refetchInterval: 8000 });
  const unreadChat = notif?.unread_chat ?? 0;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.divider,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontFamily: fonts.medium, fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: t("tree"),
          tabBarIcon: ({ color, size }) => <Network size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="chat"
        options={{
          title: t("chat"),
          tabBarBadge: unreadChat > 0 ? unreadChat : undefined,
          tabBarIcon: ({ color, size }) => <MessageCircle size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="search"
        options={{
          title: t("search"),
          tabBarIcon: ({ color, size }) => <Search size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: t("profile"),
          tabBarIcon: ({ color, size }) => <User size={size} color={color} />,
        }}
      />
      <Tabs.Screen name="add" options={{ href: null }} />
    </Tabs>
  );
}
