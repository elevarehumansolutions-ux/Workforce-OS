# Current Task

**M7 — AI Suggestions Engine — functionally complete, not yet merged.**
See `09_PROGRESS.md`'s M7 section for what's built; `08_DECISIONS.md`'s
2026-09-22 through 2026-09-28 entries for the reasoning behind every
decision made along the way. Branch: `m7-ai-suggestions`.

## What's left before this milestone closes

1. **Worker/beat restart — done (2026-09-28).** `docker compose up -d
   --force-recreate celery_worker celery_beat` run against dev; verified
   with `celery -A app.core.celery_app inspect registered`: both
   `generate_suggestions` and `quarterly_objective_review` now appear
   alongside the three pre-existing email tasks; Beat's log shows a clean
   start with no errors. **The VPS demo can't hit the same staleness bug**
   — its deploy pipeline (`.github/workflows/ci-cd.yml`'s `deploy` job)
   runs `docker compose ... up -d --build` on every merge to `main`, which
   always rebuilds the image and recreates every container fresh,
   `celery_worker`/`celery_beat` included. The staleness problem only
   happened locally this session because files were edited without a
   rebuild mid-session; a real deploy always rebuilds.
2. **New env vars are all safe to be absent on the VPS.** `ANTHROPIC_MODEL_FAST`,
   `ANTHROPIC_MODEL_STRONG`, and the three `AI_MAX_*` guardrail settings
   all have Python defaults in `config.py` — a missing var just falls back
   to the default, no crash. `Settings` also has `extra="ignore"`, so a
   leftover, now-unused `ANTHROPIC_MODEL=...` line in the server's
   `backend/.env` is harmless too. The one thing worth checking (not a
   crash risk, a functionality one): `ANTHROPIC_API_KEY` on the server —
   if it's still the placeholder, AI generation will fail at runtime with
   an auth error the moment it's triggered, worth confirming before the
   next demo. `anthropic==1.8.0` installs automatically via the deploy's
   `--build` step. The new migrations (incl. the `SECURITY DEFINER`
   function and the department-rename one, see item 4 below) apply
   automatically via the deploy's `alembic upgrade head` step.
3. **Tell Uche (frontend), non-blocking — doesn't hold up merging this
   milestone:** the client decides which endpoint to call —
   `POST .../approve` with no body when nothing changed, `POST .../edit`
   with only the changed fields otherwise (it must diff, not resend the
   whole form — `08_DECISIONS.md` 2026-09-24). Both list and review
   actions are open to `hr_administrator` **and** `business_executive`
   (2026-09-24/25).
4. **VPS deploy note:** migration `61454952170a` renames any pre-existing
   duplicate department names with a numeric suffix — expected on the next
   deploy, not a bug if display names change.
5. Standard workflow once the above are confirmed: review → commit → push
   → PR → merge → delete branch → branch for whatever's next per
   `09_PROGRESS.md` (M8 — KPIs).

## Nice-to-haves, not built (deliberately, not overlooked)

- Uniqueness for `locations.name` / `positions.title` — same gap as the
  department-name fix, less clear-cut, not requested.
- Per-org-plan model tiering (a paying customer getting the stronger
  model) — the `tier` argument leaves room for this later; not built.
- Filtering the Quarterly Review scan by `subscription_status` (skipping
  `cancelled`/`expired` orgs) — not requested, not built; every org is
  scanned today.

## Study material

A session-by-session study guide of everything decided, built, and
mistaken along the way on M7 lives at `.claude/study/M7_STUDY_GUIDE.md`
(git-ignored, not part of the public repo).
