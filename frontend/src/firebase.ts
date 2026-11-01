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
