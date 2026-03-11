import { useEffect, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { createJob, getCapabilities, type Capabilities } from "../lib/api";
import { loadSettings } from "../lib/settings";

export function ConvertPage() {
  const navigate = useNavigate();
  const defaults = loadSettings();
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [sourceType, setSourceType] = useState<"text" | "pdf">("text");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [voiceId, setVoiceId] = useState(defaults.voiceId);
  const [speakingRate, setSpeakingRate] = useState(defaults.speakingRate);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getCapabilities().then(setCapabilities).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!capabilities) {
      return;
    }
    if (!capabilities.voices.some((voice) => voice.id === voiceId)) {
      setVoiceId(capabilities.voices[0]?.id ?? "af_heart");
    }
  }, [capabilities, voiceId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("title", title);
      form.append("source_type", sourceType);
      form.append("voice_id", voiceId);
      form.append("speaking_rate", String(speakingRate));
      form.append("output_format", "mp3");
      if (sourceType === "text") {
        form.append("text", text);
      } else if (file) {
        form.append("file", file);
      }
      const result = await createJob(form);
      navigate(`/jobs/${result.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job.");
    } finally {
      setBusy(false);
    }
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  return (
    <section className="stack">
      <div className="hero card">
        <div>
          <p className="eyebrow">Pasted notes to commute-ready audio</p>
          <h2>Queue narration from your phone or desktop.</h2>
        </div>
        <p className="muted">
          The backend stays on your own machine. This PWA just packages text or PDFs and pulls finished MP3 files back down.
        </p>
      </div>
      <form className="card stack" onSubmit={handleSubmit}>
        <div className="segment-control">
          <button type="button" className={sourceType === "text" ? "active" : ""} onClick={() => setSourceType("text")}>
            Text
          </button>
          <button type="button" className={sourceType === "pdf" ? "active" : ""} onClick={() => setSourceType("pdf")}>
            PDF
          </button>
        </div>
        <label className="field">
          <span>Title</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Morning reading queue" />
        </label>
        {sourceType === "text" ? (
          <label className="field">
            <span>Text</span>
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Paste the article, memo, or notes you want narrated."
              rows={14}
            />
          </label>
        ) : (
          <label className="field">
            <span>PDF Upload</span>
            <input type="file" accept="application/pdf" onChange={handleFile} />
          </label>
        )}
        <div className="grid two-up">
          <label className="field">
            <span>Voice</span>
            <select value={voiceId} onChange={(event) => setVoiceId(event.target.value)}>
              {capabilities?.voices.map((voice) => (
                <option key={voice.id} value={voice.id}>
                  {voice.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Speaking Rate</span>
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
        </div>
        {capabilities ? (
          <p className="muted">
            Model: {capabilities.model_id} on {capabilities.device.toUpperCase()} | Limit {capabilities.limits.max_chars.toLocaleString()} chars
          </p>
        ) : null}
        {error ? <p className="error-banner">{error}</p> : null}
        <button type="submit" className="primary-button" disabled={busy}>
          {busy ? "Submitting..." : "Create MP3 Job"}
        </button>
      </form>
    </section>
  );
}
