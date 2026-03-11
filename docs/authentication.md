# Authentication and Remote Access

NAC-TTS now expects a shared deployment access token for all non-health API usage.

## Auth model

- Browser users unlock the app by submitting `APP_ACCESS_TOKEN` to `POST /api/v1/auth/login`.
- A successful login creates a signed session cookie. The frontend uses that cookie for normal API calls, audio playback, and file downloads.
- Non-browser clients can skip the login flow and send `Authorization: Bearer <APP_ACCESS_TOKEN>` on protected `/api/v1/*` routes.
- `GET /api/v1/health` stays public for liveness checks.

## Required environment variables

- `APP_ACCESS_TOKEN`: Shared secret required for browser login and bearer-token API access.
- `AUTH_SESSION_SECRET`: Signing secret for the session cookie. Use a different random value from the access token.
- `AUTH_COOKIE_SECURE`: Set to `true` when serving the app over HTTPS. Leave `false` only for local HTTP development.
- `AUTH_SESSION_TTL_SECONDS`: Session lifetime in seconds.
- `CORS_ALLOW_ORIGINS`: Comma-separated browser origins allowed to call the API.

## Recommended values

- Generate both secrets with a password manager or a command such as `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- Use explicit origins such as `https://tts.example.com`.
- Do not keep localhost origins in `CORS_ALLOW_ORIGINS` for an internet-facing deployment.
- `CORS_ALLOW_ORIGINS` must be a comma-separated list of exact origins only. Do not include paths, query strings, fragments, or `*`.

## Cloudflare Tunnel guidance

- Publish only the `caddy` service through Cloudflare Tunnel.
- Put Cloudflare Access in front of the tunnel hostname so the static app and API are both gated before requests reach your origin.
- Keep the in-app token enabled even when Cloudflare Access is used. Cloudflare Access protects the edge path; the app token still protects the API if the origin is ever reached another way.
- When the public hostname uses HTTPS, set `AUTH_COOKIE_SECURE=true`.
- Set `CORS_ALLOW_ORIGINS` to the exact public app origin, for example `https://tts.example.com`.

## Verification

1. Start the stack with non-placeholder values for `APP_ACCESS_TOKEN` and `AUTH_SESSION_SECRET`.
2. Confirm `GET /api/v1/health` returns `200`.
3. Confirm `GET /api/v1/jobs` returns `401` without a session cookie or bearer token.
4. Sign in through the web UI and create a test job.
5. Confirm audio playback and MP3 download both work after login.
6. If using Cloudflare Tunnel, verify the hostname is also protected by a Cloudflare Access policy.
