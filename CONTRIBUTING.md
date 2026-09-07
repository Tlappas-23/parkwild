# Contributing to parkwild

This is how a change lands here. I wrote it for myself and for anyone, person
or agent, working in this repository unattended. `main` is protected: nothing
reaches it except a pull request whose checks are green, and CI decides, not me.

## Before opening a pull request

Run the checks CI runs, from the repository root:

```bash
make lint                              # ruff, and every constant tagged
.venv/bin/python -m pytest -q          # offline tests on fixtures
cd app
npm run lint && npm run format:check   # ESLint at zero warnings, Prettier
npx tsc --noEmit -p .                  # typecheck
npm test && npm run build              # unit tests, then the production build
```

CI also runs the secret scan and the fixture smoke run. `make hooks` installs
a pre-commit secret scan and a pre-push hook that runs the scan, ruff, pytest
and the smoke run, but not the provenance check or the app checks.

## How a change lands

1. `git fetch origin && git checkout -b <plain-name> origin/main`. A short
   kebab-case name; the branch always starts from `origin/main`.
2. One commit. Stage paths by name (`git add path/to/file`), never `git add -A`,
   and never `app/public/data/`, `reports/` or `data/`: park data lands through
   `scripts/publish_data.sh` from its own worktree, the background jobs write
   `reports/`, and `data/` is gitignored apart from the review verdicts.
3. A short, imperative commit title ("Add the climate file", not "Added" or
   "Adds"). The body says what was verified.
4. `git push -u origin <plain-name>`, then `gh pr create` with a plain
   description and `gh pr merge --auto --rebase`. The merge happens on its own
   once the `test` and `app` checks pass. Never force-push; history is linear.
5. After it merges, `git checkout main && git pull --ff-only origin main`.
   Local `main` never has commits of its own, so a fast-forward always works.

`scripts/ship.sh "title"` is the shortcut: it branches from the current HEAD
as `ship/<timestamp>-<slug>`, commits everything with `git add -A`, rebases
onto `origin/main`, then pushes and opens the pull request. Because of the
`git add -A`, I only use it when no background job is writing files.

## The notebook conventions

- Every change of substance gets a ledger entry in `EXPERIMENTS.md` under the
  next E-number, with **What**, **Kept** and **Unresolved**, in the first
  person, never quoting a conversation. Negative results are entries too.
- Every numeric constant in `src/parkwild` and `scripts` carries a tag on the
  line above it, `MEASURED`, `DERIVED`, `BORROWED`, `ASSUMED` or `ARBITRARY`,
  with the reason and what would change it. `make lint` refuses untagged ones.
- A superseded method keeps a `_v1` copy with a comparison test, or a comment
  saying why it went. Module docstrings explain the problem, not the code.
- Notes are in my voice: first person, never "the owner". Nothing a visitor
  reads (the app, the README, the About page) uses an em dash.
- A new dependency is named in the proposal before it is added.

## What I will not merge

No paid API, no key in the app, nothing that asks for a card, and never Google
Maps or Street View. Obscured coordinates stay obscured and sensitive species
keep their coarse or hidden positions. Every photograph and record keeps its
own licence and credit. Model-predicted detections are never drawn or counted
as human-verified, and no recall figure is ever published. `SECURITY.md` and
`DECISIONS.md` have the reasoning.

## Unattended changes

`.claude/workflows/propose-review-ship.js` runs a change through five phases:
Propose, Review, Implement, Verify, Ship. A reviewer checks the proposal
against the rules above and can send it back; the implementer edits without
staging or committing; an independent verifier reruns every check in this
file; only then does the ship phase commit and open the pull request as
above. A failed verification leaves the edits uncommitted for a person to see.
