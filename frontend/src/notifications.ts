import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { Person } from "@/src/api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

export async function ensureNotificationPermission(): Promise<boolean> {
  if (Platform.OS === "web") return false;
  const settings = await Notifications.getPermissionsAsync();
  if (settings.granted) return true;
  if (!settings.canAskAgain) return false;
  const req = await Notifications.requestPermissionsAsync();
  return req.granted;
}

// Schedule a local notification 1 day before each living person's birthday (yearly).
export async function scheduleBirthdayReminders(people: Person[]): Promise<number> {
  if (Platform.OS === "web") return 0;
  await Notifications.cancelAllScheduledNotificationsAsync();
  let count = 0;
  for (const p of people) {
    if (!p.birth_date || p.death_date) continue; // living only
    const d = new Date(p.birth_date);
    if (isNaN(d.getTime())) continue;
    // day before birthday
    let month = d.getMonth() + 1; // 1-12
    let day = d.getDate() - 1;
    if (day < 1) {
      month = month - 1 || 12;
      day = new Date(2024, month, 0).getDate(); // last day of prev month
    }
    try {
      await Notifications.scheduleNotificationAsync({
        content: {
          title: "🎂 Pengingat Ulang Tahun",
          body: `Besok ulang tahun ${p.name}. Jangan lupa ucapkan selamat!`,
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.YEARLY,
          month,
          day,
          hour: 9,
          minute: 0,
        },
      });
      count++;
    } catch {}
  }
  return count;
}
