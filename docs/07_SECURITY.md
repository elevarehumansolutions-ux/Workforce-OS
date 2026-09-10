# Security

Consolidates security decisions already made across `08_DECISIONS.md`, `03_ARCHITECTURE.md`, and `05_API_DESIGN.md`, plus a few baseline items not yet written down anywhere.

## Multi-tenant isolation: two independent layers

- **Row-Level Security** (`08_DECISIONS.md`, 2026-09-04) is the database-enforced tenant boundary, `organization_id = current_setting('app.current_org_id')` on every tenant-scoped table. This is what defends against the single most common way multi-tenant SaaS actually gets breached, Broken Access Control (OWASP Top 10, #1 in the 2021 list), a forgotten `WHERE organization_id = ...` in application code.
- **Application-level authorization** handles everything RLS deliberately doesn't know about, department-level permissions, role checks, e.g. a Manager reading another department's tasks within the same org. See `03_ARCHITECTURE.md` request lifecycle for how both apply to the same query.

## The RLS-bypass role (added 2026-09-07, detail for the mention already in `08_DECISIONS.md`)

**Important distinction, easy to conflate:** `HR Administrator` and `Business Executive` are roles *inside one customer's organization* — they only ever need to see their own company's data, and RLS scoped to their own `organization_id` fully serves them. This section is not about them, nothing here changes their dashboards. It's about `System Administrator`, Elevare's own platform-level role, the only case that legitimately needs to see across every customer (e.g. billing status).

- A **separate Postgres role** (e.g. `elevare_platform_admin`) carries the `BYPASSRLS` attribute. The main application role, the one the FastAPI web app, Celery worker, and Celery Beat all use for every regular request, never has it, and never should. If the one role the whole product runs on could bypass RLS, RLS would provide zero protection against a bug in the application's own authorization code, the entire point of RLS is that it holds even when application code has a mistake in it.
- Its credential is stored separately from the main application database credential, never in the same `.env` the app containers read from.
- It's invoked only from standalone internal scripts (`scripts/admin/`), never exposed as an HTTP endpoint. No network-reachable path ever carries this level of access.
- Every invocation writes an entry to `audit_log` (actor, action, timestamp), the same accountability every other mutating action in the system already gets.

## Auth tokens

Short-lived JWT (org + role baked in) plus a refresh token that re-validates the live membership on every use. Full reasoning and the explicitly-deferred instant-revocation gap are in `03_ARCHITECTURE.md`, not repeated here.

## Passwords

`users.password_hash` stores a salted hash (bcrypt or argon2, not reversible encryption). Never logged, never returned in any API response, not even to the user who owns it.

## Injection

SQLAlchemy's parameterized queries are the default for all database access, no raw string-interpolated SQL. This is table stakes, not a design decision, but worth stating so it isn't accidentally violated by a future raw query for a "quick" report.

## Secrets

Never committed to the repo. `.env` (and any MCP config carrying live credentials, e.g. `.mcp.json`) stay in `.gitignore`. Any credential that's ever been exposed outside its intended storage, pasted in a chat, screenshotted, logged, gets rotated, not just relied on being "probably fine."

## Transport

HTTPS/TLS everywhere, no plaintext HTTP endpoint in any environment past local dev.

## Rate limiting

Login and refresh endpoints get basic rate limiting per IP/account (e.g. via `slowapi` or a reverse-proxy layer) to blunt credential-stuffing and brute-force attempts. Not built yet, flagged as an MVP-baseline item, not a Phase 2 nice-to-have, an unthrottled login endpoint is a real, immediate risk, not a hypothetical one.

## Data protection — flagged as needing legal review, not asserted as compliant

This product stores real personal data (employee names, contact info, employment details) for a Nigerian company. Nigeria's Data Protection Act (NDPA, 2023) governs this, but specifics of what it requires (data subject rights, breach notification timelines, cross-border transfer rules if hosting moves to Azure regions outside Nigeria) haven't been verified against current legal guidance. Same posture as the payroll statutory rates in `01_REQUIREMENTS.md` §9: don't treat anything here as settled without a professional (legal, in this case) sign-off before real customer data is stored.

## Audit Log (added to MVP scope 2026-09-06)

A dedicated `Audit Log` module, infrastructure category, same shape as Notifications: every domain module calls into it whenever it performs a mutating action, it calls out to nothing. See `02_SYSTEM_DESIGN.md` and `04_DATABASE.md` Cluster 9. Reasoning: unlike a deferrable feature, uninstrumented write paths can't be fixed retroactively, history not captured now is gone. The capture mechanism is MVP; a dedicated viewer screen for browsing that history is not required at the same time, the data isn't lost by building the screen later.

## Explicitly not built for MVP

- **Instant credential revocation** — see `03_ARCHITECTURE.md`, bounded by the access token's short expiry instead.
- **Audit log viewer screen** — the capture mechanism above is MVP; a UI for browsing recorded history can follow later without losing anything.
