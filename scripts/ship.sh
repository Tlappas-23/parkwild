#!/bin/sh
# Land the current working tree on main through the protected-branch flow:
# branch, commit, push, open a PR, auto-merge when CI is green. Direct pushes
# to main are refused by GitHub now that protection is on (SECURITY.md).
#
#   scripts/ship.sh "commit title" [body-file]
set -eu
TITLE="${1:?usage: ship.sh \"title\" [body-file]}"
BODY_FILE="${2:-}"
SLUG=$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | cut -c1-40 | sed 's/-$//')
BRANCH="ship/$(date +%Y%m%d-%H%M%S)-$SLUG"
git checkout -q -b "$BRANCH"
git add -A
if [ -n "$BODY_FILE" ]; then git commit -q -F "$BODY_FILE"; else git commit -q -m "$TITLE"; fi
git push -q -u origin "$BRANCH"
if [ -n "$BODY_FILE" ]; then
  gh pr create --title "$TITLE" --body-file "$BODY_FILE" --base main --head "$BRANCH" >/dev/null
else
  gh pr create --title "$TITLE" --body "$TITLE" --base main --head "$BRANCH" >/dev/null
fi
# Rebase merge keeps the linear history the branch rules require; --auto waits for the `test` check.
gh pr merge "$BRANCH" --auto --rebase >/dev/null
git checkout -q main
echo "PR opened for $BRANCH; auto-merge armed. Run: git pull --rebase origin main once it lands."
