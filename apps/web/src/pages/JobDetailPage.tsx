import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { cancelJob, getJob, type Job } from "../lib/api";
import { StatusPill } from "../components/StatusPill";

const ACTIVE = new Set(["queued", "processing"]);

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    let timer: number | undefined;

    async function refresh() {
      try {
        const next = await getJob(jobId);
        if (!mounted) {
          return;
        }
        setJob(next);
        if (ACTIVE.has(next.status)) {
          timer = window.setTimeout(refresh, 4000);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load job.");
        }
      }
    }

    refresh();
    return () => {
      mounted = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [jobId]);

  async function handleCancel() {
    if (!job) {
      return;
    }
    const next = await cancelJob(job.id);
    setJob(next);
  }

  if (error) {
    return <p className="error-banner">{error}</p>;
  }

  if (!job) {
    return <div className="card">Loading job...</div>;
  }

  return (
    <section className="stack">
      <div className="card stack">
        <div className="job-head">
          <div>
            <p className="eyebrow">Job Detail</p>
            <h2>{job.title}</h2>
          </div>
          <StatusPill status={job.status} />
        </div>
        <p className="muted">{job.progress_message ?? "Waiting for worker."}</p>
        <div className="progress-track">
          <span style={{ width: `${job.progress}%` }} />
        </div>
        <div className="detail-grid">
          <div>
            <span className="detail-label">Voice</span>
            <strong>{job.voice_id}</strong>
          </div>
          <div>
            <span className="detail-label">Speed</span>
            <strong>{job.speaking_rate.toFixed(2)}x</strong>
          </div>
          <div>
            <span className="detail-label">Length</span>
            <strong>{job.char_count.toLocaleString()} chars</strong>
          </div>
          <div>
            <span className="detail-label">Pages</span>
            <strong>{job.page_count ?? "N/A"}</strong>
          </div>
        </div>
        {job.error_message ? <pre className="error-box">{job.error_message}</pre> : null}
        <div className="card-actions">
          <Link to="/library" className="button-link">
            Back to Library
          </Link>
          {ACTIVE.has(job.status) ? (
            <button type="button" className="ghost-button" onClick={handleCancel}>
              Cancel
            </button>
          ) : null}
          {job.audio_url ? (
            <>
              <audio controls src={job.audio_url} className="audio-player" />
              <a href={job.audio_url} download className="primary-button inline-button">
                Download MP3
              </a>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}
