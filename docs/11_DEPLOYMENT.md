# Deployment

An early demo environment, pulled forward from M15 ("Deployment & Demo
Readiness") ahead of schedule — see `08_DECISIONS.md` 2026-09-21. This is
**not** the eventual production environment; that decision (Azure, pending
a CloudSA conversation, per `00_PROJECT_CONTEXT.md`) stays open and
unaffected. This is a cheap, small environment for the founder, HR, and
the frontend developer (3–6 people, not continuous use) to see real changes
land without running the stack locally.

Frontend deployment is unaffected by any of this — it stays on Vercel
(`08_DECISIONS.md` 2026-09-18), a separate, already-decided track. Everything
below is backend-only: FastAPI, Postgres, Redis, Celery worker, Celery beat.

## Host

InterServer Cloud VPS ("slice" pricing, $3/slice/month) — a real KVM VPS
with root access and Docker support, not shared/cPanel hosting (the two
look similar in InterServer's own pricing page, worth not confusing them
again). **One slice** (~1 CPU, ~1GB RAM, ~30GB disk) for this demo's actual
usage pattern — a handful of known people, not continuous traffic. If the
box ever struggles (OOM kills, slow response under a real demo), adding a
second slice (~$6/mo total) is the fix, not a re-architecture.

## Provisioning the VPS

1. Sign up at interserver.net, create a **Cloud VPS**, 1 slice, **New
   Jersey** location (lowest latency to Nigeria of InterServer's US
   locations — the major transatlantic cables from West Africa land on
   the US East Coast), **Ubuntu 24.04 LTS**.
2. During creation, add your SSH public key rather than using a generated
   root password over email, if InterServer's flow offers that option.
3. Note the server's public IP address.

## First login and hardening

SSH in as `root` using the IP from above, then:

```bash
# Create a non-root deploy user with sudo, rather than using root for
# everything going forward.
adduser deploy
usermod -aG sudo deploy

# Copy your SSH public key to the new user (paste it into this file, or
# use ssh-copy-id from your own machine instead of doing it by hand).
mkdir -p /home/deploy/.ssh
nano /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Key-only SSH, no root login, no password auth — edit /etc/ssh/sshd_config:
#   PermitRootLogin no
#   PasswordAuthentication no
# The systemd unit is named "ssh" on Debian/Ubuntu, not "sshd" — the latter
# doesn't exist as a unit name and this command would otherwise fail.
systemctl restart ssh

# Basic firewall — only what the app actually needs exposed. Postgres
# (5432) and Redis (6379) are never opened here; Caddy fronts everything
# and Postgres/Redis stay on the internal Docker network only.
apt-get update && apt-get install -y ufw
ufw allow 22
ufw allow 80
ufw allow 443
ufw enable
```

From here on, log in as `deploy`, not `root`.

## Installing Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
# log out and back in for the group change to take effect
docker compose version   # confirms the Compose plugin landed too
```

## Getting the code onto the server

The GitHub Actions deploy job runs `git pull` on the server, so the server
needs its own read-only way to reach the repo — a **Deploy Key** (GitHub
repo → Settings → Deploy keys), not a personal access token, since it's
scoped to just this one repo and read-only by design.

```bash
# On the server, as deploy:
ssh-keygen -t ed25519 -C "elevare-vps-deploy-key" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
# Paste that public key into GitHub → repo Settings → Deploy keys → Add
# deploy key. Read access is enough — this key only ever pulls.

sudo mkdir -p /opt/elevare
sudo chown deploy:deploy /opt/elevare
git clone git@github.com:elevarehumansolutions-ux/Workforce-OS.git /opt/elevare
cd /opt/elevare
```

## Creating the production env files

Two files, both server-only, both already covered by `.gitignore`'s
`.env.*` pattern — never commit either:

**`backend/.env.postgres`** — the Postgres container's own bootstrap
credentials (the schema-owning superuser):
```
POSTGRES_USER=elevare
POSTGRES_PASSWORD=<generate a real, random password>
POSTGRES_DB=elevare_db
```

**`backend/.env`** — copy `backend/.env.example` and fill in real values:
- `DATABASE_URL` — `postgresql+psycopg://elevare_app:<elevare_app's password>@db:5432/elevare_db` (note the host is `db`, the Compose service name, not `localhost`)
- `MIGRATION_DATABASE_URL` — same shape, but `elevare` (the superuser) with the password from `.env.postgres` above
- `REDIS_URL` — `redis://redis:6379/0`
- `JWT_SECRET_KEY` — generate a real secret (`openssl rand -hex 32`), never the placeholder
- `ENVIRONMENT` — **`development`, not `production`, until HTTPS is actually live.** Two independent things hinge on this one value, and getting it wrong breaks the deploy in two different ways: (1) `app/core/config.py`'s `validate_production_secrets` refuses to boot at all when `environment=production` unless `EMAIL_STUB_MODE=false` and `CORS_ALLOWED_ORIGINS` has no `localhost` entries — neither is true yet, this exact mistake crash-looped every container on first deploy; (2) it also controls the refresh-token cookie's `Secure` flag (`environment != "development"`) — `Secure` cookies are silently rejected by browsers over a non-HTTPS connection, so setting anything other than `development` while still IP-only/HTTP would have quietly broken login sessions even without the crash. Switch to `staging` once the domain's HTTPS is confirmed working (see "Domain" section below) — `production` itself still needs real `EMAIL_STUB_MODE`/CORS values first, not just HTTPS.
- `CORS_ALLOWED_ORIGINS` — the frontend's real Vercel URL once it's deployed; the placeholder `["http://localhost:5173"]` is fine for now, same reasoning as `ENVIRONMENT` above.
- `APP_URL` — `http://<server-ip>` for now, `https://workforceos.online` once HTTPS is confirmed.
- Everything else (`ANTHROPIC_API_KEY`, `PAYSTACK_*`, `EMAIL_STUB_MODE=true`) — placeholder values are fine until those features actually ship; nothing in M6 exercises them.

## First-time bootstrap

```bash
cd /opt/elevare
docker compose -f docker-compose.prod.yml up -d db redis
# wait a few seconds for db's healthcheck to pass

# Provision the elevare_app role — same script, same idea as local dev
# (07_SECURITY.md's "Provisioning a new environment" checklist), just
# run here instead of against the dev container.
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U elevare -d elevare_db -v app_password="<elevare_app's password, matching .env>" \
  < backend/scripts/db/provision_app_role.sql

# Verify it actually landed as non-superuser, non-BYPASSRLS — don't just
# assume the script ran cleanly (07_SECURITY.md: "this is what caught the
# M1 gap in the first place").
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U elevare -d elevare_db -c \
  "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname LIKE 'elevare%';"

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec -T api alembic upgrade head
```

Visit `http://<server-ip>` — Caddy should be proxying to the API.

## Wiring up GitHub Actions

Repo → Settings → Secrets and variables → Actions, add:
- `VPS_HOST` — the server's IP
- `VPS_USER` — `deploy`
- `VPS_SSH_KEY` — a **separate** ed25519 keypair generated specifically for
  this (`ssh-keygen -t ed25519 -f deploy_action_key -N ""` on your own
  machine, not the server) — paste the *private* key content into this
  secret, add the *public* key to the server's
  `/home/deploy/.ssh/authorized_keys`. Never reuse the deploy-key pair
  from the "getting the code onto the server" step above for this — that
  one is read-only-to-GitHub, this one needs to SSH *into* the server, two
  different directions, two different keys.

From here, every push to `main` (after `docker-compose.yml`/CI passes)
auto-deploys — see `.github/workflows/ci-cd.yml`.

## Domain: workforceos.online

DNS is on Cloudflare (free plan, nameservers pointed there from Namecheap
registration), **DNS only** — not proxied (grey cloud) — an `A` record for
the bare domain pointing at the VPS's IP. Kept unproxied deliberately:
Cloudflare's proxy would intercept Caddy's ACME HTTP-01 challenge before it
reaches the server, breaking automatic certificate issuance unless Caddy
were reconfigured for DNS-01 (Cloudflare API token) instead — unnecessary
complexity for a 3–6 person internal tool.

`Caddyfile` already targets `workforceos.online` — Caddy requests and
renews a free Let's Encrypt certificate for it automatically on startup,
no other config needed on the Caddy side.

**Once HTTPS is confirmed working** (`https://workforceos.online/health`
returns a valid response with no certificate warning), two follow-ups in
`backend/.env`:
1. `APP_URL` — change from the IP to `https://workforceos.online`.
2. `ENVIRONMENT` — change from `development` back to `staging` (not
   `production` yet — that still requires `EMAIL_STUB_MODE=false` and a
   real `CORS_ALLOWED_ORIGINS`, neither of which is true yet). `staging`
   gives correctly `Secure`-flagged cookies now that the connection is
   genuinely HTTPS, without tripping the strict production checks in
   `app/core/config.py`'s `validate_production_secrets`. Recreate the
   affected containers afterward — a plain `restart` doesn't reread
   `.env` (`docker compose -f docker-compose.prod.yml up -d
   --force-recreate api celery_worker celery_beat`).

## What this environment deliberately does not include

Matches `09_PROGRESS.md`'s M15 entry, which this pulled a subset out of —
the rest stays for later, not because it's forgotten:
- No seed script / demo data with historical scoring periods.
- No confirmed database backup strategy (the `postgres_data` volume
  persists across redeploys, but nothing ships it off the box).
- No investor-facing polish pass — this is an internal working
  environment, not the demo environment M15 describes.
- No staging/production split — one box, one environment.

## First deployment log (2026-09-21 to 2026-09-22): what actually happened

The steps above are the clean version. This section is the real,
chronological record of the first live run — every issue actually hit, the
exact error where one appeared, and how it was resolved — kept for future
troubleshooting, not as a retelling. If a future deploy (a rebuild, a second
environment) hits something that looks similar, check here first.

1. **VPS ordered.** InterServer Cloud VPS, 1 slice, New Jersey (lowest
   latency to Nigeria of InterServer's US locations — transatlantic cables
   from West Africa land on the US East Coast), Ubuntu 24.04 64-bit (not
   the Desktop image — that bundles a full GUI and recommends 2GB RAM just
   for the OS, wasted overhead on a headless Docker box already tight on a
   1GB slice).

2. **First SSH login failed — wrong root password.** A custom password had
   been intended during the order flow but didn't actually get set;
   InterServer doesn't re-display the root password anywhere in the
   dashboard after creation, and it wasn't in email either. Resolved via
   the VPS panel's **Reinstall OS** action (server had nothing on it yet,
   so a clean reinstall was the fastest fix) — re-selected Ubuntu 24.04
   64-bit, set the password carefully this time.

3. **Second SSH attempt warned `REMOTE HOST IDENTIFICATION HAS CHANGED`,
   refused to connect.** Expected: reinstalling the OS generates a brand
   new SSH host key, different from the one `known_hosts` recorded from
   attempt #2. Confirmed this was the known reinstall, not a real MITM,
   and cleared the stale entry:
   ```
   ssh-keygen -f '~/.ssh/known_hosts' -R '163.245.215.24'
   ```
   Reconnected cleanly after that.

4. **`docs/11_DEPLOYMENT.md` itself had a bug in the hardening step** —
   told the reader to run `systemctl restart sshd`. The systemd unit on
   Debian/Ubuntu is named `ssh`, not `sshd` (no such unit exists); the
   command would have failed. Caught and fixed before it was actually run.

5. **First-time bootstrap blocked — `docker-compose.prod.yml` didn't exist
   on the server.** The `infra/early-deploy` branch containing it had been
   built locally but never pushed/merged yet. Pushed, PR'd, merged, then
   `git pull` on the server picked it up.

6. **CI failed: `ruff: command not found`.** `ruff` is deliberately absent
   from `backend/requirements.txt` (a separate, already-logged decision —
   deferred to M14), and `.github/workflows/ci-cd.yml`'s lint step
   wrongly assumed it would already be on the runner. Fixed by installing
   a pinned `ruff==0.15.13` as its own CI-only step, not by adding it to
   `requirements.txt` (which would have quietly reopened that deferred
   decision instead of just fixing CI).

7. **The `deploy` job failed with `Error: missing server host`.**
   Expected at that point in the sequence — the `VPS_HOST`/`VPS_USER`/
   `VPS_SSH_KEY` GitHub secrets hadn't been added yet (that came later, at
   step 13). Not a bug, just reached before its prerequisite.

8. **`elevare_app` role provisioned and verified** — output read at first
   as "RLS is on for `elevare`, off for `elevare_app`, which is the
   superuser." Backwards on both counts: `elevare` (`rolsuper=t`,
   `rolbypassrls=t`) is the superuser, RLS bypassed for it, by design —
   it's migration-only, never live traffic. `elevare_app` (`rolsuper=f`,
   `rolbypassrls=f`) is the ordinary restricted role RLS actually applies
   to, and is what `DATABASE_URL` points at. Worth being exact about this
   one specifically — mixing the two up is the same class of mistake that
   caused a real incident earlier in this project (`08_DECISIONS.md`
   2026-09-17).

9. **All three app containers (`api`, `celery_worker`, `celery_beat`)
   crash-looped on first full boot.** Root cause:
   `backend/.env` had `ENVIRONMENT=production` (this runbook's own
   original, wrong guidance). `app/core/config.py`'s
   `validate_production_secrets` refuses to boot under `environment=
   production` unless `EMAIL_STUB_MODE=false` and `CORS_ALLOWED_ORIGINS`
   has no `localhost` entries — neither was true yet. The actual crash:
   ```
   pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
     Value error, Production security checks failed:
     - EMAIL_STUB_MODE must be false in production
     - CORS_ORIGINS contains localhost — remove before production deploy
   ```
   A second, quieter bug was sitting right behind this one: `ENVIRONMENT`
   also drives the refresh-token cookie's `Secure` flag — had the crash
   not happened, `production` would have set `Secure` on a cookie served
   over plain HTTP (no domain/TLS yet at this point in the sequence),
   which browsers silently refuse to store, breaking login with no
   visible error. Fixed by setting `ENVIRONMENT=development` for this
   interim IP-only phase — accurate, and gives correct cookie behavior for
   the transport actually in use at the time.

10. **`/health` confirmed working over plain HTTP** —
    `{"status":"ok","database":"ok",...}`. First real end-to-end proof the
    stack was up.

11. **Domain bought** — `workforceos.online`, Namecheap, under $2
    first-year promo (renewal will be higher, a known tradeoff of
    promo-priced TLDs, accepted deliberately).

12. **DNS moved to Cloudflare** via "Connect a domain" (not "Transfer" —
    transfer moves registration/billing too, blocked by ICANN for the
    first 60 days of a new registration anyway, and unnecessary just to
    manage DNS) — nameservers changed at Namecheap, confirmed active by
    Cloudflare within a few hours.

13. **Adding the VPS's A record surfaced pre-existing conflicting DNS
    records** — Cloudflare's initial scan had imported Namecheap's default
    parking-page setup: an `A` record for the bare domain pointing at
    Namecheap's parking IP (**Proxied**), a `www` CNAME to the same
    parking page (**Proxied**), and MX/TXT records for Namecheap's free
    email forwarding. Two `A` records for the same name would have made
    resolution unpredictable, and the old Proxied one would have
    intercepted Caddy's certificate request even if DNS picked the right
    one. Fixed: deleted the old parking-page `A` record, kept only the new
    one (VPS IP, **DNS only**, not proxied — proxying would break Caddy's
    ACME HTTP-01 challenge the same way). Left the MX/TXT records alone
    (unrelated, harmless). Left the `www` CNAME as optional cleanup (not
    blocking — nothing serves `www`, `Caddyfile` only handles the bare
    domain).

14. **`Caddyfile` updated** from `:80` to `workforceos.online`, pushed,
    merged, Caddy container recreated. **Certificate issuance succeeded on
    the first attempt** — confirmed via `docker compose logs caddy`:
    `"msg":"certificate obtained successfully","identifier":
    "workforceos.online"`. No manual certbot step, no cron job — this is
    genuininely automatic with Caddy, unlike the nginx+certbot setup used
    previously for the recruitment site.

15. **`APP_URL` guidance in this runbook was wrong.** Told the reader to
    set it to the backend's own domain (`https://workforceos.online`).
    Actually used exclusively to build links *emailed to users*
    (`{APP_URL}/verify-email?token=...`, `/reset-password?...`,
    `/accept-invite?...`) — frontend routes, not backend ones; the backend
    has no page at `/verify-email` at all, only an API endpoint at a
    different path. Caught by inspection of `app/core/email.py` before it
    caused a real broken-link incident (harmless in the moment only
    because `EMAIL_STUB_MODE=true` means no real email was going out yet).
    Fixed: left as an obvious placeholder until the frontend is actually
    deployed, with an explicit note not to forget updating it before
    `EMAIL_STUB_MODE` is ever flipped to `false`.

16. **`ENVIRONMENT` switched from `development` to `staging`** once HTTPS
    was confirmed live — correct now that the transport genuinely
    supports `Secure` cookies. Still not `production`: that requires real
    `EMAIL_STUB_MODE`/CORS values first, unrelated to whether TLS exists.

17. **GitHub Actions deploy secrets added** (`VPS_HOST`, `VPS_USER`,
    `VPS_SSH_KEY`) — a dedicated keypair generated specifically for this,
    deliberately separate from the read-only deploy key added back at
    step 5 (that one only lets GitHub *read* the repo; this one lets
    GitHub Actions *SSH into* the server — opposite directions, must never
    be the same key).

18. **`develop` branch added** as a CI safety gate (feature branch → PR →
    `develop` → PR → `main`) — not a second deployment. Explicitly decided
    against a real staging *environment*: the current VPS is already using
    roughly 850MB of its ~1GB slice for one stack; a second full stack
    would need a second VPS or more slices, an added cost not justified
    yet for a 3–6 person internal tool. `develop` gets the same automated
    test+lint gate `main` does, just no deploy target of its own.

19. **Open/unresolved at the time of writing:** the site was reported as
    "still trying to load" once, not yet diagnosed. If this recurs, first
    checks: `docker compose -f docker-compose.prod.yml ps` (all containers
    should say `Up`, not `Restarting`), then `docker compose -f
    docker-compose.prod.yml logs api --tail 50` for the real error.
