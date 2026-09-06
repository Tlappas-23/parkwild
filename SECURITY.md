# Security model

The requirement, in the owner's words: "tight security so no one can write over
what I build." Reads of the finished app are public by design (BUILD_SPEC.md:
"publicly reachable", "no auth"). Everything that can *change* what is
published is locked to one person. A free read gate exists if the owner wants
it; see the last section.

## What is protected, from what

| Asset | Threat | Control |
|---|---|---|
| Source code | someone else pushing, force-pushing, or deleting | public repository with one writer, 2FA, protected `main`, required checks |
| Secrets (`MAPILLARY_TOKEN`) | committed by accident, leaked in CI logs | gitignored `.env`, pre-commit secret scan, CI secret scan, never echoed |
| Raw model output | overwritten by a rerun or a "fix" | `predictions_raw` / `detections_raw` are append-only (`INSERT OR IGNORE`); corrections live in `manual_review` |
| Published data files | tampered after build | `manifest.json` with SHA-256 per file and the git commit; the app checks hashes before using data |
| Deployed site | deployed from an unreviewed branch, or by someone else | static site, deploy only from protected `main` via CI, deploy tokens only in Actions secrets |
| Runtime | injection, framing, third-party scripts | no server, no write path, strict CSP, no CDN scripts; the two MapLibre popups built from data go through one HTML escaper (`app/src/html.ts`) |

## Source control

- Repo is public (decision O-7, 2026-09-05): that is what makes server-side branch protection free. Only the owner's account has write access; nothing secret is in it, and history was checked for the token before the flip.
- 2FA on the GitHub account (Settings > Password and authentication).
- Server-side protection of `main` (status checks required, no force-push, no
  deletion) is applied with `make protect REPO=owner/name`. **GitHub does not
  offer branch protection or rulesets on a free private repository** (checked
  2026-09-05: HTTP 403 "Upgrade to GitHub Pro or make this repository public").
  Applied on 2026-09-05 once the repo went public. The local `pre-push` hook
  (`make hooks`) stays as a second layer: it refuses non-fast-forward pushes
  to `main` and any push when lint, tests, smoke or the secret scan fail.
- `.github/CODEOWNERS` names the owner for every path.
- Commit signing is recommended, not required: `git config commit.gpgsign true`
  with an SSH or GPG key registered on GitHub.

Landing changes: `scripts/ship.sh "title"` branches, pushes, opens a PR and
arms auto-merge; the `test` check must pass first. `make ship TITLE=...`.

## Secrets

- `.env` is gitignored. `make hooks` installs a pre-commit hook that runs
  `scripts/check_secrets.py --staged`; it refuses commits containing a Mapillary
  token (`MLY|...`), private keys, GitHub or AWS tokens, or any `.env` file.
  CI runs the same scan across the whole tree on every push.
- The Mapillary client token is read-only for public data. If it leaks, revoke
  and regenerate it in the Mapillary developer dashboard. It was pasted into a
  chat once during setup; rotate it before launch.
- Nothing in CI needs the token. Tests run offline against fixtures.

## Data integrity

- Raw model tables never change once written. A rerun over the same image with
  the same model version is a no-op; a new model version is a new row.
- Every ingest and filter appends a line to `reports/decision_log.jsonl` with
  rows in, rows out, and the rule, so a missing population is explainable.
- Stage-boundary contracts (`parkwild/contracts.py`) assert coordinate ranges,
  normalised boxes, millisecond timestamps, and row conservation.
- Exports carry `manifest.json`: SHA-256 per file, build time, git commit.

## Deployment (Phase 5+)

- Static files only. No API, no database, no writable surface at runtime.
- Cloudflare Pages (or GitHub Pages) deploys from `main` only; preview deploys
  from branches are fine because they are not the production URL.
- `_headers` sets `Content-Security-Policy: default-src 'self'; img-src 'self'
  data: <tile host>; connect-src 'self' <tile host>; frame-ancestors 'none'`,
  plus `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  strict-origin-when-cross-origin`, `Permissions-Policy` denying sensors.
- All JS is bundled; no third-party script tags. Dependencies pinned via
  lockfile; Dependabot alerts on.

## Optional read gate, zero cost

Cloudflare Access (Zero Trust free plan, up to 50 users) can sit in front of the
Pages site with no code changes. Viewers sign in with an emailed one-time code,
GitHub, or Google. The installed PWA keeps working offline from cache; fresh
data fetches need a session. This contradicts "publicly reachable" in the spec,
so it is a decision for the owner (DECISIONS.md, ADR-0008), off by default.

## Not covered

- Loss of the local machine: `data/` is regenerable from the scripts, but the
  hand-entered `review.csv` files are committed so they survive.
- Reuse of the published dataset: it is derived from CC BY-SA and CC-licensed
  sources and is meant to be reused, with attribution.

## Controls in place (checked 2026-09-06)

Reads are public by design; everything that changes what is published is
locked to one account. The repository stays public so that server-side
branch protection is free.

| Layer | Control | State |
|---|---|---|
| `main` | protected: required checks `test` (Python) and `app` (typecheck, tests, lint, format, build), strict up-to-date, linear history, conversation resolution, no force-push, no deletion, rules enforced for admins | on |
| Account | two-factor authentication; only the owner has write access; `CODEOWNERS` names the owner for every path | on |
| Secrets | `.env` gitignored; pre-commit and CI secret scan; GitHub secret scanning with push protection and non-provider patterns | on |
| Dependencies | Dependabot security updates; weekly Dependabot pull requests for npm, pip and Actions; `npm audit` clean | on |
| Code scanning | CodeQL default setup for TypeScript and Python on every pull request | on |
| Actions | every action pinned to a commit SHA; workflow token read-only by default; the Pages job alone gets `pages: write` and `id-token: write` | on |
| Reporting | private vulnerability reporting on the repository; `/.well-known/security.txt` on the site points to it | on |
| Runtime | no server, no write path, no accounts, no third-party scripts; Content Security Policy in the page; every data file hash-checked against a manifest compiled into the app; geolocation only on a tap | on |
| Signed commits | not required yet: the owner has no signing key registered. Once one is added on GitHub, `required_signatures` on `main` is one API call (`make protect`) | off |

What a static host cannot do: GitHub Pages sends no custom response
headers, so `frame-ancestors`, `Cross-Origin-Opener-Policy` and
`X-Content-Type-Options` in `app/public/_headers` only take effect on a host
that reads that file (Cloudflare Pages, also free). The page-level policy
covers scripts, connections, images and workers. Open decision O-11.
