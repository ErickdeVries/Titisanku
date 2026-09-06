import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { storage } from "@/src/utils/storage";
import { authSession, getMe, logoutApi, setToken, User } from "@/src/api";

WebBrowser.maybeCompleteAuthSession();

const TOKEN_KEY = "session_token";

type AuthCtx = {
  user: User | null;
  loading: boolean;
  signingIn: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>({
  user: null,
  loading: true,
  signingIn: false,
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

function extractSessionId(url: string | null | undefined): string | null {
  if (!url) return null;
  const m = /[?#&]session_id=([^&#]+)/.exec(url);
  return m ? decodeURIComponent(m[1]) : null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [signingIn, setSigningIn] = useState(false);
  const processed = useRef<Set<string>>(new Set());

  const exchange = async (sessionId: string) => {
    if (processed.current.has(sessionId)) return;
    processed.current.add(sessionId);
    setSigningIn(true);
    try {
      const res = await authSession(sessionId);
      await storeToken(res.session_token);
      setToken(res.session_token);
      // Fetch the full profile (includes is_superadmin) rather than the raw
      // session user, so superadmin-only UI shows right after first login.
      try {
        const me = await getMe();
        setUser(me);
      } catch {
        setUser(res.user);
      }
    } catch (e) {
      console.log("auth exchange error", e);
    } finally {
      setSigningIn(false);
    }
  };

  const bootstrap = async () => {
    // web: check session_id in URL first
    if (Platform.OS === "web") {
      const sid = extractSessionId(window.location.hash) || extractSessionId(window.location.search);
      if (sid) {
        await exchange(sid);
        try {
          window.history.replaceState(window.history.state, "", window.location.pathname);
        } catch {}
        setLoading(false);
        return;
      }
    } else {
      const initial = await Linking.getInitialURL();
      const sid = extractSessionId(initial);
      if (sid) {
        await exchange(sid);
        setLoading(false);
        return;
      }
    }
    // otherwise check existing token
    const token = await readToken();
    if (token) {
      setToken(token);
      try {
        const me = await getMe();
        setUser(me);
      } catch {
        await clearToken();
        setToken(null);
        setUser(null);
      }
    }
    setLoading(false);
  };

  useEffect(() => {
    bootstrap();
    const sub = Linking.addEventListener("url", ({ url }) => {
      const sid = extractSessionId(url);
      if (sid) exchange(sid);
    });
    return () => sub.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async () => {
    const redirectUrl = Platform.OS === "web" ? window.location.origin + "/" : Linking.createURL("");
    const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
    if (Platform.OS === "web") {
      // Use replace (not href) so the auth URL is NOT kept in the browser back-history.
      // Otherwise pressing Back returns to a consumed auth page -> "Invalid state parameter".
      window.location.replace(authUrl);
      return;
    }
    setSigningIn(true);
    try {
      const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
      let sid: string | null = null;
      if (result.type === "success" && result.url) sid = extractSessionId(result.url);
      if (!sid) sid = extractSessionId(await Linking.getInitialURL());
      if (sid) await exchange(sid);
    } catch (e) {
      console.log("login error", e);
    } finally {
      setSigningIn(false);
    }
  };

  const logout = async () => {
    try {
      await logoutApi();
    } catch {}
    await clearToken();
    setToken(null);
    setUser(null);
  };

  const refresh = async () => {
    try {
      const me = await getMe();
      setUser(me);
    } catch {}
  };

  return (
    <Ctx.Provider value={{ user, loading, signingIn, login, logout, refresh }}>{children}</Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
