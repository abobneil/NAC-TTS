import { useEffect, useState } from "react";

import { deleteJob, listJobs, type Job } from "../lib/api";
import { JobCard } from "../components/JobCard";

const ACTIVE_STATUSES = new Set(["queued", "processing"]);

export function LibraryPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    let timer: number | undefined;

    async function refresh() {
      try {
        const response = await listJobs();
        if (!mounted) {
          return;
        }
        setJobs(response.items);
        setError("");
        if (response.items.some((job) => ACTIVE_STATUSES.has(job.status))) {
          timer = window.setTimeout(refresh, 4000);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load jobs.");
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
  }, []);

  async function handleDelete(jobId: string) {
    await deleteJob(jobId);
    setJobs((current) => current.filter((job) => job.id !== jobId));
  }

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <p className="eyebrow">Library</p>
          <h2>Recent render jobs</h2>
        </div>
      </div>
      {error ? <p className="error-banner">{error}</p> : null}
      <div className="jobs-grid">
        {jobs.map((job) => (
          <JobCard key={job.id} job={job} onDelete={handleDelete} />
        ))}
        {jobs.length === 0 ? <div className="card empty-state">No jobs yet. Start from Convert.</div> : null}
      </div>
    </section>
  );
}
