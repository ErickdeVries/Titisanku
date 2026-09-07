// Chat notification sound registry. Assets are static require()s so Metro bundles them.
// Selection is persisted under storage key "chat_sound".
export type ChatSoundKey = "ding" | "chime" | "pop" | "bell" | "none";

export const CHAT_SOUND_STORAGE_KEY = "chat_sound";
export const DEFAULT_CHAT_SOUND: ChatSoundKey = "ding";

export type ChatSound = {
  key: ChatSoundKey;
  label: string;
  asset: number | null; // null = silent
};

export const CHAT_SOUNDS: ChatSound[] = [
  { key: "ding", label: "Ding", asset: require("../../assets/ding.wav") },
  { key: "chime", label: "Chime", asset: require("../../assets/chime.wav") },
  { key: "pop", label: "Pop", asset: require("../../assets/pop.wav") },
  { key: "bell", label: "Bell", asset: require("../../assets/bell.wav") },
  { key: "none", label: "Senyap", asset: null },
];

export function soundByKey(key: string | null): ChatSound {
  return CHAT_SOUNDS.find((s) => s.key === key) ?? CHAT_SOUNDS[0];
}
