# Row-Level Security, Explained Simply

A plain-language reference for the RLS policies on `organizations` and
`memberships`. Come back here whenever the SQL stops making sense — it's
written for a reader who only remembers "RLS restricts what rows you can
see," nothing more.

---

## 1. What RLS actually does, in one paragraph

Postgres can attach an invisible filter to a table. Every time anyone reads
from, writes to, or deletes from that table, Postgres silently checks a rule
first, and only lets the operation through if the rule says yes. The rule
usually compares a column on the row (like `organization_id`) against a
small piece of information the app told the database earlier in the same
request — think of it as a sticky note left on the current database
connection, e.g. "you're acting as this company right now." No sticky note,
no match, no rows.

---

## 2. Who is even subject to these rules — roles, superusers, and `BYPASSRLS`

Everything in §1 has one silent precondition: it only applies to *some*
database connections. This section is about that precondition — because a
real bug in this project lived entirely inside it, invisibly, for a while.

### What a "role" is

Every time anything connects to Postgres, it connects *as* someone — a
"role" (Postgres's word for a login identity, roughly like a username).
Every permission Postgres ever checks, RLS included, is checked against
whichever role the current connection is using.

### Superusers skip everything, including RLS

A role can be marked `SUPERUSER`. A superuser role is allowed to do
*literally anything* — including reading and writing every row of every
table, no matter what RLS policies say. RLS policies aren't even consulted
for a superuser's queries; they're skipped entirely, as if they didn't
exist. This isn't a bug or a special case to work around — it's what
"superuser" means by definition, the same way `root` on a Linux box isn't
stopped by file permissions.

(There's also a narrower, separate switch called `BYPASSRLS` — a role can
have *just* that, without being a full superuser, and it has the same
effect: RLS is skipped for it. Superusers automatically have it too. Not
relevant to what went wrong here, but worth knowing it exists as its own
thing.)

### Every fresh Postgres cluster has exactly one superuser — always

This is the part that caused the most back-and-forth: **a brand-new
Postgres cluster is required to have at least one superuser.** That's not a
Docker convention or something this project chose — it's how Postgres's own
initialization step (`initdb`) works, full stop. There's no configuration
that results in a fresh cluster with zero superusers.

The official `postgres` Docker image (`postgres:16-alpine`, what
`docker-compose.yml` uses) reads one specific environment variable —
`POSTGRES_USER` — to decide what to *name* that unavoidable first superuser
and what password to give it. If `POSTGRES_USER` isn't set, the image
doesn't skip creating a superuser — it just falls back to naming it
`postgres` instead. The variable controls the name. It does not control
whether a superuser gets created; that part isn't optional.

### What actually went wrong here

`docker-compose.yml` has:

```yaml
db:
  image: postgres:16-alpine
  environment:
    POSTGRES_USER: elevare
```

So `elevare` is a superuser — correctly, unavoidably, nothing to fix there.
The actual mistake was one step later: `.env`'s `DATABASE_URL` (the
connection string the live FastAPI app and both Celery processes use for
*all* their normal traffic) also pointed at `elevare`. So every request the
app ever handled ran as a superuser — meaning every RLS policy in this
document was installed correctly, syntactically fine, and **completely
skipped**, the whole time, for real traffic. Nothing was checking them.
Every earlier "proof" that RLS worked was actually just the app's own
`WHERE user_id = ...`-style code happening to filter correctly on its own —
not Postgres enforcing anything.

### The fix: a second, ordinary role, used only for live traffic

`backend/scripts/db/provision_app_role.sql` creates `elevare_app` — an
*ordinary* role: no `SUPERUSER`, no `BYPASSRLS`. It's granted only what the
app actually needs (`SELECT`/`INSERT`/`UPDATE`/`DELETE` on tables), nothing
schema-altering. `.env`'s `DATABASE_URL` now points at `elevare_app`
instead — so RLS policies are, for the first time, actually being checked
for real app requests. `elevare` (the superuser) still exists — it has to,
per the rule above — but now it's only used for schema migrations
(`MIGRATION_DATABASE_URL`, read by `alembic/env.py`), which genuinely need
superuser-level DDL privileges (`CREATE TABLE`, `ALTER TABLE`) that
`elevare_app` deliberately doesn't have.

| Role | Superuser? | `BYPASSRLS`? | Used for |
|---|---|---|---|
| `elevare` | Yes (required by Postgres itself) | Yes (automatic) | Alembic migrations only |
| `elevare_app` | No | No | Live app traffic (FastAPI, Celery worker, Celery Beat) — RLS genuinely enforced |

### Dead ends worth naming, since they came up

- **"What if I rename the `POSTGRES_USER` variable to something else, like
  `DB_USER`?"** The Postgres image only recognizes the exact name
  `POSTGRES_USER` — it's hardcoded into the image's own startup script.
  Anything named differently is invisible to it; the image would just fall
  back to its default (`postgres`) instead. You'd still get exactly one
  superuser, just under a different, now-mismatched name — nothing about
  the actual problem changes.
- **"What if I delete the database volume and all migration files, then
  start fresh?"** Doesn't matter — "a fresh cluster always gets exactly one
  superuser" applies on *every* `initdb` run, not just the first one ever.
  A clean slate still produces a superuser; that's the one thing a clean
  slate can't avoid.
- **"What if I rebuild the Docker project?"** `docker-compose.yml`'s `db`
  service uses `image: postgres:16-alpine` — a prebuilt image pulled as-is,
  not built from a `Dockerfile` in this repo (unlike `api`/`celery_worker`/
  `celery_beat`, which do have a `build:` block). There's nothing to
  rebuild for `db` at all.

The one fact underneath all three: **a superuser existing was never the
bug.** Postgres requires one, unconditionally. The bug was the live app
*connecting as* that superuser instead of a separate, restricted identity —
and that's exactly what `elevare_app` fixes, regardless of what the
superuser is named or how the volume/containers get reset.

---

## 3. The problem these two policies solve

The sticky note ("which company am I acting as") normally gets written once
someone is logged in and has picked a company. But three moments in this
app happen **before** that sticky note can possibly exist:

1. **Creating a brand-new organization** (registration) — the org doesn't
   exist yet, so there's no id to put on a sticky note.
2. **Creating the founding membership row** (also registration) — same
   problem, one table over.
3. **Looking up which companies someone belongs to** (login) — this is the
   *point* of the lookup; you can't have the answer before you've asked.

A plain RLS policy (just "show me rows matching my company sticky note")
would block all three of these, forever, because none of them have a
company sticky note yet. Each policy below carves out one narrow,
deliberate exception for exactly this — never a blanket "if nothing is set,
show everything," because that would be a serious security hole (any
request that forgets to set a sticky note would suddenly see every
customer's data instead of none of it).

---

## 4. Syntax primer — the building blocks, explained once

Both policies below are built from the same handful of pieces. Learn these
once, and both policies read the same way.

### `current_setting('app.current_org_id', true)`

A Postgres function that reads back a sticky note left earlier in the same
database connection (written by a line like
`SET LOCAL app.current_org_id = ...` or `SELECT set_config('app.current_org_id', ..., true)`
somewhere in the Python code). The second argument, `true`, means "don't
error if nothing was ever written — just hand back an empty result."

**Gotcha:** if nothing was ever set, this returns an **empty string** (`''`),
not a real SQL `NULL`.

### `NULLIF(x, '')`

Compares two values. If they're equal, returns `NULL`. Otherwise returns `x`
unchanged. `NULLIF(current_setting(...), '')` exists purely to translate
"got an empty string back" into "got a real `NULL` back" — because the next
step needs a real `NULL` to work.

### `::uuid`

A type cast. `current_setting` always returns plain text; the columns being
compared against (`id`, `organization_id`, `user_id`) are UUID columns.
`::uuid` converts the text into a real UUID so the comparison is valid.

### Why `= NULL` means "no rows," not "an error"

In SQL, comparing anything to `NULL` with `=` never returns `true` or
`false` — it returns `unknown`. A row is only included when the result is
`true`. So when the sticky note is a real `NULL` (nothing was ever set),
every `column = NULL` comparison comes back `unknown`, and **every row is
excluded**. This one fact is the entire mechanism behind "no context yet =
see nothing." Nobody coded that behavior explicitly — it falls straight out
of how `NULL` comparisons work.

### `USING (...)` vs `WITH CHECK (...)`

A policy can carry two separate rules:
- **`USING`** — governs *reading*: `SELECT`, `DELETE`, and (for `UPDATE`)
  which existing rows you're even allowed to touch.
- **`WITH CHECK`** — governs *writing*: `INSERT`, and (for `UPDATE`) whether
  the new version of the row is still valid.

They can have completely different conditions, which is exactly what makes
the org-creation bootstrap exception possible: reads stay strict, writes get
one narrow exception.

### Why `current_setting(...)` gets called twice in the same `WITH CHECK`

Both `WITH CHECK` clauses below read the org sticky note **twice** in one
expression:

```sql
WITH CHECK (
    NULLIF(current_setting('app.current_org_id', true), '') IS NULL
    OR id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
)
```

This is still only **one** sticky note — it's just being asked two
different questions about it, joined by `OR`:
- **Question 1:** *"Is the note completely empty — was nothing ever
  written?"* (`... IS NULL`, on its own, nothing being compared).
- **Question 2:** *"If there is a note, does it match this row?"*
  (`id = ...`, comparing the note's value to the row).

A SQL policy condition is one boolean expression, not a sequence of steps —
there's no variable to compute the note's value once and reuse it under a
name, the way `note = read_note(); if note is None or note == row.id:`
would work in Python. So the lookup gets spelled out again everywhere it's
needed. Nothing changes the note in between the two calls, so both are
guaranteed to read back the exact same value.

---

## 5. Policy 1 — `organizations`

```sql
CREATE POLICY tenant_isolation ON organizations
USING (
    id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
    OR (
        NULLIF(current_setting('app.current_org_id', true), '') IS NULL
        AND id IN (
            SELECT organization_id FROM memberships
            WHERE user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        )
    )
)
WITH CHECK (
    NULLIF(current_setting('app.current_org_id', true), '') IS NULL
    OR id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
)
```

**Reading (`USING`), updated 2026-09-18 — this now has a bootstrap branch too, not just `memberships`.** Originally this was just `id = <org sticky note>`, no exception at all. That broke `GET /me` for any user with more than one membership: RLS only ever allows seeing one org's row at a time, so there was no way to fetch every organization a multi-membership user belongs to for the frontend's org-switcher. The second branch mirrors `memberships`' own bootstrap pattern: when no org has been chosen yet, and the session is identified by `app.current_user_id` instead, a row is visible if it's an organization that user genuinely has a membership in, found via a subquery against `memberships` (itself already RLS-protected the same bootstrap way, so this can't leak anything, it only ever returns orgs belonging to the identified user).

**Writing (`WITH CHECK`):** unchanged. Allowed if *either*:
- there is no sticky note at all right now (the org-creation moment), **or**
- the row being written matches the org you're already acting as (every
  normal case, once someone's logged in).

Only `USING` got the broader exception — writes stay narrow, so the bootstrap branch only ever grants *read* access to your own orgs, never a way to write to one you haven't explicitly selected as `current_org_id`.

### Worked example

| Moment | `app.current_org_id` | `app.current_user_id` | Trying to... | Result |
|---|---|---|---|---|
| Ada is registering a brand-new company | never set | not set | `INSERT` the new org row | **Allowed** — `WITH CHECK`'s first branch (`IS NULL`) is true |
| Ada, now logged in as Org A, requests `GET /organizations/{Org B's id}` | set to Org A's id | not set this request | `SELECT` Org B's row | **Blocked** — first branch fails (`id (Org B) ≠ current_org_id (Org A)`), second branch fails too (`current_org_id` isn't null) |
| Ada, logged in as Org A, requests her own org | set to Org A's id | not set this request | `SELECT` Org A's row | **Allowed** — first branch, `id = current_org_id` is `true` |
| Ada calls `GET /me`, belongs to Org A and Org C | never set this request | set to Ada's id | `SELECT` every organization | **Allowed for Org A and Org C, blocked for everything else** — second branch: no org chosen yet, and each of Org A/Org C's `id` is in the subquery result for Ada's `user_id`; Org B (Ada isn't a member) is not |

### Why `login()` and `get_me()` explicitly clear `app.current_org_id` first, not just assume it's unset (added 2026-09-18)

Both bootstrap flows used to just start setting `app.current_user_id`, trusting `app.current_org_id` had never been set on this connection. True for a genuinely fresh connection in production (each request gets its own transaction, and `SET LOCAL`'s scope ends when that transaction does) — but that was an *assumption*, never enforced. A test environment binding one shared connection/transaction across several sequential requests exposed exactly the case where a prior request's `app.current_org_id` was still set when a later `login()` call ran, silently breaking that login's org resolution against a stale value. Both methods now explicitly reset `app.current_org_id` to empty before proceeding, rather than relying on it never having been touched.

### Why `login()` then re-sets `app.current_org_id` to the *real* value once it's known

Picking which org to log into happens under bootstrap (user-id-only) context, where the subquery branch above is what makes any organization visible at all. Once `login()` picks the actual membership, it explicitly runs `set_config('app.current_org_id', <that org's id>, true)` before fetching the `Organization` row it returns — it does not just reuse whatever got eager-loaded during the bootstrap-context query (that eager load only worked *because* of the bootstrap branch; the row wasn't actually visible as "your current org" yet). Setting the real value afterward means every later operation in the same request also sees the correct, real tenant context, not a leftover bootstrap one.

---

## 6. Policy 2 — `memberships`

```sql
CREATE POLICY tenant_isolation ON memberships
USING (
    organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
    OR (
        NULLIF(current_setting('app.current_org_id', true), '') IS NULL
        AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    )
)
WITH CHECK (
    NULLIF(current_setting('app.current_org_id', true), '') IS NULL
    OR organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
)
```

**Writing (`WITH CHECK`):** identical shape to organizations' — swap `id`
for `organization_id`. Same two branches, same reasoning (registration's
founding-membership insert needs the same bootstrap exception).

**Reading (`USING`):** this is the one with an extra piece. Read it as
`X OR (Y AND Z)`:

- **`X`** — `organization_id = <org sticky note>`. The normal case, exactly
  like organizations' rule. Handles every ordinary request once someone has
  picked a company.
- **`Y`** — `<org sticky note> IS NULL`. "No company has been chosen yet."
- **`Z`** — `user_id = <a SECOND, different sticky note: app.current_user_id>`.
  This row's `user_id` matches the person currently logging in.

`(Y AND Z)` only ever turns on when **both** are true at once: no company
chosen yet, **and** this row belongs to the specific person who just logged
in. `X OR (Y AND Z)` means: show this row if it's your company's (normal
case), or — only when you have no company at all yet — if it's your own
row by user id. Never "show everyone's."

### Who sets `app.current_user_id`, and when

Only one place: `AuthService.login()`, in `backend/app/modules/auth/service.py`,
right after the password check succeeds and right before looking up which
companies this person belongs to:

```python
await self._db.execute(
    text("SELECT set_config('app.current_user_id', :user_id, true)"),
    {"user_id": str(user.id)},
)
memberships = await self._membership_service.get_user_memberships(user.id)
```

It is **not** set anywhere else — not at registration, not on every
request. See §6 for why.

### Worked example

| Moment | `app.current_org_id` | `app.current_user_id` | Trying to... | Result |
|---|---|---|---|---|
| Login, right after password check | never set | set to Ada's id | `SELECT` memberships where `user_id = Ada` | **Allowed** — branch `Z` matches, `Y` is true |
| Login (same moment) | never set | set to Ada's id | `SELECT` memberships where `user_id = someone else` | **Blocked** — `Z` fails (wrong user id), `X` fails (no org set) |
| Ada, logged in as Org A, browsing the team page | set to Org A's id | not set this request | `SELECT` all memberships in Org A | **Allowed** — branch `X` matches |

---

## 7. Why registration doesn't set `app.current_user_id` in advance

Every sticky note (`SET LOCAL` / `set_config(..., true)`) only lives for
**one database transaction**, and every HTTP request in this app opens a
brand-new database connection (`get_db`, called fresh per request). Once
that request's transaction ends, the sticky note is gone — there is no way
for a later, unrelated request to read it back.

Registration and login are two separate requests, possibly separated by
weeks. Setting `app.current_user_id` during registration would only affect
*other queries within that same registration request* — it would have
already vanished by the time login runs, since login opens its own new
connection and transaction.

This is deliberate, not a limitation: `08_DECISIONS.md` (2026-09-04)
explains that `SET LOCAL` was chosen specifically so a setting **can't**
leak between requests, because in production, database connections get
reused across different customers via connection pooling (PgBouncer). The
same property that stops registration's sticky note from surviving into
login is what stops one customer's session from ever leaking into another
customer's request. Login has to redo the "who is this" step itself, in its
own transaction, because it's the only place that has both the
freshly-verified password and a live connection at the same moment.

---

## 8. `INSERT ... RETURNING` needs the *read* rule too, not just the write rule

This one is easy to miss, and it stayed hidden here for a while for a very
specific reason explained below.

When you `INSERT` a row, you'd expect only `WITH CHECK` (the write rule) to
matter. In practice, Postgres also has to decide whether to hand you back
the row you just inserted — and the ORM (SQLAlchemy) always asks for that
via `RETURNING`, to read back server-generated columns like `created_at`.
Handing back a row is a *read*, so Postgres also checks it against `USING`
(the read rule). If `WITH CHECK` says "yes, you may write this" but `USING`
says "you may not see this," Postgres doesn't insert the row and quietly
return nothing — it fails the whole statement with the same "new row
violates row-level security policy" error you'd get from a rejected write.

This bit `organizations`: registration's `WITH CHECK` correctly has a
bootstrap branch allowing the insert when no company sticky note exists
yet — but `USING` has no such branch (deliberately — see §5, giving it one
would mean any request that forgets to set a sticky note could suddenly
read every company's row). So the moment `WITH CHECK` let the write
through, `USING` turned around and blocked the `RETURNING` read of that
same row, and the whole insert failed.

**The fix isn't a `USING` exception** (that reintroduces the exact "see
everything" hole this design was built to avoid). It's to set the sticky
note to the *real* value before inserting, since it's already knowable:
`organizations.id` is generated in Python (`uuid.uuid4()`) before the
`INSERT` ever runs, so the code sets `app.current_org_id` to that exact id
first. By the time the insert (and its `RETURNING`) happens, the row
genuinely does match the sticky note under the normal branch — no
bootstrap exception needed for this table's reads at all.

**Why this stayed hidden until now:** the very first Postgres role this
project's app connected as (`elevare`) turned out to be a superuser with
`BYPASSRLS` — an M1 provisioning gap (`docker-compose.yml`'s
`POSTGRES_USER` becomes a superuser automatically; nothing ever created the
restricted role `07_SECURITY.md` actually specified). A superuser skips
every RLS check, `USING` included, so this `RETURNING` interaction never
had a chance to matter until the app was moved onto `elevare_app` — a real,
non-superuser, non-`BYPASSRLS` role
(`backend/scripts/db/provision_app_role.sql`) — and registration
immediately started failing. That failure is what surfaced this section.

---

## 9. Quick reference

| Table | Reads (`USING`) | Writes (`WITH CHECK`) |
|---|---|---|
| `users` | No RLS at all — identity is global, not company-owned | No RLS at all |
| `organizations` | Your current company's row, **or** (only when no company is set) every company you have a real membership in | Your current company's row, **or** any row when no company is set yet (creation) |
| `memberships` | Your current company's rows, **or** (only when no company is set) your own rows by user id | Your current company's rows, **or** any row when no company is set yet (creation) |

If something about a specific row not showing up (or a write being
rejected) doesn't make sense, check three things in order: (1) was
`app.current_org_id` or `app.current_user_id` actually set this request, by
what code, (2) which of the two branches should match given that, (3) does
the actual value being compared really equal what you expect (UUID
formatting, wrong id, etc.).
