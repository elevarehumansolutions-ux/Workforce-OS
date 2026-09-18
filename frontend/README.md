# Frontend

Reserved for Uche's Next.js app — this folder was previously a Vite/React
scaffold from M1 planning, before the actual frontend stack (Next.js,
client-rendered only, confirmed 2026-09-18, see `../docs/08_DECISIONS.md`)
was settled. Cleared out since none of that scaffold applies to Next.js's
project structure or tooling.

## Getting started

Initialize your own Next.js project directly in this folder (e.g.
`npx create-next-app@latest .`), commit it here.

## What you need to know about the API

Full endpoint list: `../docs/05_API_DESIGN.md`. Auth/token design:
`../docs/03_ARCHITECTURE.md`.

The short version, worth getting right from the start:

- **Every request needs `credentials: "include"`** (fetch) or the
  equivalent in whatever client you use — the refresh token lives in an
  `httpOnly` cookie, it won't be sent cross-origin without this. The
  backend's `CORSMiddleware` already has `allow_credentials=True` set to
  match.
- **Access token goes in `localStorage`** after login, sent as
  `Authorization: Bearer <token>` on every request. Short-lived (15 min);
  `POST /auth/refresh` (using the httpOnly cookie) gets you a new one.
- **Error responses are a flat JSON shape**, not nested:
  ```json
  { "code": "VALIDATION_ERROR", "status": "error", "message": "...", "details": [] }
  ```
  `details` is a list of `{field, message}` pairs, populated for validation
  errors (400s), empty otherwise.
- **CORS is origin-allowlisted**, not wildcard-open (required anyway —
  browsers refuse wildcard origin + credentials together). Send Emmanuel
  your deployed URL (Vercel preview/prod) once you have one, so it can be
  added to `CORS_ALLOWED_ORIGINS`.
- **Env var:** point at `NEXT_PUBLIC_API_BASE_URL` (Next.js only exposes
  `NEXT_PUBLIC_*`-prefixed vars to browser code) — see `.env.example`.

None of this needs a proxy or server-side data fetching — the browser talks
to the API directly, same as any regular client-side app.
