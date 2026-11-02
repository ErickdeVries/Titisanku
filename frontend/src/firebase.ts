/**
 * Firebase Auth — Google Sign-In langsung via Firebase SDK (mandiri, tanpa proxy OAuth pihak ketiga).
 *
 * Konfigurasi lewat env Expo (prefix `EXPO_PUBLIC_` agar ikut ter-bundle):
 *   EXPO_PUBLIC_FIREBASE_API_KEY
 *   EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN
 *   EXPO_PUBLIC_FIREBASE_PROJECT_ID
 *   EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET
 *   EXPO_PUBLIC_FIREBASE_APP_ID
 *
 * Google Sign-In hanya aktif bila `google-services.json` tersedia
 * (Android) / `GoogleService-Info.plist` (iOS), sesuai alur native Firebase.
 */
import { Platform } from "react-native";
import { initializeApp, getApps, getApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  OAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signInWithCredential,
  signOut,
  type Auth,
} from "firebase/auth";

const config = {
  apiKey: process.env.EXPO_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET,
  appId: process.env.EXPO_PUBLIC_FIREBASE_APP_ID,
};

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

export function firebaseConfigured(): boolean {
  return Boolean(config.apiKey && config.authDomain && config.projectId && config.appId);
}

function getFirebaseAuth(): Auth {
  if (!firebaseConfigured()) {
    throw new Error("Firebase belum dikonfigurasi: set EXPO_PUBLIC_FIREBASE_* di .env");
  }
  if (!app) {
    app = getApps().length ? getApp() : initializeApp(config as Required<typeof config>);
  }
  if (!auth) auth = getAuth(app);
  return auth;
}

/**
 * Muat + konfigurasi modul native Google Sign-In (hanya dipakai di Android/iOS).
 * Dilepas dari signInWithGoogle agar bisa dipakai juga saat logout.
 */
async function loadNativeGoogle() {
  const gsi = await import("@react-native-google-signin/google-signin");
  const webClientId = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;
  if (!webClientId) {
    throw new Error("EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID belum diisi (dibutuhkan untuk Google Sign-In native).");
  }
  gsi.GoogleSignin.configure({ webClientId });
  return gsi;
}

/**
 * Buang sesi Google yang di-cache modul native di perangkat.
 *
 * Tanpa ini, `GoogleSignin.signIn()` memakai ulang akun terakhir yang pernah
 * dipakai tanpa menampilkan sheet pemilihan akun, sehingga pengguna tidak bisa
 * ganti akun saat login. Kegagalan pembersihan tidak boleh menghalangi login.
 */
export async function forgetGoogleSession(): Promise<void> {
  if (Platform.OS === "web") return;
  try {
    const gsi = await loadNativeGoogle();
    if (gsi.GoogleSignin.hasPreviousSignIn()) await gsi.GoogleSignin.signOut();
  } catch {
    // diamkan: percobaan login berikutnya tetap akan menampilkan sheet Google
  }
}

/**
 * ID token terbaru bila pengguna sudah login di Firebase, atau null.
 * `getIdToken(true)` memaksa refresh agar tidak memakai token kedaluwarsa.
 */
export async function onIdToken(): Promise<string | null> {
  const a = getFirebaseAuth();
  const current = a.currentUser;
  if (current) return current.getIdToken(true);

  // Tunggu sekali event state agar sesi persisten sempat dipulihkan.
  return new Promise((resolve) => {
    const unsub = onAuthStateChanged(a, async (u) => {
      unsub();
      resolve(u ? u.getIdToken(true) : null);
    });
  });
}

/** Login Google. Mengembalikan ID token, atau null bila pengguna membatalkan. */
export async function signInWithGoogle(): Promise<string | null> {
  const a = getFirebaseAuth();
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });

  if (Platform.OS === "web") {
    try {
      const result = await signInWithPopup(a, provider);
      return await result.user.getIdToken(true);
    } catch (e) {
      const code = (e as { code?: string })?.code || "";
      if (code.includes("popup-closed-by-user") || code.includes("cancelled-popup-request")) return null;
      throw e;
    }
  }

  // Native (Android/iOS): gunakan @react-native-google-signin/google-signin.
  // Diimpor dinamis agar web tetap bisa build tanpa modul native ini.
  try {
    const gsi = await loadNativeGoogle();
    await gsi.GoogleSignin.hasPlayServices();
    // Modul native menyimpan sesi Google terakhir. Kalau tidak dibersihkan,
    // GoogleSignin.signIn() langsung memakai akun itu tanpa menampilkan sheet
    // pemilihan akun — akibatnya pengguna tidak bisa ganti akun saat login.
    await forgetGoogleSession();
    const res = await gsi.GoogleSignin.signIn();
    const idToken = res.data?.idToken ?? (res as { idToken?: string }).idToken;
    if (!idToken) throw new Error("Google Sign-In tidak mengembalikan idToken.");
    const credential = GoogleAuthProvider.credential(idToken);
    const userCred = await signInWithCredential(a, credential);
    return await userCred.user.getIdToken(true);
  } catch (e) {
    const code = (e as { code?: string })?.code || "";
    if (code === "SIGN_IN_CANCELLED" || code === "12501") return null;
    throw e;
  }
}

export async function signOutFirebase(): Promise<void> {
  // Bersihkan sesi Google kached di perangkat juga, supaya login berikutnya
  // menampilkan pilihan akun (bukan otomatis masuk ke akun yang sama).
  await forgetGoogleSession();
  if (!firebaseConfigured()) return;
  await signOut(getFirebaseAuth());
}

// ---------------------------------------------------------------------------
// Sign in with Apple (iOS 13+). Wajib ada karena App Store Review Guideline
// 4.8: aplikasi yang menyediakan login pihak ketiga (Google) harus juga
// menyediakan Sign in with Apple. Tanpa ini build iOS akan DITOLAK.
//
// Native (iOS): expo-apple-authentication menghasilkan identityToken yang
// ditukar menjadi sesi Firebase (credential OAuth "apple.com").
// Web: lewat popup Firebase (butuh Service ID Apple di Firebase Console).
// Android: Apple tidak menyediakan Sign in with Apple native — tombol tidak
// ditampilkan, jadi fungsi ini hanya dipanggil bila `appleSignInAvailable()`.
// ---------------------------------------------------------------------------

/** Apple mengirim email relay `@privaterelay.appleid.com` bila pengguna memilih
 *  menyembunyikan email. Formatnya valid, tapi tidak boleh dipakai untuk
 *  deduplikasi lintas identitas — server menyimpan `provider` terpisah. */
export function isPrivateRelayEmail(email?: string | null): boolean {
  return !!email && /@privaterelay\.appleid\.com$/i.test(email);
}

/**
 * True bila tombol Apple layak ditampilkan. Di iOS dicek ke modul native
 * (perangkat bisa Apple ID-nya belum login); di web cukup konfigurasi Firebase.
 */
export async function appleSignInAvailable(): Promise<boolean> {
  if (!firebaseConfigured()) return false;
  if (Platform.OS === "web") return true;
  if (Platform.OS !== "ios") return false;
  try {
    const AppleAuthentication = await import("expo-apple-authentication");
    return await AppleAuthentication.isAvailableAsync();
  } catch {
    // Modul native belum terpasang (mis. build lama) → jangan tampilkan tombol
    // yang pasti gagal saat ditekan.
    return false;
  }
}

/** Login Apple. Mengembalikan ID token Firebase, atau null bila dibatalkan. */
export async function signInWithApple(): Promise<string | null> {
  if (!firebaseConfigured()) {
    throw new Error("Firebase belum dikonfigurasi: set EXPO_PUBLIC_FIREBASE_* di .env");
  }
  const a = getFirebaseAuth();
  const provider = new OAuthProvider("apple.com");
  provider.addScope("email");
  provider.addScope("name");

  if (Platform.OS === "web") {
    try {
      const result = await signInWithPopup(a, provider);
      return await result.user.getIdToken(true);
    } catch (e) {
      const code = (e as { code?: string })?.code || "";
      if (code.includes("popup-closed-by-user") || code.includes("cancelled-popup-request")) return null;
      throw e;
    }
  }

  const AppleAuthentication = await import("expo-apple-authentication");
  // Nonce mencegah replay token Apple: Firebase memverifikasi klaim `nonce`
  // di identityToken terhadap hash SHA-256 yang kita kirim sebagai `nonce`.
  const rawNonce = generateNonce();
  let credential;
  try {
    credential = await AppleAuthentication.signInAsync({
      requestedScopes: [
        AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        AppleAuthentication.AppleAuthenticationScope.EMAIL,
      ],
      nonce: await sha256Hex(rawNonce),
    });
  } catch (e) {
    // ERR_REQUEST_CANCELED = pengguna menutup sheet; bukan kegagalan.
    if ((e as { code?: string })?.code === "ERR_REQUEST_CANCELED") return null;
    throw e;
  }
  if (!credential.identityToken) {
    throw new Error("Apple Sign-In tidak mengembalikan identityToken.");
  }

  const firebaseCredential = provider.credential({
    idToken: credential.identityToken,
    rawNonce,
  });
  const userCred = await signInWithCredential(a, firebaseCredential);

  // Nama lengkap HANYA dikirim Apple pada login pertama, tidak pernah lagi.
  // Simpan ke profil Firebase agar tidak hilang selamanya.
  if (credential.fullName?.givenName && !userCred.user.displayName) {
    const parts = [credential.fullName.givenName, credential.fullName.middleName, credential.fullName.familyName];
    try {
      const { updateProfile } = await import("firebase/auth");
      await updateProfile(userCred.user, { displayName: parts.filter(Boolean).join(" ") });
    } catch {
      // best-effort: login tetap berhasil walau nama tidak tersimpan
    }
  }
  return await userCred.user.getIdToken(true);
}

/** Nonce acak kriptografis (hex). */
function generateNonce(length = 32): string {
  const bytes = new Uint8Array(length);
  const cryptoObj = (globalThis as { crypto?: Crypto }).crypto;
  if (cryptoObj?.getRandomValues) {
    cryptoObj.getRandomValues(bytes);
  } else {
    // Fallback non-kriptografis hanya untuk runtime tanpa Web Crypto; nonce
    // tetap unik. Di iOS/Android native Web Crypto selalu tersedia.
    for (let i = 0; i < length; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** SHA-256 hex dari string UTF-8, memakai expo-crypto bila tersedia. */
async function sha256Hex(input: string): Promise<string> {
  try {
    const Crypto = await import("expo-crypto");
    return await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, input);
  } catch {
    const webCrypto = (globalThis as { crypto?: Crypto }).crypto;
    if (!webCrypto?.subtle) throw new Error("SHA-256 tidak tersedia di runtime ini.");
    const digest = await webCrypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  }
}
