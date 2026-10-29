import React, { createContext, useContext, useEffect, useState } from "react";
import { Platform } from "react-native";
import { storage } from "@/src/utils/storage";
import { authSession, getMe, logoutApi, setToken, User } from "@/src/api";
import {
  firebaseConfigured,
  onIdToken,
  signInWithGoogle,
  signOutFirebase,
} from "@/src/firebase";

const TOKEN_KEY = "session_token";

type AuthCtx = {
  user: User | null;
  loading: boolean;
  signingIn: boolean;
  authError: string | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>({
  user: null,
  loading: true,
  signingIn: false,
  authError: null,
  login: async () => {},
  logout: async () => {},
  refresh: async () => {},
});

async function storeToken(token: string) {
  if (Platform.OS === "web") {
    try {
      window.localStorage.setItem(TOKEN_KEY, token);
    } catch {}
  } else {
    await storage.secureSet(TOKEN_KEY, token);
  }
}
async function readToken(): Promise<string | null> {
  if (Platform.OS === "web") {
    try {
      return window.localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  }
  return await storage.secureGet<string>(TOKEN_KEY, "");
}
async function clearToken() {
  if (Platform.OS === "web") {
    try {
      window.localStorage.removeItem(TOKEN_KEY);
    } catch {}
  } else {
    await storage.secureRemove(TOKEN_KEY);
  }
}

/** Pesan ramah untuk error Firebase Auth. */
function friendlyError(e: unknown): string {
  const code = (e as { code?: string })?.code || "";
  if (code.includes("popup-closed-by-user") || code.includes("cancelled")) return "";
  if (code.includes("popup-blocked")) return "Popup diblokir browser. Izinkan popup lalu coba lagi.";
  if (code.includes("network-request-failed")) return "Tidak ada koneksi internet.";
  if (code.includes("unauthorized-domain")) return "Domain ini belum diizinkan di Firebase Console.";
  if (code.includes("operation-not-allowed")) return "Metode login Google belum diaktifkan di Firebase Console.";
  return (e as Error)?.message || "Gagal masuk. Silakan coba lagi.";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [signingIn, setSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  /**
   * Tukar Firebase ID token dengan session token aplikasi kita, lalu simpan.
   * Dipakai saat login maupun saat token Firebase diperbarui otomatis.
   */
  const exchange = async (idToken: string) => {
    const res = await authSession(idToken);
    await storeToken(res.session_token);
    setToken(res.session_token);
    try {
      setUser(await getMe());
    } catch {
      setUser(res.user);
    }
  };

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      if (!firebaseConfigured()) {
        setAuthError("Konfigurasi Firebase belum lengkap (EXPO_PUBLIC_FIREBASE_*).");
        setLoading(false);
        return;
      }
      // Bila user sudah login di Firebase, pakai ID token terbaru.
      try {
        const idToken = await onIdToken();
        if (idToken && !cancelled) {
          await exchange(idToken);
          setLoading(false);
          return;
        }
      } catch (e) {
        console.log("firebase restore gagal", e);
      }
      // Fallback: session token lokal yang masih valid.
      const token = await readToken();
      if (token && !cancelled) {
        setToken(token);
        try {
          setUser(await getMe());
        } catch {
          await clearToken();
          setToken(null);
          setUser(null);
        }
      }
      if (!cancelled) setLoading(false);
    };

    bootstrap();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async () => {
    setAuthError(null);
    setSigningIn(true);
    try {
      const idToken = await signInWithGoogle();
      if (!idToken) return; // user menutup popup
      await exchange(idToken);
    } catch (e) {
      const msg = friendlyError(e);
      if (msg) setAuthError(msg);
      console.log("login error", e);
    } finally {
      setSigningIn(false);
    }
  };

  const logout = async () => {
    try {
      await logoutApi();
    } catch {}
    try {
      await signOutFirebase();
    } catch {}
    await clearToken();
    setToken(null);
    setUser(null);
  };

  const refresh = async () => {
    try {
      setUser(await getMe());
    } catch {}
  };

  return (
    <Ctx.Provider value={{ user, loading, signingIn, authError, login, logout, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
