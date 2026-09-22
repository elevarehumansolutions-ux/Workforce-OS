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
- `ENVIRONMENT` — `production` (this is what flips the refresh-token cookie's `Secure` flag — see `03_ARCHITECTURE.md`; leave it `production` even though this is a demo box, since it's genuinely reachable over the internet)
- `CORS_ALLOWED_ORIGINS` — the frontend's real Vercel URL, as a JSON list, never a wildcard
- `APP_URL` — `http://<server-ip>` (or the domain, once one exists)
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

## Adding a domain later (optional, recommended)

IP-only mode means login traffic is unencrypted (see `Caddyfile`'s own
comment). To add a domain:
1. Buy a cheap domain, point an A record at the server's IP.
2. Edit `Caddyfile`: replace `:80` with the domain name.
3. `git push` (or just edit directly on the server and
   `docker compose -f docker-compose.prod.yml restart caddy`) — Caddy
   automatically requests and renews a free Let's Encrypt certificate, no
   other change needed.
4. Update `CORS_ALLOWED_ORIGINS`/`APP_URL` in `backend/.env` if the
   frontend's origin or this API's own public URL changes.

## What this environment deliberately does not include

Matches `09_PROGRESS.md`'s M15 entry, which this pulled a subset out of —
the rest stays for later, not because it's forgotten:
- No seed script / demo data with historical scoring periods.
- No confirmed database backup strategy (the `postgres_data` volume
  persists across redeploys, but nothing ships it off the box).
- No investor-facing polish pass — this is an internal working
  environment, not the demo environment M15 describes.
- No staging/production split — one box, one environment.
