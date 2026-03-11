import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { getCapabilities } from "../lib/api";
import { loadSettings, saveSettings } from "../lib/settings";

export function SettingsPage() {
  const defaults = loadSettings();
  const [voiceId, setVoiceId] = useState(defaults.voiceId);
  const [speakingRate, setSpeakingRate] = useState(defaults.speakingRate);
  const [voices, setVoices] = useState<{ id: string; label: string }[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getCapabilities().then((capabilities) => setVoices(capabilities.voices)).catch(() => undefined);
  }, []);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    saveSettings({ voiceId, speakingRate });
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  }

  return (
    <section className="stack">
      <form className="card stack" onSubmit={handleSubmit}>
        <div>
          <p className="eyebrow">Defaults</p>
          <h2>Saved mobile defaults</h2>
        </div>
        <label className="field">
          <span>Preferred Voice</span>
          <select value={voiceId} onChange={(event) => setVoiceId(event.target.value)}>
            {voices.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voice.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Preferred Speaking Rate</span>
          <input
            type="range"
            min="0.7"
            max="1.4"
            step="0.05"
            value={speakingRate}
            onChange={(event) => setSpeakingRate(Number(event.target.value))}
          />
          <small>{speakingRate.toFixed(2)}x</small>
        </label>
        <button type="submit" className="primary-button">
          Save Defaults
        </button>
        {saved ? <p className="success-banner">Saved to this device.</p> : null}
      </form>
    </section>
  );
}
