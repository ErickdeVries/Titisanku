import { Platform } from "react-native";
import { File as FsFile } from "expo-file-system";

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
    err.detail = detail;
    throw err;
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

/**
 * Ubah error API menjadi pesan yang bisa ditampilkan ke pengguna.
 * Backend mengirim detail berprefix (STORAGE_LIMIT:/MEMBER_LIMIT:/EDITOR_LIMIT:)
 * agar frontend tahu ini batas paket, bukan kerusakan sistem.
 */
export function limitMessage(e: any): string | null {
  const detail = typeof e?.detail === "string" ? e.detail
    : typeof e?.message === "string" ? e.message : "";
  const clean = detail.replace(/^[A-Z_]+:/, "").trim();
  if (e?.status === 402) {
    return clean || "Kuota paket Anda sudah penuh. Upgrade plan untuk melanjutkan.";
  }
  return null;
}

export function isLimitError(e: any): boolean {
  return e?.status === 402;
}

export type Person = {
  id: string;
  name: string;
  gender?: string | null;
  birth_date?: string | null;
  birth_place?: string | null;
  death_date?: string | null;
  photo_url?: string | null;
  cover_url?: string | null;
  job?: string | null;
  is_adopted?: boolean;
  notes?: string | null;
  is_root?: boolean;
  note_count?: number;
  gallery?: GalleryPhoto[];
  privacy?: Record<string, PrivacyEntry> | null;
  redacted_fields?: string[];
};

export type PrivacyField = "birth_date" | "birth_place" | "job" | "death_date" | "notes";

/** One field's visibility. `hidden` with an empty `allow` means "nobody else";
 *  `allow` lists the members who may still see it. The API always returns this
 *  shape, even for records saved before allow-lists existed. */
export type PrivacyEntry = { hidden: boolean; allow: string[] };

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
  is_superadmin?: boolean;
};

// ---- Auth ----
export const authSession = (session_id: string) =>
  apiFetch("/auth/session", { method: "POST", body: JSON.stringify({ session_id }) });
export const getMe = () => apiFetch("/auth/me");
export const updateProfile = (data: { name?: string; picture?: string }) =>
  apiFetch("/users/me", { method: "PUT", body: JSON.stringify(data) });
export const logoutApi = () => apiFetch("/auth/logout", { method: "POST" });
export const leaveGroup = (roomId: string): Promise<{ ok: boolean }> =>
  apiFetch(`/chat/rooms/${roomId}/leave`, { method: "POST" });
export const submitFeedback = (message: string, category: string): Promise<{ ok: boolean }> =>
  apiFetch("/feedback", { method: "POST", body: JSON.stringify({ message, category }) });
export const deleteAccount = (): Promise<{ ok: boolean }> =>
  apiFetch("/account", { method: "DELETE" });
export const adminOverview = () => apiFetch("/admin/overview");
export const adminUsers = () => apiFetch("/admin/users");
export const adminFeedback = () => apiFetch("/admin/feedback");

export type PlanId = "free" | "pro" | "family" | "unlimited";

export type Tree = {
  id: string;
  name: string;
  owner_id: string;
  plan: PlanId;
  is_public?: boolean;
  root_person_id: string | null;
  role: "admin" | "editor" | "viewer";
  person_count: number;
  member_count?: number;
  editor_count?: number;
  photo_count?: number;
  /** Batas orang & editor. Kuota foto memakai `storage_limit` (byte). */
  plan_limits?: { people: number | null; editors: number | null };
  /** Pemakaian penyimpanan pohon dalam byte (foto, lampiran, galeri). */
  storage_used?: number;
  /** Kuota penyimpanan dalam byte; null = tak terbatas. */
  storage_limit?: number | null;
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
export const deleteTree = (tid: string): Promise<{ ok: boolean }> =>
  apiFetch(`/trees/${tid}`, { method: "DELETE" });
export const claimBranch = (
  tid: string,
  person_id: string,
  scope: "descendants" | "children" | "whole",
  name?: string,
): Promise<Tree & { copied: number }> =>
  apiFetch(`/trees/${tid}/claim-branch?tree_id=${tid}`, {
    method: "POST",
    body: JSON.stringify({ person_id, scope, name }),
  });
export const upgradeTree = (tid: string, plan: "pro" | "family" = "pro") =>
  apiFetch(`/trees/${tid}/upgrade?tree_id=${tid}`, { method: "POST", body: JSON.stringify({ plan }) });
export const createSnap = (plan: string, finishUrl?: string): Promise<{ order_id: string; token: string; redirect_url: string; amount: number; plan: string }> =>
  apiFetch("/payments/snap", { method: "POST", body: JSON.stringify({ plan, finish_url: finishUrl }) });
export const paymentStatus = (orderId: string): Promise<{ status: string; plan: string }> =>
  apiFetch(`/payments/status/${orderId}`);
export type PaymentOrder = { order_id: string; plan: string; amount: number; status: string; created_at: string; paid_at?: string; tree_name?: string };
export const paymentHistory = (): Promise<{ orders: PaymentOrder[] }> =>
  apiFetch("/payments/history");
export const getMembers = (tid: string): Promise<{ members: TreeMember[]; role: string; owner_id: string }> =>
  apiFetch(`/trees/${tid}/members?tree_id=${tid}`);
export const changeMemberRole = (tid: string, user_id: string, role: string) =>
  apiFetch(`/trees/${tid}/members/role?tree_id=${tid}`, { method: "PUT", body: JSON.stringify({ user_id, role }) });
export const removeMember = (tid: string, member_id: string) =>
  apiFetch(`/trees/${tid}/members/${member_id}?tree_id=${tid}`, { method: "DELETE" });
export const deleteRelation = (relId: string) =>
  apiFetch(`/relations/${relId}`, { method: "DELETE" });
export const updateRelation = (relId: string, data: { marriage_date: string | null; divorce_date: string | null; is_divorced: boolean }) =>
  apiFetch(`/relations/${relId}`, { method: "PUT", body: JSON.stringify(data) });
export const linkCoparents = (): Promise<{ linked: number }> =>
  apiFetch(`/tree/link-coparents`, { method: "POST" });

export const listPeople = (q?: string): Promise<Person[]> =>
  apiFetch(`/people${q ? `?q=${encodeURIComponent(q)}` : ""}`);
export const getPerson = (id: string): Promise<Person> => apiFetch(`/people/${id}`);
export type GalleryPhoto = { id: string; path: string; caption?: string; date?: string };
export const addGalleryPhoto = (id: string, path: string, caption?: string, date?: string): Promise<{ gallery: GalleryPhoto[] }> =>
  apiFetch(`/people/${id}/gallery`, { method: "POST", body: JSON.stringify({ path, caption, date }) });
export const editGalleryPhoto = (id: string, photoId: string, caption?: string, date?: string): Promise<{ gallery: GalleryPhoto[] }> =>
  apiFetch(`/people/${id}/gallery/${photoId}`, { method: "PATCH", body: JSON.stringify({ caption, date }) });
export const removeGalleryPhoto = (id: string, photoId: string): Promise<{ gallery: GalleryPhoto[] }> =>
  apiFetch(`/people/${id}/gallery`, { method: "DELETE", body: JSON.stringify({ id: photoId }) });
export const addRelative = (payload: any) =>
  apiFetch("/people/add-relative", { method: "POST", body: JSON.stringify(payload) });
export const addFirstPerson = (person: any): Promise<Person> =>
  apiFetch("/people/first", { method: "POST", body: JSON.stringify(person) });
export const updatePerson = (id: string, data: any) =>
  apiFetch(`/people/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const setPersonPrivacy = (
  id: string,
  privacy: Record<string, PrivacyEntry | boolean>,
) => apiFetch(`/people/${id}/privacy`, { method: "PUT", body: JSON.stringify(privacy) });
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

// ---- Tree invite links ----
export const createInviteLink = (tid: string): Promise<{ token: string }> =>
  apiFetch(`/trees/${tid}/invite-link?tree_id=${tid}`, { method: "POST" });
export const getInviteInfo = (
  token: string,
): Promise<{ tree_id: string; tree_name: string; inviter_name: string; role: string; already_member: boolean }> =>
  apiFetch(`/invite-info/${token}`);
export const acceptInviteLink = (token: string): Promise<{ tree_id: string; name: string }> =>
  apiFetch(`/invite-accept/${token}`, { method: "POST" });

// ---- Join requests & public search ----
export type PublicTree = { id: string; name: string; owner_name: string; member_count: number; is_member: boolean; pending: boolean };
export const searchTrees = (q: string): Promise<PublicTree[]> =>
  apiFetch(`/trees/search?q=${encodeURIComponent(q)}`);
export const requestJoin = (treeId: string): Promise<{ ok: boolean; status: string; tree_name: string }> =>
  apiFetch(`/trees/${treeId}/join-request`, { method: "POST" });
export const listJoinRequests = (treeId: string): Promise<any[]> =>
  apiFetch(`/trees/${treeId}/join-requests?tree_id=${treeId}`);
export const actJoinRequest = (reqId: string, action: "approve" | "reject") =>
  apiFetch(`/join-requests/${reqId}/${action}`, { method: "POST" });
export const setTreeVisibility = (treeId: string, is_public: boolean) =>
  apiFetch(`/trees/${treeId}/visibility?tree_id=${treeId}`, { method: "PUT", body: JSON.stringify({ is_public }) });

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
export type ChatRoom = {
  id: string;
  type: "family" | "group" | "direct";
  name: string;
  picture?: string | null;
  member_count: number;
  last_message: string;
  last_message_at?: string | null;
  unread: number;
  muted?: boolean;
};
export type ChatContact = { user_id: string; name: string; picture?: string | null; role: string };

export const listChatRooms = (): Promise<{ rooms: ChatRoom[] }> => apiFetch("/chat/rooms");
export const chatContacts = (): Promise<{ contacts: ChatContact[] }> => apiFetch("/chat/contacts");
export const createGroup = (name: string, member_ids: string[], picture?: string | null): Promise<ChatRoom> =>
  apiFetch("/chat/group", { method: "POST", body: JSON.stringify({ name, member_ids, picture }) });
export const openDirect = (user_id: string): Promise<ChatRoom> =>
  apiFetch("/chat/direct", { method: "POST", body: JSON.stringify({ user_id }) });
export const updateGroup = (roomId: string, data: { name?: string; member_ids?: string[]; picture?: string | null }): Promise<ChatRoom> =>
  apiFetch(`/chat/rooms/${roomId}`, { method: "PUT", body: JSON.stringify(data) });
export const muteRoom = (roomId: string, muted: boolean): Promise<{ ok: boolean; muted: boolean }> =>
  apiFetch(`/chat/rooms/${roomId}/mute`, { method: "POST", body: JSON.stringify({ muted }) });

export const getChat = (roomId?: string) =>
  apiFetch(`/chat${roomId ? `?room_id=${encodeURIComponent(roomId)}` : ""}`);
export const sendChat = (
  payload: { message?: string; attachments?: string[]; reply_to?: string | null; mentions?: string[] },
  roomId?: string,
) => apiFetch(`/chat${roomId ? `?room_id=${encodeURIComponent(roomId)}` : ""}`, { method: "POST", body: JSON.stringify(payload) });
export const deleteChat = (msgId: string) => apiFetch(`/chat/${msgId}`, { method: "DELETE" });
export const setTyping = (roomId?: string) =>
  apiFetch(`/chat/typing${roomId ? `?room_id=${encodeURIComponent(roomId)}` : ""}`, { method: "POST" });

// ---- Notifications ----
export type AppNotification = {
  id: string;
  type: string;
  title: string;
  body?: string;
  read: boolean;
  created_at: string;
};
export const getNotifications = (): Promise<{ unread: number; unread_chat: number; items: AppNotification[] }> =>
  apiFetch("/notifications");
export const registerPush = (platform: string, device_token: string): Promise<{ status: string }> =>
  apiFetch("/register-push", { method: "POST", body: JSON.stringify({ platform, device_token }) });
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
  const form = new FormData();
  if (Platform.OS === "web") {
    const blob = await (await fetch(uri)).blob();
    form.append("file", blob, name);
  } else {
    // Expo SDK 54+ "winter" fetch rejects the legacy { uri, name, type } part.
    // Use the File class (implements the Blob interface) instead.
    form.append("file", new FsFile(uri) as unknown as Blob, name);
  }
  const qs = activeTreeId ? `?tree_id=${encodeURIComponent(activeTreeId)}` : "";
  const res = await fetch(`${API}/upload${qs}`, {
    method: "POST",
    headers: { ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) },
    body: form,
  });
  if (!res.ok) {
    let detail = "Upload failed";
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  const data = await res.json();
  return data.path as string;
}
