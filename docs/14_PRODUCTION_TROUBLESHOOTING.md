# Production Troubleshooting Runbook

Commands for diagnosing problems on the VPS (`/opt/elevare`, Docker Compose, file
`docker-compose.prod.yml`). Each command is followed by a line-by-line explanation of what
it does. Companion to `11_DEPLOYMENT.md` (how the server was built); this file is "something
is broken, what do I run."

All commands are run **on the server**, as the `deploy` user, from `/opt/elevare`:

```bash
cd /opt/elevare
```

Containers: `api` (FastAPI), `celery_worker`, `celery_beat`, `db` (Postgres), `redis`,
`caddy` (HTTPS reverse proxy).

---

## How to read this app's logs (read this first)

- The API logs **every SQL statement** (`sqlalchemy.engine.Engine ... BEGIN (implicit)`, the
  `SELECT`/`INSERT`/`UPDATE`, then `ROLLBACK` or `COMMIT`). So when a request returns 500,
  the failing SQL and the database error are in the log **in the seconds around that
  request**, even if the word "Traceback" never appears.
- Every request logs a JSON line `Request started | request_id=... method=... path=...`.
  The matching access line looks like `"PUT /api/v1/business-dna HTTP/1.1" 500`.
- Log timestamps are **UTC**. Lagos is UTC+1, so 03:00 in Lagos = 02:00 UTC.
- Several requests can run at once, so their log lines interleave. A request's `request_id`
  appears on the "Request started" line, not on every SQL line. Use the **time window**
  method (Section 3) rather than grepping one id.
- The user-facing message "An unexpected error occurred" is deliberately generic. The real
  reason is only ever in these logs.

---

## Reading one request's story (the landmark method)

A single request prints hundreds of lines (every SQL statement, twice: plain text and JSON).
Ignore the JSON copies (lines starting `{"event"`) and read only these landmarks, in order:

| Landmark | Meaning |
|---|---|
| `BEGIN (implicit)` | A database transaction starts. |
| `SELECT set_config('app.current_org_id', ...)` | The tenant (organization) context is set **for this transaction only**. |
| `SELECT ... FROM <table>` | A read. The table name tells you which step of the code is running. |
| `INSERT INTO ...` / `UPDATE ...` | A write. |
| `COMMIT` | The transaction ends and is saved. **The tenant context is gone after this.** |
| `ROLLBACK` | The transaction ends and is discarded (normal at the end of a read; after a failure it means the request errored). |
| `Request failed ... exc_info [...]` | The Python exception. The class and message here are the real cause. |
| `"PUT /api/v1/... 500"` | What the user saw. |

Print only the landmarks for the last few minutes:

```bash
docker compose -f docker-compose.prod.yml logs api --no-log-prefix --since 5m 2>&1 \
  | grep -v '"logger": "sqlalchemy' \
  | grep -E "Engine (BEGIN|COMMIT|ROLLBACK)|set_config\(|^FROM |INSERT INTO|UPDATE |Request failed|HTTP/1\.1\"" \
  | cut -c1-200
```

| Part | What it does |
|---|---|
| `grep -v '"logger": "sqlalchemy'` | Removes the JSON copies of the SQL lines (halves the output). |
| `grep -E "..."` | Keeps only the landmark lines above. `^FROM ` shows which table each query read. |
| `cut -c1-200` | Trims every line to 200 characters. |

**Rules of thumb:**
- Find the `COMMIT`/`ROLLBACK` that ends the request, then read **upward** to the error.
- A `BEGIN (implicit)` with **no `set_config` after it** means queries are running with no
  tenant context. Row-level security then hides every row, so lookups return nothing
  (`None`/empty) rather than raising. This is the signature of a "read after `commit()`" bug.
- An error right after a `SELECT ... FROM x` often means that table/column is missing
  (migration not applied). Compare with `alembic current` vs `alembic heads` (Section 5).

---

## 1. Is everything running?

```bash
docker compose -f docker-compose.prod.yml ps
```

| Part | What it does |
|---|---|
| `docker compose` | Docker's multi-container tool. |
| `-f docker-compose.prod.yml` | Use the production definition file, not the local-dev one. Required on every command. |
| `ps` | List this stack's containers and their state. |

**Healthy:** every row says `Up` (db and redis also `healthy`).
**Bad:** `Restarting` (crash loop, see the logs for the reason), `Exited`, or a missing row.

---

## 2. Latest API log lines

```bash
docker compose -f docker-compose.prod.yml logs api --tail 100
```

| Part | What it does |
|---|---|
| `logs api` | Print the log output of the `api` container only. Swap `api` for `celery_worker`, `celery_beat`, `db`, `redis` or `caddy` to look at those. |
| `--tail 100` | Only the last 100 lines instead of the whole history. |

Add `-f` to follow live (new lines print as they happen; Ctrl+C to stop). Useful: run it,
ask the user to repeat the failing action, watch what appears.

---

## 3. Everything the API logged around a failure (the reliable method)

Use when someone gives you a time. Convert Lagos time to UTC first (subtract 1 hour).

```bash
docker compose -f docker-compose.prod.yml logs api --no-log-prefix \
  --since "2026-10-07T02:00:40Z" --until "2026-10-07T02:00:55Z" 2>&1
```

| Part | What it does |
|---|---|
| `--no-log-prefix` | Drops the `api-1  \|` label at the start of each line, so lines are shorter and easier to read or copy. |
| `--since "...Z"` | Only lines from this moment onward. The trailing `Z` means UTC. **Without the `Z`, Docker reads the time in the server's own timezone, which can silently point at the wrong window and print nothing.** |
| `--until "...Z"` | Only lines before this moment. Together with `--since` this gives a small window (about 15 seconds is plenty for one request). |
| `2>&1` | Docker prints logs on both stdout and stderr. This merges stderr into stdout so everything shows up together and can be piped. |

**What to look for in the output:** the line `"PUT /api/v1/... 500"`, then scan *upward*
for the line before it containing `ERROR`, `ProgrammingError`, `UndefinedColumn`,
`UndefinedTable`, `IntegrityError`, `relation ... does not exist`, `column ... does not
exist`, or a SQL statement followed immediately by `ROLLBACK`. That is the real cause.

**Short versions (use these first, the full window above can be very long):**

```bash
# A. Only the error lines, trimmed (usually 1-5 lines):
docker compose -f docker-compose.prod.yml logs api --no-log-prefix \
  --since "2026-10-07T02:00:40Z" --until "2026-10-07T02:01:00Z" 2>&1 \
  | grep -iE "error|does not exist|rollback" | grep -v " 500 " | head -5 | cut -c1-400

# B. The 15 lines leading up to the FIRST 500:
docker compose -f docker-compose.prod.yml logs api --no-log-prefix \
  --since "2026-10-07T02:00:40Z" --until "2026-10-07T02:01:00Z" 2>&1 \
  | grep -m1 -B15 '" 500 ' | cut -c1-300
```

| Part | What it does |
|---|---|
| `grep -iE "error\|does not exist\|rollback"` | Keep only lines that look like errors (case-insensitive, `\|` = "or"). |
| `grep -v " 500 "` | `-v` inverts: drop the access line that just reports the 500 itself. |
| `head -5` | Keep only the first 5 matching lines. |
| `cut -c1-400` | Trim each line to its first 400 characters so one giant SQL line can't flood the screen. |
| `grep -m1` | Stop after the first match, i.e. the first 500. |
| `-B15` | Also print the 15 lines **before** that match (the failing SQL and error live there). |

To pipe the full window into a file you can paste or share (**check for secrets first**):

```bash
docker compose -f docker-compose.prod.yml logs api --no-log-prefix \
  --since "2026-10-07T02:00:40Z" --until "2026-10-07T02:00:55Z" > /tmp/api-window.log 2>&1
```

`>` writes the output to a file instead of the screen.

---

## 4. Search the logs for one endpoint or one kind of error

```bash
docker compose -f docker-compose.prod.yml logs api --no-log-prefix --since 24h 2>&1 \
  | grep -n -B2 -A5 -iE "business-dna"
```

| Part | What it does |
|---|---|
| `--since 24h` | A relative window: the last 24 hours (`30m`, `2h`, `7d` also work). |
| `\|` | Pipe: send the log text into the next command instead of the screen. |
| `grep` | Print only lines matching a pattern. |
| `-n` | Show the line number of each match. |
| `-B2` / `-A5` | Also show 2 lines **B**efore and 5 lines **A**fter each match. **The dash matters:** `grep A1` (no dash) means "search for the text A1", not "show 1 line after", and was the typo on 2026-10-07. |
| `-i` | Ignore upper/lower case. |
| `-E` | Allow `\|` to mean "or" inside the pattern. |
| `"business-dna"` | The pattern. Change it to any endpoint, e.g. `"auth/login"`. |

Errors of any kind, last hour:

```bash
docker compose -f docker-compose.prod.yml logs api --no-log-prefix --since 1h 2>&1 \
  | grep -n -iE "error|exception|traceback|rollback|does not exist|UndefinedColumn|ProgrammingError|IntegrityError" \
  | tail -60
```

`tail -60` keeps only the last 60 matches so the screen isn't flooded.

---

## 5. Is the database schema behind the code? (migrations)

A very common cause of a sudden 500 after new code ships: the code expects a column or
table that the database doesn't have yet because `alembic upgrade head` wasn't run.

```bash
docker compose -f docker-compose.prod.yml exec -T api alembic current
docker compose -f docker-compose.prod.yml exec -T api alembic heads
```

| Part | What it does |
|---|---|
| `exec` | Run a command **inside an already-running** container (here `api`). |
| `-T` | Don't allocate an interactive terminal. Needed when the command is scripted or piped; harmless otherwise. |
| `alembic current` | The migration revision the **database** is actually at. |
| `alembic heads` | The newest migration revision that exists in the **code**. |

**Both should print the same revision id.** If `current` is older (or empty), the database is
behind the code. That is the bug.

Fix (after reading Section 6, because one migration can refuse to run):

```bash
docker compose -f docker-compose.prod.yml exec -T api alembic upgrade head
```

`upgrade head` applies every missing migration in order, up to the newest. Then restart so
nothing holds stale connections or schedules (Section 9).

If it prints a "multiple heads" error, two migrations branch from the same parent; that is a
code problem to fix in the repo, not a server problem.

---

## 6. Check a specific column or table exists

```bash
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U elevare -d elevare_db -c "\d organizations"
```

| Part | What it does |
|---|---|
| `exec -T db` | Run inside the **database** container. |
| `psql` | Postgres's command-line client. |
| `-U elevare` | Connect as the `elevare` role (the schema-owning superuser; fine for read-only inspection). |
| `-d elevare_db` | Connect to the `elevare_db` database. |
| `-c "..."` | Run this one command and exit. |
| `\d organizations` | psql command: describe the `organizations` table (all columns, types, constraints, indexes, RLS). Change the table name to inspect others. |

Narrow it to one column: add `| grep -i timezone` to the end of the command. No output means
the column does not exist.

List all tables: `-c "\dt"`. List applied migrations: `-c "SELECT * FROM alembic_version;"`.

**Safe pre-check before `alembic upgrade head`:** migration `1f55b227d9d9` refuses to run if
two accounts differ only by email capitalisation. Check first:

```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U elevare -d elevare_db -c \
  "SELECT lower(btrim(email)) AS email, count(*) FROM users GROUP BY 1 HAVING count(*) > 1;"
```

| Part | What it does |
|---|---|
| `lower(btrim(email))` | The email with spaces trimmed and lower-cased, which is how the migration compares them. |
| `GROUP BY 1` | Group rows that normalise to the same address. |
| `HAVING count(*) > 1` | Keep only addresses that appear more than once. |

**Zero rows = safe to migrate.** Any rows = duplicate accounts; fix those first.

---

## 7. Check the app's database role is still restricted (RLS safety)

```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U elevare -d elevare_db -c \
  "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname LIKE 'elevare%';"
```

Expected: `elevare` is `t`/`t` (migration-only superuser); `elevare_app` is `f`/`f`. If
`elevare_app` ever shows `t` for either, tenant isolation is not being enforced
(`08_DECISIONS.md` 2026-09-17).

---

## 8. Background jobs (emails, AI suggestions, auto-close)

```bash
docker compose -f docker-compose.prod.yml logs celery_worker --no-log-prefix --since 1h 2>&1 | tail -80
docker compose -f docker-compose.prod.yml logs celery_beat --no-log-prefix --since 1h 2>&1 | tail -40
```

- **Emails and AI generation run in the worker, not the API**, so their errors are in
  `celery_worker`'s log.
- `celery_beat` is the scheduler (quarterly review, hourly attendance auto-close). It should
  log "Scheduler: Sending due task ..." lines. Silence for hours means beat is down.
- AI suggestions silently empty? Check the key and recent calls:
  ```bash
  docker compose -f docker-compose.prod.yml logs celery_worker --since 24h 2>&1 | grep -iE "generate_suggestions|anthropic"
  docker compose -f docker-compose.prod.yml exec -T db psql -U elevare -d elevare_db -c \
    "SELECT created_at, purpose, model FROM ai_usage_log ORDER BY created_at DESC LIMIT 10;"
  ```
  No recent `ai_usage_log` rows means no call reached Claude (missing/placeholder
  `ANTHROPIC_API_KEY`, or generation never triggered).

---

## 9. Restarting things

```bash
# Apply a changed .env (a plain `restart` does NOT re-read .env):
docker compose -f docker-compose.prod.yml up -d --force-recreate api celery_worker celery_beat

# Just bounce containers (picks up new migrations/code already on disk, not .env changes):
docker compose -f docker-compose.prod.yml restart api celery_worker celery_beat
```

| Part | What it does |
|---|---|
| `up -d` | Start/refresh containers in the background (`-d` = detached). |
| `--force-recreate` | Destroy and recreate the named containers, so they re-read `.env`. |
| `api celery_worker celery_beat` | Only these three. Never recreate `db` casually. Its data is in a volume and survives, but recreating it is rarely needed. |
| `restart` | Stop and start the same containers without re-reading `.env`. |

After shipping new code or migrations, always restart **all three** app containers: the worker
and beat only learn about new tasks and schedules on start-up.

---

## 10. Quick decision guide

| Symptom | First command | Likely cause |
|---|---|---|
| Whole site down or timing out | Section 1 (`ps`), then `logs caddy` | A container is `Restarting`/`Exited`; for crash loops read `logs api`. Usual cause: `ENVIRONMENT=production` before real email/CORS values (`11_DEPLOYMENT.md`). |
| One endpoint returns 500 | Section 3 (time window) | Look for a SQL/DB error just above the 500. |
| 500 right after a new release | Section 5 (`alembic current` vs `heads`) | Migrations not applied. |
| Login works, one feature 500s | Section 6 (`\d <table>`) | Missing column/table. |
| Emails not arriving | Section 8 (worker log) | Resend key/domain, or worker not restarted. |
| AI suggestions never appear | Section 8 (`ai_usage_log`) | Missing `ANTHROPIC_API_KEY` or no trigger fired. |
| Scheduled jobs not running | `logs celery_beat` | Beat down or not restarted after deploy. |

---

## 11. Reset a test organization so onboarding starts afresh (destructive)

Use on a **test/demo** organization only. Keeps the organization row, the user and the
owner's membership; deletes everything else the organization owns (plan, departments, roles,
people, OKRs, KPIs, tasks, workflows, scores, Business DNA) and blanks the company name.
Steps: back up, dry-run with `ROLLBACK`, then run again with `COMMIT`.

**Why this order.** Foreign keys point child to parent (a KPI points at a key result, a key
result at an objective, an objective at a department), so children are deleted first.
Three self-references are set to NULL first (`departments.head_employee_id`,
`positions.reports_to_position_id`, `employees.manager_id`), or the delete is blocked by its
own rows. `audit_log` and `ai_usage_log` are left alone (history, may be append-only).

**Where the onboarding position lives.** In the browser (`localStorage` key
`wos_onboarding_progress`), not on the server. After the reset, open
`/onboarding/business-dna` directly. Saving Business DNA triggers the first plan only when
the organization has no `blueprint_items`, which is what the reset guarantees.

Backup first: `docker compose -f docker-compose.prod.yml exec -T db pg_dump -U elevare elevare_db > backup_before_reset.sql`.

Save as `reset_org.sql` (replace `ORG-ID`; end with `ROLLBACK;` for the dry run, `COMMIT;` for real):

```sql
BEGIN;
SELECT set_config('app.current_org_id', 'ORG-ID', true);
UPDATE departments SET head_employee_id = NULL;
UPDATE positions SET reports_to_position_id = NULL;
UPDATE employees SET manager_id = NULL;
DELETE FROM task_blocks;
DELETE FROM tasks;
DELETE FROM workflow_instances;
DELETE FROM workflow_steps;
DELETE FROM workflow_templates;
DELETE FROM attendance_records;
DELETE FROM employee_kpi_scores;
DELETE FROM kpi_scores;
DELETE FROM department_scores;
DELETE FROM executive_summaries;
DELETE FROM ai_suggestions;
DELETE FROM blueprint_items;
DELETE FROM kpis;
DELETE FROM key_results;
DELETE FROM okrs;
DELETE FROM invites;
DELETE FROM employees;
DELETE FROM positions;
DELETE FROM departments;
DELETE FROM locations;
DELETE FROM notifications;
DELETE FROM business_dna_core_values;
DELETE FROM business_dna;
UPDATE organizations SET name = NULL WHERE id = 'ORG-ID';
SELECT (SELECT count(*) FROM blueprint_items) AS blueprint,
       (SELECT count(*) FROM departments) AS departments,
       (SELECT count(*) FROM employees) AS employees,
       (SELECT count(*) FROM memberships) AS memberships;
ROLLBACK;
```

Run: `docker compose -f docker-compose.prod.yml exec -T db psql -U elevare -d elevare_db -v ON_ERROR_STOP=1 < reset_org.sql`
(`-v ON_ERROR_STOP=1` stops at the first error so nothing half-applies; `<` feeds the file in).
If other team members exist, their memberships/users are untouched; only their employee rows go.

---

## 12. Test scoring without waiting three months (test companies only)

Scoring works in fiscal quarters, and a quarter only closes when a night runs after it ended. The
helper `backend/scripts/admin/stage9_time_helper.py` runs the REAL nightly job as if it were another
date. It does not change the company; it only changes the "now" the job uses.

Step 1: find the company's id and exact name (the helper asks for both so it can never be pointed
at a real customer by accident):

```
docker compose -f docker-compose.prod.yml exec -T db psql -U elevare -d elevare_db -c "SELECT id, name FROM organizations;"
```
`exec -T db` runs a command inside the database container (`-T` = no terminal, needed when
scripting); `psql -U elevare -d elevare_db` opens the database as the `elevare` user; `-c` runs the one
query and exits. Copy the id and the name of the TEST company (for example `Zenith Test Ltd`).

Step 2: see where the company stands (read-only):

```
docker compose -f docker-compose.prod.yml exec -T api python scripts/admin/stage9_time_helper.py show --org <id> --name "Zenith Test Ltd"
```
It prints the company's fiscal year start month, and for the previous and the current quarter how
many department rows exist and how many are **frozen** (closed for good).

Step 3: close the quarter that contains the tasks you made (their deadlines are in November 2026,
so that is Q4 2026, which ends on 31 December; pretend it is 2 January 2027):

```
docker compose -f docker-compose.prod.yml exec -T api python scripts/admin/stage9_time_helper.py run --org <id> --name "Zenith Test Ltd" --on 2027-01-02
```
It prints `{'closed_previous_period': True}`. Now open Performance, the department summary, the
leaderboard and the company view and pick the quarter 2026-10-01 to 2026-12-31: the numbers are final.
On the first night of the new quarter HR administrators also get the KPI-weight reminder for any
department with weights below 100 (Notifications).

Step 4: to add more data and close the quarter again, re-open it (only the "frozen" marks are cleared;
nothing is deleted; manual KPI results you typed in are never touched), then run step 3 again:

```
docker compose -f docker-compose.prod.yml exec -T api python scripts/admin/stage9_time_helper.py unfreeze --org <id> --name "Zenith Test Ltd" --quarter-start 2026-10-01
```
Reading the evidence: `show` after step 3 should say `1 frozen`-or-more department rows for the closed
quarter and `0 frozen` for the current one. If `run` prints `closed_previous_period: False`, the quarter
was already frozen (run `unfreeze` first), or the company was created after that quarter ended.
Rule to remember: **the job is safe to run twice; a frozen quarter is never rewritten**, which is why
`unfreeze` exists.

---

## 13. Bring back a company its owner deleted (archived)
Deleting a company never erases it: it stamps `organizations.archived_at`, and stamps every membership's
`deactivated_at` with the SAME instant (`04_DATABASE.md`). So restoring is the reverse, in one transaction.
Run it as the database owner (`-U elevare`), the same way as section 11; the app's own role cannot see across companies.

```sql
BEGIN;

-- 1. Which companies are archived, and when? Pick the id to restore.
SELECT id, name, archived_at FROM organizations WHERE archived_at IS NOT NULL;

-- 2. Give access back to exactly the people who lost it BECAUSE of the deletion (replace the id twice).
UPDATE memberships
   SET deactivated_at = NULL
 WHERE organization_id = '<company id>'
   AND deactivated_at = (SELECT archived_at FROM organizations WHERE id = '<company id>');

-- 3. Make the company live again.
UPDATE organizations SET archived_at = NULL WHERE id = '<company id>';

COMMIT;
```

Line by line:
- `BEGIN; ... COMMIT;` makes the three statements all-or-nothing. Change `COMMIT` to `ROLLBACK` to rehearse.
- Step 1 only reads; it shows the company's name so you do not restore the wrong one.
- Step 2 matches `deactivated_at` to the company's own `archived_at`. Anyone an HR administrator had deactivated
  EARLIER has a different time, so they correctly stay deactivated. Without that condition you would reopen
  access for people who were removed on purpose.
- Step 3 last, so the company is never live with nobody in it.
- Not restored: invites that were waiting (they were marked used), so send them again. The owner's other
  companies are untouched, so they just open "Switch company".
- Check afterwards: the owner's name menu shows "Switch company (N)" again, and the restored company opens.

---

## Incident log

### 2026-10-07: `PUT /api/v1/business-dna` returns 500 (reported by Uche)

- **Report:** three 500s ("An unexpected error occurred") from `umbonuike@gmail.com`, about
  03:00 Lagos (02:00 UTC) on 2026-10-07, request bodies matched `BusinessDNAUpsertRequest`.
  Login and `GET /auth/me` worked.
- **First hypothesis (wrong):** migrations (`timezone` / `organization_name` columns) not
  applied on the VPS. Ruled out: the log showed `SELECT organizations.timezone` running fine.
- **Cause (confirmed):** `PUT /business-dna` committed, then re-read the organization and core
  values. The tenant context (`set_config('app.current_org_id', ..., true)`) is
  transaction-local, so it is gone after `commit()`; row-level security then hid the
  `organizations` row, `get_organization_by_id` returned `None`, and `organization.name`
  raised `AttributeError: 'NoneType' object has no attribute 'name'`. The save itself had
  already committed (the `business_dna` row existed, `updated_at` 02:00:41Z, the first
  attempt). Core values were also silently returned empty for the same reason.
- **How it was found:** the error lines (Section 3, short version A) showed
  `AttributeError ... 'name'` straight after a `ROLLBACK`; the landmark method (above) showed
  a `BEGIN (implicit)` after the `COMMIT` with no `set_config`, i.e. a query running with no
  tenant context. A real PUT from the author's own account reproduced it.
- **Why tests missed it:** the test session runs inside one outer transaction, so `commit()`
  never ends it and the tenant setting survives. Regression tests now simulate a real commit
  (`commit_like_production` in `tests/conftest.py`).
- **Same bug, found in the audit:** `POST /memberships` read the organization after commit, so
  invite emails silently lost the company name (no crash). Fixed the same way. No other
  commit in the app reads tenant data afterwards; the remaining post-commit reads touch only
  `users` and `invites`, which have no RLS.
- **Fix:** branch `fix/business-dna-put-rls-context`: read everything and build the response
  *before* `commit()`. Production keeps the bug until that branch is merged to `main` and
  deployed.
- **Rule to remember:** never read tenant data after `commit()` in a request. If a query must
  follow a commit, set `app.current_org_id` again first.
- **Status:** fixed on the branch, awaiting merge and deploy.

### 2026-10-22: the app says "Couldn't reach server" (the VPS bill was unpaid)

- **Report:** right after merging the AI-blueprint work, the frontend showed "Couldn't reach
  server". The first suspicion was the deploy that the merge triggers.
- **Check from outside first (no server login needed).** From any laptop:
  ```bash
  curl -sS -m 15 -o /dev/null -w "http=%{http_code}\n" https://api.workforceos.online/health
  getent hosts api.workforceos.online
  ```
  | Part | What it does |
  |---|---|
  | `-sS` | Silent, but still print an error if the request fails. |
  | `-m 15` | Give up after 15 seconds, so a dead server does not hang the command. |
  | `-o /dev/null` | Throw the response body away. |
  | `-w "http=%{http_code}\n"` | Print only the HTTP status code (`000` means it never connected). |
  | `getent hosts` | Shows which IP the domain points to (so you know which machine you are testing). |
- **What the evidence said, and how to read it.** The frontend (Vercel, `workforceos.online`)
  answered, so the problem was not the frontend. The API domain **refused** the connection on
  ports 443 and 80 within 0.3 s, while SSH (port 22) was open. *Refused fast* is not the same
  as *timed out*: a refusal means the machine answered but nothing listens on that port (here
  Caddy, the only program on 80/443); a timeout means the machine or network is unreachable.
  Pattern to remember: **"Couldn't reach server" in the app = the browser got no answer at
  all**, so check the network path (DNS, ports, the VPS itself) before reading API logs.
- **First guess and why it was only a guess:** "the deploy left Caddy down" (two merges close
  together can make two deploys fight over the containers). It fitted the symptom but nothing
  proved it; the user then reported the real cause.
- **Cause:** the InterServer VPS had not been paid for, so the provider had stopped serving it
  (SSH still answered, which a plain "powered off" server would not do: a partly suspended
  account looks like this).
- **Why it was missed:** nothing on the project warns when the hosting bill is due. The code,
  CI and the deploy were all fine.
- **Fix:** pay InterServer and make sure the VPS is on. Then re-check with the `curl` above.
  If `ps` shows containers `Exited`, run `docker compose -f docker-compose.prod.yml up -d`
  (starts what is stopped, rebuilds nothing). If the GitHub "CD" run after a merge failed
  because the server was unreachable, re-run it once the server answers: it pulls the code,
  rebuilds, applies migrations (including `e3de7830b474`) and restarts the worker.
- **Second cause, found after paying (same day): the DEV stack was running instead of the
  production one.** `docker compose ps` showed `api` published on `0.0.0.0:8000`, `db` on
  `0.0.0.0:5432`, `redis` on `0.0.0.0:6380` and **no `caddy` row**. `docker-compose.prod.yml`
  publishes only Caddy's 80 and 443 and nothing for api/db/redis, so containers with those
  ports can only have been created from the dev file (`docker-compose.yml`), which is what a
  plain `docker compose up -d` (no `-f docker-compose.prod.yml`) uses. A port check from
  outside confirmed 8000, 5432 and 6380 were OPEN to the internet and 80/443 closed.
  *How to read this:* the PORTS column of `ps` is the quickest way to tell which compose file
  a container came from. In production only `caddy` may show `0.0.0.0:`.
  Why it matters: Postgres and an **unauthenticated Redis** were reachable by anyone.
  Fix: `docker compose -f docker-compose.prod.yml up -d --build --force-recreate` (the same
  command the deploy runs), then check `ps` shows caddy and no `0.0.0.0:` on api/db/redis, and
  that `curl https://api.workforceos.online/health` answers.
- **Rule to remember (the `-f` rule):** on this server EVERY compose command needs
  `-f docker-compose.prod.yml`. Forgetting it does not error: it quietly starts the dev stack.
  Consider `alias dc='docker compose -f docker-compose.prod.yml'` in the deploy user's profile.
- **Rule to remember:** when the whole API is unreachable, ask three questions in order before
  touching code: (1) is the bill paid and the VPS on, (2) does the domain still point at the
  right IP, (3) is Caddy running (`ps`). Also set a calendar reminder for the VPS renewal date.

### 2026-11-13: changing a teammate's access level shows a 500, but the change is saved

- **Report (Emmanuel, live testing):** choosing Manager or Employee for a person in Team
  Management showed a 500 error. After a reload the new role was there.
- **Symptom pattern to remember:** *an error, yet the change is saved after reload*. That means
  the failure happens AFTER the `COMMIT`, not before it.
- **Cause (reproduced by a test):** `PATCH /memberships/{id}` committed and then called
  `db.refresh(updated, attribute_names=["user"])` to build the reply. The tenant setting
  (`app.current_org_id`, set with `set_config(..., true)`) lives only until the commit, and
  `memberships` has row-level security, so the re-read found no row and SQLAlchemy raised
  `InvalidRequestError: Could not refresh instance '<Membership ...>'`. This is the same family as the
  2026-10-07 `PUT /business-dna` incident.
- **How it was found:** the first hypothesis came straight from the symptom pattern above and
  the incident log. The proof was a test using `commit_like_production` (`tests/conftest.py`),
  which makes the test database forget the tenant setting on commit like the real one does. It
  failed with exactly that error. On the server the same error line would sit just above the
  `"PATCH /api/v1/memberships/... 500"` access line, after a `COMMIT`.
- **Why it was missed:** the ordinary tests run inside one outer transaction, so a commit never
  ends it and the tenant setting survives. Only a test with `commit_like_production` sees it.
- **Fix:** `update_membership` in `tenancy_identity/router.py` now loads the user and builds the
  response BEFORE `commit()`. Test: `tests/memberships/test_role_change_commit_context.py`. A search
  of every router found no other read after a commit.
- **Rule to remember (second time):** never read anything tenant-scoped after `commit()`. Build
  the reply first, commit last. Any new endpoint that returns data should get a test with
  `commit_like_production`.
