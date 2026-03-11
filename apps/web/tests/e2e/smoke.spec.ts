import { expect, test } from "@playwright/test";

test.use({ serviceWorkers: "block" });

test("signs in, creates a job, waits for completion, and downloads the MP3", async ({ page }) => {
  let authenticated = false;
  let detailPollCount = 0;
  const context = page.context();

  await context.route("**/api/v1/auth/session", async (route) => {
    await route.fulfill({ json: { authenticated } });
  });

  await context.route("**/api/v1/auth/login", async (route) => {
    authenticated = true;
    await route.fulfill({ status: 204 });
  });

  await context.route("**/api/v1/auth/logout", async (route) => {
    authenticated = false;
    await route.fulfill({ status: 204 });
  });

  await context.route("**/api/v1/capabilities", async (route) => {
    if (!authenticated) {
      await route.fulfill({ status: 401, json: { detail: "Authentication required." } });
      return;
    }

    await route.fulfill({
      json: {
        device: "cpu",
        model_id: "test-model",
        voices: [{ id: "af_heart", label: "AF Heart" }],
        formats: ["mp3"],
        limits: { max_upload_mb: 25, max_pages: 100, max_chars: 80000 },
        sample_rate: 24000,
      },
    });
  });

  await context.route("**/api/v1/jobs?limit=50", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            id: "job-1",
            title: "Integration Job",
            source_type: "text",
            source_filename: null,
            status: detailPollCount > 0 ? "completed" : "processing",
            progress: detailPollCount > 0 ? 100 : 45,
            progress_message: detailPollCount > 0 ? "Completed" : "Synthesizing chunk 1/2",
            voice_id: "af_heart",
            speaking_rate: 1,
            char_count: 24,
            attempt_count: 1,
            page_count: null,
            duration_seconds: detailPollCount > 0 ? 1.25 : null,
            error_message: null,
            created_at: "2026-03-11T00:00:00Z",
            started_at: "2026-03-11T00:00:01Z",
            completed_at: detailPollCount > 0 ? "2026-03-11T00:00:02Z" : null,
            audio_url: detailPollCount > 0 ? "/api/v1/jobs/job-1/file" : null,
          },
        ],
        total: 1,
      },
    });
  });

  await context.route("**/api/v1/jobs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }

    await route.fulfill({ status: 202, json: { job_id: "job-1", status: "queued" } });
  });

  await context.route("**/api/v1/jobs/job-1", async (route) => {
    detailPollCount += 1;
    const completed = detailPollCount > 1;
    await route.fulfill({
      json: {
        id: "job-1",
        title: "Integration Job",
        source_type: "text",
        source_filename: null,
        status: completed ? "completed" : "processing",
        progress: completed ? 100 : 45,
        progress_message: completed ? "Completed" : "Synthesizing chunk 1/2",
        voice_id: "af_heart",
        speaking_rate: 1,
        char_count: 24,
        attempt_count: 1,
        page_count: null,
        duration_seconds: completed ? 1.25 : null,
        error_message: null,
        created_at: "2026-03-11T00:00:00Z",
        started_at: "2026-03-11T00:00:01Z",
        completed_at: completed ? "2026-03-11T00:00:02Z" : null,
        audio_url: completed ? "/api/v1/jobs/job-1/file" : null,
      },
    });
  });

  await context.route("**/api/v1/jobs/job-1/file", async (route) => {
    await route.fulfill({
      status: 200,
      body: Buffer.from("fake-mp3"),
      headers: {
        "content-type": "audio/mpeg",
        "content-disposition": 'attachment; filename="Integration Job.mp3"',
      },
    });
  });

  await page.goto("/");

  await expect(page.getByText("Protected Access")).toBeVisible();
  await page.getByLabel("Access Token").fill("test-token");
  await page.getByRole("button", { name: "Unlock App" }).click();

  await expect(page.getByRole("heading", { name: "Queue narration from your phone or desktop." })).toBeVisible();
  await page.getByLabel("Title").fill("Integration Job");
  await page.getByLabel("Text").fill("Hello integration coverage.");
  await page.getByRole("button", { name: "Create MP3 Job" }).click();

  await expect(page).toHaveURL(/\/jobs\/job-1$/);
  await expect(page.getByRole("heading", { name: "Integration Job" })).toBeVisible();
  await expect(page.locator(".status-pill")).toHaveText(/completed/i);

  await expect(page.getByRole("link", { name: "Download MP3" })).toHaveAttribute("href", "/api/v1/jobs/job-1/file");
  const download = await page.evaluate(async () => {
    const response = await fetch("/api/v1/jobs/job-1/file");
    return {
      status: response.status,
      body: Array.from(new Uint8Array(await response.arrayBuffer())),
    };
  });
  expect(download.status).toBe(200);
  expect(download.body).toEqual(Array.from(Buffer.from("fake-mp3")));
});
