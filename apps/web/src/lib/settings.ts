const KEY = "nac-tts-settings";

export type LocalSettings = {
  voiceId: string;
  speakingRate: number;
};

export function loadSettings(): LocalSettings {
  const raw = localStorage.getItem(KEY);
  if (!raw) {
    return { voiceId: "af_heart", speakingRate: 1 };
  }
  try {
    const parsed = JSON.parse(raw) as Partial<LocalSettings>;
    return {
      voiceId: parsed.voiceId ?? "af_heart",
      speakingRate: parsed.speakingRate ?? 1,
    };
  } catch {
    return { voiceId: "af_heart", speakingRate: 1 };
  }
}

export function saveSettings(settings: LocalSettings): void {
  localStorage.setItem(KEY, JSON.stringify(settings));
}
