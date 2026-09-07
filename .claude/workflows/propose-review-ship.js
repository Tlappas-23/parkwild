export const meta = {
  name: 'propose-review-ship',
  description: 'Propose a change, have it reviewed against the project rules, implement it, verify with the real checks, then commit and open an auto-merge pull request',
  whenToUse: 'A change to parkwild described in a sentence or two. args: { task: "...", maxRounds?: 2 }',
  phases: [
    { title: 'Propose', detail: 'one agent writes the proposal' },
    { title: 'Review', detail: 'a reviewer checks it against the rules and may send it back' },
    { title: 'Implement', detail: 'apply the approved proposal' },
    { title: 'Verify', detail: 'an independent check: diff, lint, tests, build' },
    { title: 'Ship', detail: 'commit, push, pull request, auto-merge' },
  ],
}

// How a change gets into parkwild when nobody is watching: a proposal, a
// review that can say no, an implementation, an independent verification with
// the same checks CI runs, and only then a commit and a pull request that
// merges itself once CI is green. Nothing here pushes to main directly.

const task = typeof args === 'string' ? args : args && args.task
if (!task) throw new Error('args.task is required: describe the change in a sentence or two')
const MAX_ROUNDS = (args && args.maxRounds) || 2
const ROOT = '/Users/thomaslappas/Desktop/NationalParksProject'

const RULES = `Project rules (from BUILD_SPEC.md, DECISIONS.md, SECURITY.md and the notes in EXPERIMENTS.md):
- Zero cost: no paid APIs, no keys in the app, nothing that wants a card. Never Google Maps or Street View.
- Obscured coordinates stay obscured; sensitive species keep their coarse or hidden positions.
- Every photograph and record is credited under its own licence. Model-predicted detections are never drawn or counted as human-verified. Never publish a recall figure.
- Narrative code standard: every numeric constant carries a tag comment on the line above (MEASURED, DERIVED, BORROWED, ASSUMED or ARBITRARY) with a reason; a superseded method keeps a _v1 copy or a comment saying why; module docstrings explain the problem; every change of substance gets a ledger entry in EXPERIMENTS.md (next E-number) with What / Kept / Unresolved, written in the first person, never quoting chat.
- Writing voice: first person in notes, never "the owner"; commit titles short and imperative; no em dashes in anything a visitor reads.
- Checks that must pass before shipping: make lint; .venv/bin/python -m pytest -q; and in app/: npm run lint, npm run format:check, npx tsc --noEmit -p ., npm test, npm run build.
- Never git add -A; stage explicit paths; never touch app/public/data or reports/ or data/; never force-push; never commit secrets; no new dependency without saying so in the proposal.
- Ship flow: a plain branch name from main (git checkout -b <name> origin/main after git fetch), one commit, git push -u, gh pr create with a plain description, gh pr merge --auto --rebase. Main is protected; CI decides.`

const PROPOSAL = {
  type: 'object',
  properties: {
    summary: { type: 'string', description: 'two or three sentences: what changes and why' },
    files: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, change: { type: 'string' } }, required: ['path', 'change'] } },
    tests: { type: 'string', description: 'which tests exist or are added, or why none' },
    ledger: { type: 'string', description: 'the EXPERIMENTS.md entry text, first person, What / Kept / Unresolved' },
    risks: { type: 'array', items: { type: 'string' } },
    commitTitle: { type: 'string', description: 'short, imperative, no ledger number' },
    branch: { type: 'string', description: 'plain kebab-case branch name' },
  },
  required: ['summary', 'files', 'tests', 'ledger', 'risks', 'commitTitle', 'branch'],
}
const REVIEW = {
  type: 'object',
  properties: {
    approved: { type: 'boolean' },
    blocking: { type: 'array', items: { type: 'string' }, description: 'each reason the proposal must change before it can proceed' },
    suggestions: { type: 'array', items: { type: 'string' } },
    reason: { type: 'string' },
  },
  required: ['approved', 'blocking', 'suggestions', 'reason'],
}
const IMPL = {
  type: 'object',
  properties: {
    changed: { type: 'array', items: { type: 'string' }, description: 'repo-relative paths touched' },
    checks: { type: 'array', items: { type: 'object', properties: { command: { type: 'string' }, passed: { type: 'boolean' }, note: { type: 'string' } }, required: ['command', 'passed'] } },
    notes: { type: 'string' },
  },
  required: ['changed', 'checks', 'notes'],
}
const VERIFY = {
  type: 'object',
  properties: {
    pass: { type: 'boolean' },
    failures: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['pass', 'failures', 'notes'],
}
const SHIP = {
  type: 'object',
  properties: {
    branch: { type: 'string' },
    commit: { type: 'string' },
    prUrl: { type: 'string' },
    autoMerge: { type: 'boolean' },
    notes: { type: 'string' },
  },
  required: ['branch', 'commit', 'prUrl', 'autoMerge', 'notes'],
}

const proposePrompt = (t, prev, review) => `You are proposing a change to the parkwild repository at ${ROOT} (read README.md, docs/ARCHITECTURE.md and the relevant code first; do not edit anything yet).
Task: ${t}
${RULES}
${prev ? `Your previous proposal:\n${JSON.stringify(prev, null, 2)}\nThe reviewer sent it back. Blocking: ${JSON.stringify(review.blocking)}. Suggestions: ${JSON.stringify(review.suggestions)}. Revise it.` : ''}
Write a concrete proposal: which files change and how, what is tested, the ledger entry text, the risks, a commit title and a branch name. Keep the change as small as the task allows.`

const reviewPrompt = (t, p) => `You are the reviewer for the parkwild repository at ${ROOT}. Read the proposal below against the rules and against the actual code (open the files it names; check the claims). Be strict: approve only a proposal you would merge yourself. Anything that violates a rule, misreads the code, skips tests where logic changes, forgets the ledger entry, adds cost, or widens scope is blocking.
Task: ${t}
${RULES}
Proposal:
${JSON.stringify(p, null, 2)}`

const implementPrompt = (t, p) => `Implement this approved proposal in the parkwild repository at ${ROOT}. Work on the current checkout of main (run: git -C ${ROOT} status --short first; the tree should be clean apart from reports/ and data/; if other files are modified, stop and report it in notes with changed=[]).
Task: ${t}
${RULES}
Proposal:
${JSON.stringify(p, null, 2)}
Make exactly the proposed change (small deviations are fine if the code demands them; say so in notes). Add the ledger entry to EXPERIMENTS.md above the "## Open questions" heading. Run every check listed in the rules and record each with passed true/false. Do not commit, do not stage, do not touch git beyond status and diff.`

const verifyPrompt = (t, p, impl) => `You are an independent verifier for the parkwild repository at ${ROOT}. Another agent implemented this proposal and reports the changes below. Do not trust the report: run git -C ${ROOT} status --short and git -C ${ROOT} diff yourself, read every changed file, and rerun every check in the rules. Fail it if: any check fails; a file outside the proposal changed without a stated reason; app/public/data, data/ or reports/ are staged or meant for commit; a constant has no tag; user-facing text contains an em dash; the ledger entry is missing or written in the third person; a secret or token appears; behaviour differs from the proposal.
Task: ${t}
${RULES}
Proposal:
${JSON.stringify(p, null, 2)}
Implementation report:
${JSON.stringify(impl, null, 2)}
Do not change any file. Report pass/fail with specific failures.`

const fixPrompt = (t, p, verify) => `The verifier failed the implementation of this proposal in the parkwild repository at ${ROOT}. Fix exactly these failures, rerun the checks, and report. Do not commit or stage.
Task: ${t}
${RULES}
Proposal:
${JSON.stringify(p, null, 2)}
Failures:
${JSON.stringify(verify.failures, null, 2)}`

const shipPrompt = (t, p, impl) => `Ship the verified change in the parkwild repository at ${ROOT}. Steps, in order, all from ${ROOT}:
1. git fetch -q origin
2. git checkout -q -b ${p.branch} origin/main  (if the name exists, append -2)
3. git add <exactly these paths>: ${JSON.stringify(impl.changed)}  (never git add -A; never anything under app/public/data, data/ or reports/)
4. git commit with the title "${p.commitTitle}" and a short body in the first person saying what changed and why (two to five lines). Follow the commit attribution rules of your environment.
5. git push -q -u origin ${p.branch}
6. gh pr create --title "${p.commitTitle}" --body-file <a temp file with a plain description: what changed, why, what was checked> --base main --head ${p.branch}
7. gh pr merge ${p.branch} --auto --rebase
8. git checkout -q main
Report the branch, the commit hash, the PR URL and whether auto-merge is armed. If any step fails, stop, leave the branch as it is, and say exactly what failed.`

phase('Propose')
let proposal = await agent(proposePrompt(task), { schema: PROPOSAL, phase: 'Propose', label: 'proposer' })
if (!proposal) return { status: 'failed', where: 'propose' }

phase('Review')
let review = null
let round = 0
for (;;) {
  review = await agent(reviewPrompt(task, proposal), { schema: REVIEW, phase: 'Review', label: `reviewer round ${round + 1}` })
  if (!review) return { status: 'failed', where: 'review' }
  if (review.approved || round >= MAX_ROUNDS) break
  round += 1
  log(`review round ${round}: sent back (${review.blocking.length} blocking)`)
  proposal = await agent(proposePrompt(task, proposal, review), { schema: PROPOSAL, phase: 'Propose', label: `proposer revision ${round}` })
  if (!proposal) return { status: 'failed', where: 'revise' }
}
if (!review.approved) {
  log('rejected after the last review round; nothing implemented')
  return { status: 'rejected', review, proposal }
}

phase('Implement')
let impl = await agent(implementPrompt(task, proposal), { schema: IMPL, phase: 'Implement', label: 'implementer' })
if (!impl || impl.changed.length === 0) return { status: 'failed', where: 'implement', impl }

phase('Verify')
let verify = await agent(verifyPrompt(task, proposal, impl), { schema: VERIFY, phase: 'Verify', label: 'verifier' })
if (verify && !verify.pass) {
  log(`verification failed (${verify.failures.length}); one fix round`)
  const fixed = await agent(fixPrompt(task, proposal, verify), { schema: IMPL, phase: 'Implement', label: 'fixer' })
  if (fixed) impl = { ...impl, changed: Array.from(new Set([...impl.changed, ...fixed.changed])), checks: fixed.checks, notes: impl.notes + ' | fix: ' + fixed.notes }
  verify = await agent(verifyPrompt(task, proposal, impl), { schema: VERIFY, phase: 'Verify', label: 'verifier, second pass' })
}
if (!verify || !verify.pass) {
  log('not shipped: the working tree keeps the changes for a person to look at')
  return { status: 'not-shipped', verify, impl, proposal }
}

phase('Ship')
const ship = await agent(shipPrompt(task, proposal, impl), { schema: SHIP, phase: 'Ship', label: 'shipper' })
return { status: ship && ship.autoMerge ? 'shipped' : 'ship-incomplete', ship, summary: proposal.summary, reviewRounds: round + 1 }
