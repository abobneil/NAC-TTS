import { Link } from "react-router-dom";

import type { Job } from "../lib/api";
import { StatusPill } from "./StatusPill";

type Props = {
  job: Job;
  onDelete: (jobId: string) => Promise<void>;
};

export function JobCard({ job, onDelete }: Props) {
  return (
    <article className="card job-card">
      <div className="job-head">
        <div>
          <p className="eyebrow">{job.source_type.toUpperCase()}</p>
          <h3>{job.title}</h3>
        </div>
        <StatusPill status={job.status} />
      </div>
      <p className="muted">{job.progress_message ?? "Waiting"}</p>
      <div className="progress-track">
        <span style={{ width: `${job.progress}%` }} />
      </div>
      <div className="job-meta">
        <span>{job.char_count.toLocaleString()} chars</span>
        <span>{job.voice_id}</span>
      </div>
      <div className="card-actions">
        <Link to={`/jobs/${job.id}`} className="button-link">
          View
        </Link>
        {job.audio_url ? (
          <a href={job.audio_url} className="button-link" download>
            Download
          </a>
        ) : null}
        <button type="button" className="ghost-button" onClick={() => onDelete(job.id)}>
          Delete
        </button>
      </div>
    </article>
  );
}
