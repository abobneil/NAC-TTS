export type VoiceOption = {
  id: string;
  label: string;
};

export type Capabilities = {
  device: string;
  model_id: string;
  voices: VoiceOption[];
  formats: string[];
  sample_rate: number;
  limits: {
    max_upload_mb: number;
    max_pages: number;
    max_chars: number;
  };
};

export type Job = {
  id: string;
  title: string;
  source_type: string;
  source_filename: string | null;
  status: string;
  progress: number;
  progress_message: string | null;
  voice_id: string;
  speaking_rate: number;
  char_count: number;
  page_count: number | null;
  duration_seconds: number | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  audio_url: string | null;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const AUTH_REQUIRED_EVENT = "nac-tts-auth-required";

const JSON_HEADERS = {
  Accept: "application/json",
};

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // Fall back to the default detail string.
    }
    if (response.status === 401) {
      window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
    }
    throw new ApiError(response.status, detail);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

type RequestInitWithAuth = RequestInit & {
  headers?: HeadersInit;
};

async function request<T>(input: string, init?: RequestInitWithAuth): Promise<T> {
  return handle(
    await fetch(input, {
      credentials: "same-origin",
      ...init,
    }),
  );
}

export async function getSession(): Promise<{ authenticated: boolean }> {
  return request("/api/v1/auth/session", { headers: JSON_HEADERS });
}

export async function login(accessToken: string): Promise<void> {
  return request("/api/v1/auth/login", {
    method: "POST",
    headers: {
      ...JSON_HEADERS,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ access_token: accessToken }),
  });
}

export async function logout(): Promise<void> {
  return request("/api/v1/auth/logout", {
    method: "POST",
    headers: JSON_HEADERS,
  });
}

export async function getCapabilities(): Promise<Capabilities> {
  return request("/api/v1/capabilities", { headers: JSON_HEADERS });
}

export async function createJob(form: FormData): Promise<{ job_id: string; status: string }> {
  return request("/api/v1/jobs", {
      method: "POST",
      body: form,
    });
}

export async function listJobs(): Promise<{ items: Job[]; total: number }> {
  return request("/api/v1/jobs?limit=50", { headers: JSON_HEADERS });
}

export async function getJob(jobId: string): Promise<Job> {
  return request(`/api/v1/jobs/${jobId}`, { headers: JSON_HEADERS });
}

export async function cancelJob(jobId: string): Promise<Job> {
  return request(`/api/v1/jobs/${jobId}/cancel`, {
      method: "POST",
      headers: JSON_HEADERS,
    });
}

export async function deleteJob(jobId: string): Promise<void> {
  return request(`/api/v1/jobs/${jobId}`, {
      method: "DELETE",
      headers: JSON_HEADERS,
    });
}
