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
  { h: "3. Berbagi Data", p: "Data pohon Anda hanya dibagikan kepada anggota yang Anda undang atau setujui. Pembayaran diproses secara aman oleh Google Play Billing (Android), Apple App Store (iOS), dan/atau Midtrans; kami tidak menyimpan detail kartu Anda." },
  { h: "4. Penyimpanan Foto", p: "Foto yang Anda unggah disimpan pada penyimpanan objek yang aman dan hanya dapat diakses melalui aplikasi oleh anggota pohon terkait." },
  { h: "5. Hak & Penghapusan Akun", p: "Anda dapat menghapus akun kapan saja melalui Setelan → Hapus Akun. Penghapusan akun menghapus profil dan keanggotaan Anda. Pohon keluarga yang Anda miliki TIDAK ikut dihapus: kepemilikannya dialihkan secara otomatis kepada anggota lain (admin yang paling lama bergabung lebih dahulu, lalu editor, lalu anggota lain), agar data silsilah tidak hilang bagi keluarga yang lain. Pohon hanya dihapus apabila Anda merupakan satu-satunya anggotanya." },
  { h: "6. Kepemilikan & Kontinuitas Data", p: "Anda adalah pemilik data silsilah yang Anda masukkan. Anda berhak mengunduh seluruh data beserta foto kapan saja melalui Setelan → Cadangan (berkas ZIP yang dapat dipulihkan kembali ke aplikasi). Kami menganjurkan Anda melakukan ekspor dan menyimpan salinannya sendiri secara berkala di perangkat atau penyimpanan pribadi Anda." },
  { h: "7. Penghentian Layanan & Masa Tenggang", p: "Kami berupaya menjaga layanan tetap berjalan, namun layanan ini disediakan sebagaimana adanya dan dapat dihentikan, diubah, atau dihentikan operasionalnya sewaktu-waktu, termasuk apabila bisnis tidak lagi dijalankan. Apabila layanan akan dihentikan secara permanen, kami akan berupaya memberitahukan melalui aplikasi dan/atau email terdaftar sekurang-kurangnya 90 (sembilan puluh) hari sebelumnya, sehingga Anda memiliki waktu yang cukup untuk mengekspor seluruh data dan foto Anda. Setelah masa tenggang berakhir, data dapat dihapus secara permanen." },
  { h: "8. Batasan Tanggung Jawab atas Data", p: "Meskipun kami berupaya mencegah kehilangan data, Anda memahami bahwa tidak ada sistem penyimpanan yang bebas dari risiko. Kami tidak bertanggung jawab atas kehilangan, kerusakan, atau tidak dapat diaksesnya data yang timbul dari force majeure, kegagalan penyedia layanan pihak ketiga, kegagalan perangkat Anda, atau kelalaian pengguna dalam menyimpan salinan cadangan sendiri. Tanggung jawab kami, sejauh diizinkan hukum yang berlaku, terbatas pada upaya wajar untuk memulihkan data dari cadangan internal kami." },
  { h: "9. Sifat Data Silsilah Keluarga", p: "Data yang Anda masukkan dapat mencakup informasi tentang anggota keluarga lain. Anda bertanggung jawab memastikan bahwa Anda berhak membagikan informasi tersebut, dan menghormati permintaan anggota yang tidak ingin datanya ditampilkan. Anggota dapat meminta penghapusan data dirinya melalui fitur yang tersedia atau menghubungi kami." },
  { h: "10. Keamanan", p: "Kami menerapkan langkah keamanan yang wajar untuk melindungi data Anda. Namun, tidak ada sistem yang sepenuhnya aman; gunakan aplikasi dengan bijak." },
  { h: "11. Konten Buatan Pengguna & Moderasi", p: "Fitur obrolan memungkinkan Anda mengirim pesan dan foto. Anda dilarang mengirim konten yang melanggar hukum, mengancam, melecehkan, mengandung kebencian, pornografi, atau spam. Setiap pesan dan profil pengguna dapat dilaporkan melalui menu Laporkan, dan setiap pengguna dapat diblokir melalui menu Blokir; pesan dari pengguna yang Anda blokir tidak akan ditampilkan kepada Anda. Laporan ditinjau oleh tim moderator kami, dan kami berhak menghapus konten serta menangguhkan atau menghentikan akun yang melanggar, tanpa pemberitahuan sebelumnya apabila diperlukan untuk melindungi pengguna lain. Pelanggaran berat dapat dilaporkan kepada pihak berwenang." },
  { h: "12. Anak-anak", p: "Aplikasi ini tidak ditujukan untuk anak di bawah 13 tahun tanpa pengawasan orang tua/wali." },
  { h: "13. Perubahan Kebijakan", p: "Kebijakan ini dapat diperbarui sewaktu-waktu. Perubahan akan ditampilkan di halaman ini beserta tanggal pembaruannya." },
  { h: "14. Kontak", p: "Untuk pertanyaan terkait privasi atau permintaan data, hubungi kami di emmusic.indonesia@gmail.com." },
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
        <Text style={styles.updated}>Terakhir diperbarui: Februari 2026</Text>
      </ScrollView>
    </View>
  );
}
