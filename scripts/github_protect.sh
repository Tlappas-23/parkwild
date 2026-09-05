#!/bin/sh
# Lock the main branch of a GitHub repo so only reviewed, CI-passing commits
# land on it, and nobody (admins included) can force-push or delete it.
# Usage: scripts/github_protect.sh owner/repo      (needs `gh auth login`)
set -eu
REPO="${1:?usage: github_protect.sh owner/repo}"

# Branch protection. required_pull_request_reviews is left off on purpose: a
# solo owner cannot approve their own PR, and the CI check plus single-writer
# access already stop anyone else. Turn reviews on when a second person joins.
gh api -X PUT "repos/$REPO/branches/main/protection" --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "contexts": ["test"] },
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": true,
  "required_conversation_resolution": true
}
JSON

# Dependabot vulnerability alerts.
gh api -X PUT "repos/$REPO/vulnerability-alerts" >/dev/null
echo "main on $REPO is protected; Dependabot alerts on"
