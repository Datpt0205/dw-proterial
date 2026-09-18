#!/usr/bin/env bash
# SessionStart hook. Stdout is injected into the model's context at session start,
# so a new session begins knowing where the last one stopped instead of guessing
# from the diff. Registered in .claude/settings.json and invoked with an absolute
# path via $CLAUDE_PROJECT_DIR, because hooks resolve relative paths against the
# working directory rather than the project root.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$root" || exit 0

branch=$(git branch --show-current 2>/dev/null || echo "not a git repo")
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
recent=$(git log --oneline -5 2>/dev/null || echo "no commits")

plan="$root/.claude/PLAN.md"
if [ -f "$plan" ]; then
  plan_state=$(sed -n '1,40p' "$plan")
else
  plan_state=".claude/PLAN.md does not exist. Create it before starting multi-file work."
fi

# The migration head, because two people adding a migration in the same day is
# how this repository learned that alembic refuses a merged tree with "revision
# is present more than once" — and git reports no conflict, because the filenames
# differ. Knowing the head up front makes the next revision derivable.
head_rev=$(ls db/migrations/versions/*.py 2>/dev/null | tail -1 | xargs -r basename)

# Where this session started. The Stop hook compares HEAD against it to tell
# whether anything was committed, and therefore whether there is something this
# session learned that `.claude/PLAN.md` should now say. Written here because
# this is the only moment that knows "before".
git rev-parse HEAD > "$root/.claude/.session-head" 2>/dev/null || true

cat <<EOF
Branch: $branch
Uncommitted files: $dirty
Latest migration file: ${head_rev:-none}

Recent commits:
$recent

Current plan (.claude/PLAN.md, first 40 lines):
$plan_state

Before writing code, .claude/rules/failure-modes.md lists the seven shapes of bug
this repository has actually produced, with counts. Two of them are only findable
by running the thing rather than reasoning about it.

Before calling any feature finished, run the reviewing-feature-security skill
(.claude/skills/reviewing-feature-security/). It is not optional and it is not
something the user should have to ask for. A commit that changes behaviour is
also gated by .claude/hooks/pre-commit-gate.sh, which runs the mechanical
invariant checks itself and raises only the questions this diff earns.
EOF
exit 0
