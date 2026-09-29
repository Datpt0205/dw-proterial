#!/usr/bin/env bash
# Stop hook. Runs when the model finishes a turn. Exit 2 sends stderr back as
# feedback and asks it to keep working; exit 0 lets the turn end.
#
# What it is for: a session that ends with the work committed but the plan
# describing the previous state has lost what it learned, however good the code is.
# The next session reads the plan and believes it. The plan is `.claude/PLAN.md`
# (the index) plus one file per area under `.claude/plans/`; updating either counts.
#
# To disable without editing settings: touch .claude/no-stop-gate
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$root" || exit 0

[ -f "$root/.claude/no-stop-gate" ] && exit 0

input=$(cat)

# Guard against a loop: if this hook already fired for this turn, let it end.
# jq is preferred; the grep fallback keeps the guard working without it — a hook
# that fails open into an infinite loop is worse than one that does not run.
if command -v jq >/dev/null 2>&1; then
  active=$(printf '%s' "$input" | jq -r '.stop_hook_active // false')
else
  active=$(printf '%s' "$input" | grep -o '"stop_hook_active"[[:space:]]*:[[:space:]]*true' >/dev/null && echo true || echo false)
fi
[ "$active" = "true" ] && exit 0

git rev-parse --git-dir >/dev/null 2>&1 || exit 0

changed=$(git status --porcelain | wc -l | tr -d ' ')

# Nothing uncommitted, but did this session COMMIT something without saying what
# it learned? That is the quieter half of the same loss: the code is safe, the
# reasoning behind it is not, and the next session reads a plan describing the
# state before any of it happened.
if [ "$changed" -eq 0 ]; then
  started=$(cat "$root/.claude/.session-head" 2>/dev/null || true)
  [ -z "$started" ] && exit 0
  git cat-file -e "$started^{commit}" 2>/dev/null || exit 0
  [ "$started" = "$(git rev-parse HEAD)" ] && exit 0
  if git diff --name-only "$started"..HEAD | grep -qE '^\.claude/(PLAN\.md|plans/[^/]+\.md)$'; then
    exit 0
  fi
  {
    echo "This session committed $(git rev-list --count "$started"..HEAD) change(s)"
    echo "and touched neither .claude/PLAN.md nor an area file in .claude/plans/."
    echo
    echo "The code is safe; what was learned making it is not. Update the plan so"
    echo "the next session reads where the work actually stands — what is done,"
    echo "what is open, what was measured and found NOT to be true, and any"
    echo "decision the user still owes. Then commit that too."
    echo
    echo "If this session genuinely learned nothing worth recording, say so and"
    echo "end the turn; this fires once."
  } >&2
  exit 2
fi

{
  echo "There are $changed uncommitted file(s)."
  echo "Before ending the turn: commit them with a Conventional Commits message,"
  echo "and update the plan so it describes where the work now stands — what was"
  echo "done, what is open, and any decision the user still owes: the area file in"
  echo ".claude/plans/, and .claude/PLAN.md (the index) if the state, the next"
  echo "step or a decision owed changed."
  echo "If the work is deliberately incomplete, say so explicitly rather than"
  echo "committing it as if it were finished."
} >&2
exit 2
