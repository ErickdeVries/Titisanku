import { Platform } from "react-native";

export const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL as string;
const API = `${BACKEND_URL}/api`;

let authToken: string | null = null;
export function setToken(token: string | null) {
  authToken = token;
}
export function getToken() {
  return authToken;
}

let activeTreeId: string | null = null;
export function setActiveTree(id: string | null) {
  activeTreeId = id;
}
export function getActiveTree() {
  return activeTreeId;
}

function withTree(path: string): string {
  if (!activeTreeId || path.includes("tree_id=")) return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}tree_id=${encodeURIComponent(activeTreeId)}`;
}

async function apiFetch(path: string, opts: RequestInit = {}) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  const res = await fetch(`${API}${withTree(path)}`, { ...opts, headers });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {}
    const err: any = new Error(detail);
    err.status = res.status;
    throw err;
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

export type Person = {
  id: string;
  name: string;
  gender?: string | null;
  birth_date?: string | null;
  birth_place?: string | null;
  death_date?: string | null;
  photo_url?: string | null;
  job?: string | null;
  is_adopted?: boolean;
  notes?: string | null;
  is_root?: boolean;
  note_count?: number;
};

export type Relation = {
  id: string;
  person_id: string;
  related_person_id: string;
  relation_type: "parent" | "adopted_child" | "spouse" | "divorced" | "sibling";
  marriage_date?: string | null;
  divorce_date?: string | null;
};

export type User = {
  user_id: string;
  email: string;
  name: string;
  picture?: string | null;
  role: "admin" | "editor" | "viewer";
};

// ---- Auth ----
export const authSession = (session_id: string) =>
  apiFetch("/auth/session", { method: "POST", body: JSON.stringify({ session_id }) });
export const getMe = () => apiFetch("/auth/me");
export const logoutApi = () => apiFetch("/auth/logout", { method: "POST" });

export type Tree = {
  id: string;
  name: string;
  owner_id: string;
  plan: "free" | "pro";
  root_person_id: string | null;
  role: "admin" | "editor" | "viewer";
  person_count: number;
  member_count?: number;
  limit: number | null;
};

export type TreeMember = {
  user_id: string;
  role: "admin" | "editor" | "viewer";
  name: string;
  email?: string | null;
  picture?: string | null;
  is_owner: boolean;
};

// ---- Tree / People ----
export const getTree = (): Promise<{
  people: Person[];
  relations: Relation[];
  root_id: string | null;
  tree?: any;
  role?: string | null;
  person_count?: number;
  limit?: number | null;
}> => apiFetch("/tree");

// ---- Trees (multi-tenant) ----
export const listTrees = (): Promise<Tree[]> => apiFetch("/trees");
export const createTree = (name: string): Promise<Tree> =>
  apiFetch("/trees", { method: "POST", body: JSON.stringify({ name }) });
export const upgradeTree = (tid: string) =>
  apiFetch(`/trees/${tid}/upgrade?tree_id=${tid}`, { method: "POST" });
export const getMembers = (tid: string): Promise<{ members: TreeMember[]; role: string; owner_id: string }> =>
  apiFetch(`/trees/${tid}/members?tree_id=${tid}`);
export const changeMemberRole = (tid: string, user_id: string, role: string) =>
  apiFetch(`/trees/${tid}/members/role?tree_id=${tid}`, { method: "PUT", body: JSON.stringify({ user_id, role }) });
export const removeMember = (tid: string, member_id: string) =>
  apiFetch(`/trees/${tid}/members/${member_id}?tree_id=${tid}`, { method: "DELETE" });

export const listPeople = (q?: string): Promise<Person[]> =>
  apiFetch(`/people${q ? `?q=${encodeURIComponent(q)}` : ""}`);
export const getPerson = (id: string): Promise<Person> => apiFetch(`/people/${id}`);
export const addRelative = (payload: any) =>
  apiFetch("/people/add-relative", { method: "POST", body: JSON.stringify(payload) });
export const updatePerson = (id: string, data: any) =>
  apiFetch(`/people/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const deletePerson = (id: string) => apiFetch(`/people/${id}`, { method: "DELETE" });

// ---- Backup / Invites ----
export const getBackup = () => apiFetch("/backup");
export const restoreBackup = (payload: { people: any[]; relations: any[] }) =>
  apiFetch("/restore", { method: "POST", body: JSON.stringify(payload) });
export const createInvite = (email: string) =>
  apiFetch("/invite", { method: "POST", body: JSON.stringify({ email }) });
export const acceptInvite = (code: string) =>
  apiFetch("/invite/accept", { method: "POST", body: JSON.stringify({ code }) });
export const listInvites = () => apiFetch("/invites");

// ---- Person notes & files ----
export const listPersonNotes = (personId: string) => apiFetch(`/people/${personId}/notes`);
export const addPersonNote = (personId: string, note_text: string) =>
  apiFetch(`/people/${personId}/notes`, { method: "POST", body: JSON.stringify({ note_text }) });
export const deleteNote = (noteId: string) => apiFetch(`/notes/${noteId}`, { method: "DELETE" });

export async function addPersonFile(personId: string, uri: string): Promise<any> {
  const name = uri.split("/").pop() || `file_${Date.now()}`;
  const match = /\.(\w+)$/.exec(name);
  const type = match ? `image/${match[1] === "jpg" ? "jpeg" : match[1]}` : "application/octet-stream";
  const form = new FormData();
  if (Platform.OS === "web") {
    const blob = await (await fetch(uri)).blob();
    form.append("file", blob, name);
  } else {
    form.append("file", { uri, name, type } as any);
  }
  const res = await fetch(`${API}/people/${personId}/files${activeTreeId ? `?tree_id=${activeTreeId}` : ""}`, {
    method: "POST",
    headers: { ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) },
    body: form,
  });
  if (!res.ok) throw new Error("Upload failed");
  return res.json();
}

// ---- Family chat ----
export const getChat = () => apiFetch("/chat");
export const sendChat = (payload: { message?: string; attachments?: string[]; reply_to?: string | null; mentions?: string[] }) =>
  apiFetch("/chat", { method: "POST", body: JSON.stringify(payload) });
export const deleteChat = (msgId: string) => apiFetch(`/chat/${msgId}`, { method: "DELETE" });
export const setTyping = () => apiFetch("/chat/typing", { method: "POST" });

// ---- Notifications ----
export const getNotifications = () => apiFetch("/notifications");
export const markNotificationsRead = (type?: string) =>
  apiFetch(`/notifications/read${type ? `?type=${type}` : ""}`, { method: "POST" });

// ---- Files ----
export function fileUrl(pathOrUrl?: string | null): string | undefined {
  if (!pathOrUrl) return undefined;
  if (pathOrUrl.startsWith("http")) return pathOrUrl;
  const clean = pathOrUrl.startsWith("/api/files/") ? pathOrUrl.replace("/api/files/", "") : pathOrUrl;
  return `${API}/files/${clean}?token=${authToken ?? ""}`;
}

export async function uploadPhoto(uri: string): Promise<string> {
  const name = uri.split("/").pop() || `photo_${Date.now()}.jpg`;
  const match = /\.(\w+)$/.exec(name);
  const type = match ? `image/${match[1] === "jpg" ? "jpeg" : match[1]}` : "image/jpeg";
  const form = new FormData();
  if (Platform.OS === "web") {
    const blob = await (await fetch(uri)).blob();
    form.append("file", blob, name);
  } else {
    form.append("file", { uri, name, type } as any);
  }
  const res = await fetch(`${API}/upload`, {
    method: "POST",
    headers: { ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) },
    body: form,
  });
  if (!res.ok) throw new Error("Upload failed");
  const data = await res.json();
  return data.path as string;
}
