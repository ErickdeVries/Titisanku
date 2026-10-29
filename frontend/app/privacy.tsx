import { View, Text, Pressable, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { useGoBack } from "@/src/hooks/useGoBack";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Feather from "@react-native-vector-icons/feather";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  backBtn: { width: 36, height: 36, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  h: { fontFamily: fonts.semibold, fontSize: 16, color: c.onSurface, marginTop: 20, marginBottom: 6 },
  p: { fontFamily: fonts.regular, fontSize: 14, color: c.onSurfaceSecondary, lineHeight: 21 },
  updated: { fontFamily: fonts.regular, fontSize: 12, color: c.muted, marginTop: 8 },
}));

const SECTIONS: { h: string; p: string }[] = [
  { h: "1. Data yang Kami Kumpulkan", p: "Kami mengumpulkan nama, alamat email, dan foto profil dari akun Google Anda saat login. Kami juga menyimpan data silsilah yang Anda buat (nama anggota keluarga, tanggal, foto, catatan, relasi) dan pesan obrolan di dalam aplikasi." },
  { h: "2. Bagaimana Data Digunakan", p: "Data digunakan untuk menyediakan fitur pohon keluarga, kolaborasi antar anggota, obrolan, notifikasi, dan pemrosesan pembayaran langganan. Kami tidak menjual data pribadi Anda kepada pihak ketiga." },
  { h: "3. Berbagi Data", p: "Data pohon Anda hanya dibagikan kepada anggota yang Anda undang atau setujui. Pembayaran diproses secara aman oleh Midtrans; kami tidak menyimpan detail kartu Anda." },
  { h: "4. Penyimpanan Foto", p: "Foto yang Anda unggah disimpan pada penyimpanan objek yang aman dan hanya dapat diakses melalui aplikasi oleh anggota pohon terkait." },
  { h: "5. Hak & Penghapusan Akun", p: "Anda dapat menghapus akun kapan saja melalui Setelan → Hapus Akun. Menghapus akun akan menghapus permanen akun Anda beserta seluruh pohon yang Anda miliki dan datanya. Anda juga dapat keluar dari grup atau pohon yang Anda ikuti." },
  { h: "6. Keamanan", p: "Kami menerapkan langkah keamanan yang wajar untuk melindungi data Anda. Namun, tidak ada sistem yang sepenuhnya aman; gunakan aplikasi dengan bijak." },
  { h: "7. Anak-anak", p: "Aplikasi ini tidak ditujukan untuk anak di bawah 13 tahun tanpa pengawasan orang tua/wali." },
  { h: "8. Perubahan Kebijakan", p: "Kebijakan ini dapat diperbarui sewaktu-waktu. Perubahan akan ditampilkan di halaman ini." },
  { h: "9. Kontak", p: "Untuk pertanyaan terkait privasi atau permintaan data, hubungi kami di emmusic.indonesia@gmail.com." },
];

export default function PrivacyScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const router = useRouter();
  const goBack = useGoBack("/");
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable style={styles.backBtn} onPress={() => goBack()} hitSlop={8} testID="privacy-back">
          <Feather name="chevron-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("privacy_policy")}</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: insets.bottom + 40 }}>
        <Text style={styles.p}>
          Titisanku menghargai privasi Anda. Kebijakan ini menjelaskan bagaimana kami mengumpulkan, menggunakan, dan melindungi data Anda saat menggunakan aplikasi.
        </Text>
        {SECTIONS.map((s) => (
          <View key={s.h}>
            <Text style={styles.h}>{s.h}</Text>
            <Text style={styles.p}>{s.p}</Text>
          </View>
        ))}
        <Text style={styles.updated}>Terakhir diperbarui: Juni 2026</Text>
      </ScrollView>
    </View>
  );
}
