# Architecture

Built incrementally, same approach as `04_DATABASE.md` and `02_SYSTEM_DESIGN.md`. This doc covers how the modules from `02_SYSTEM_DESIGN.md` actually get wired together at runtime, starting with the request lifecycle.

## Request Lifecycle

Every request that touches an RLS-protected table goes through the same sequence, in this order, before any module's business logic runs:

1. **Authenticate.** Validate the JWT (access token). If it's missing, expired, or malformed, reject before anything else happens.
2. **Resolve org + role.** The access token carries `organization_id` and `role` as claims, baked in at issuance (see "Auth Tokens" below) — no database lookup needed on this step for most requests.
3. **Set the tenant context.** `SET LOCAL app.current_org_id = <organization_id from the token>`, inside the current transaction, in a single shared FastAPI dependency (per `08_DECISIONS.md`, 2026-09-04). `SET LOCAL`, not plain `SET`, because pooled connections are reused across different tenants' requests.
4. **Run the query.** The owning module's service issues its query with whatever business-level filter applies (e.g. Task module filtering `WHERE department_id = :department_id` to enforce "a Manager only sees their own department"). Postgres Row-Level Security invisibly ANDs `organization_id = current_setting('app.current_org_id')` onto that same query, in the same round trip. This is one combined query, not a fetch-everything-then-filter-in-code pass, that would mean pulling every row in the org into application memory just to discard most of it.

**Two separate authorization layers, doing two different jobs, both required:**
- **Row-Level Security** (step 3/4) blocks cross-organization access. It knows nothing about departments, roles, or managers, it only ever checks "does this row belong to the org this session is operating as." It's a deliberately dumb, uniform backstop that never has to know a business rule, present on every RLS-protected table the same way.
- **Application-level authorization** (part of step 4, written into each module's service) blocks in-tenant access that RLS can't see, e.g. a Manager in one department reading another department's tasks, still the same organization, so RLS alone would allow it. This lives in code, per module, because it depends on business rules RLS is deliberately kept ignorant of.

## Auth Tokens

**Short-lived access token + refresh token, re-validated against the live `Membership` on each refresh.**

- The JWT (access token) bakes in `organization_id` and `role` at issuance, so almost every request pays no lookup cost to know "who is this, what can they do here."
- It expires quickly (on the order of 15 minutes). A separate, longer-lived refresh token is used to obtain a new access token when it expires.
- **Every refresh re-queries the `memberships` table.** This is what makes a revoked or changed membership actually take effect, not immediately, but within one token lifetime.

**Why baked-in claims with a short expiry, instead of a fresh lookup on every request:** a pure "look up org/role fresh every time" design has zero staleness (a revoked user is blocked on their very next request) but costs a database query on every single request. A pure "bake it in, long-lived token" design has zero per-request cost but means a fired employee, or a Manager who just got demoted, keeps acting with their old permissions until the token expires, potentially hours or days. Short expiry plus a refresh-time revalidation is the standard middle ground: near-zero overhead on almost every request, in exchange for a small, bounded window (one token lifetime, ~15 minutes) before a permission change fully takes effect.

**Storage, decided 2026-09-07:** refresh token as an `httpOnly` cookie (`Secure=true` in production, `Secure=false` in local dev, since browsers refuse `Secure` cookies over plain HTTP, and dev runs on HTTP), unreadable by JavaScript, meaningfully reducing what an XSS bug could steal. Access token in `localStorage`, readable by JS if this app ever has an XSS bug, but bounded by its own short expiry, a stolen one is only useful for whatever's left of its 15 minutes. Same pattern already proven in production on Elevare's recruitment platform.

## CORS

`CORSMiddleware` configured with an explicit allow-list of real frontend origins (dev, staging, prod), never a wildcard. `allow_credentials=True`, required for the httpOnly refresh cookie to be sent cross-origin, and paired naturally with the explicit origin list since browsers refuse wildcard-origin-plus-credentials outright. `allow_methods`/`allow_headers` scoped to what's actually used, not wildcarded either.

**Explicitly not built for MVP: instant revocation.** A stricter guarantee, access cut off the same second a membership is revoked, would need something heavier on top of this, e.g. a fast revocation check (a Redis lookup) on every request, not just at refresh time. Nothing in `01_REQUIREMENTS.md` calls for that guarantee today. Flagged here deliberately so it isn't forgotten: revisit if an enterprise customer ever makes instant revocation a contractual or compliance requirement, don't build it speculatively now.

## Background Jobs

Two different flavors of Celery task, used for different reasons:

- **Event-triggered** — a specific action in the app enqueues a job right at that moment. Example: after `Org Structure`'s service saves a department as critical, or `OKR`'s service saves a new objective, it calls `ai_suggestions_service.request_suggestions(...)`, a normal service call, respecting the module-boundary rule. It's *inside* `AI Suggestions`' own service that the decision to call `.delay()` on its LLM-generation task lives, the calling module never needs to know that detail exists.
- **Scheduled** (Celery Beat) — runs on a repeating timer regardless of any specific action. Example: the Overdue check. Whether a task has crossed its `due_at` is a derived fact (see `04_DATABASE.md` Cluster 6), but the notification that has to fire "the moment" it becomes overdue (`01_REQUIREMENTS.md` §6) needs something actively scanning for newly-overdue tasks on a timer, there's no user action to hang that check off of.

**Why background jobs at all, instead of doing this inline in the request:** an LLM call takes real time, a second or more. Making an HR Administrator's browser wait on that before confirming "department saved" is a bad tradeoff for an otherwise-instant action, and it means an unrelated LLM failure or timeout could take down the save operation with it. Pushing it to a background job lets the request return immediately; the result shows up once the job finishes, and a failure there is isolated and retryable.

**What Celery actually needs to run:** a message broker sits between the process enqueueing a job (the web app) and the process executing it (a worker). `.delay()` pushes the job onto the broker; a worker pulls it off and runs it. Redis is that broker here, standard pairing with Celery, no need for anything heavier (e.g. RabbitMQ) at this scale.

## Infrastructure Topology & Scaling

Five distinct processes have to run at once for the system to function: the **FastAPI web app**, **PostgreSQL**, **Redis**, one or more **Celery workers**, and **Celery Beat**. Each has a different scaling profile, and getting this wrong for Celery Beat specifically is a real, common mistake, not a hypothetical:

| Process | Scaling |
|---|---|
| FastAPI web app | Horizontal, freely. Stateless, auth is a JWT, tenant context is set fresh per request/transaction, so no instance holds anything another instance needs to know about. Standard load-balanced setup. |
| PostgreSQL | Vertical first. One writable primary for a long time, more CPU/RAM as load grows. Read replicas are a real horizontal option later, only worth adding once read load is an actual bottleneck, not built ahead of need. |
| Redis | Single instance, for a very long time. A single instance handles far more broker throughput than this product will produce for years; clustering solves a scale problem not relevant yet. |
| Celery worker | Horizontal, freely, this is the point of it. More workers, even across machines, pull from the same Redis queue and process jobs in parallel. |
| Celery Beat | **Exactly one instance, always, by design, not by current lack of need.** Beat fires scheduled jobs on a timer with no coordination between copies of itself. Two Beat processes means the overdue check, and its notifications, fire twice as often, duplicated. This isn't solved by "just don't need to scale it yet", running more than one is a bug regardless of scale. |

## Routing

Each module owns a `router.py`, a FastAPI `APIRouter`. The main app aggregates all of them with `app.include_router(module_router, prefix="/...")`, one line per module. Incoming requests are matched to a module purely by URL prefix.

## Deployment: one Dockerfile, not three

The FastAPI web app, the Celery worker, and Celery Beat are the exact same codebase and dependency set, they're all part of one modular monolith. **One Docker image is built from one Dockerfile**, and three separate containers run from that same image, distinguished only by the startup command:

- `uvicorn app.main:app` → the web app container
- `celery -A app worker` → the worker container
- `celery -A app beat` → the beat container

**Why one image instead of three:** with genuinely identical code and dependencies across all three roles, three separate Dockerfiles would mean three times the build and maintenance work for no real difference in what ships, and a real risk of drift, a dependency update applied to one Dockerfile and forgotten in the other two, the same class of problem as logic duplicated across unrelated files, just showing up in infrastructure config instead of application code.

**The real tradeoff, acknowledged rather than ignored:** one shared image means all three redeploy together, even when a change only touches one of them, a Celery worker mid-job just gets its task requeued when this happens, which Celery handles gracefully, so this is a minor cost, not a real production risk at this team size and scale. It also means the three can't have independently pinned dependency versions. If either of those ever becomes an actual, measured problem, that's the trigger to split into separate Dockerfiles, not something to build ahead of now.
