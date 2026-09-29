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

# The plan is an index read WHOLE, with detail in one file per area under
# .claude/plans/. A cut-off read (it used to be the first 40 lines) hides exactly
# what was added last, so the cap is on the file instead: past the limit this
# says so, rather than silently reading less.
plan="$root/.claude/PLAN.md"
plan_limit=80
if [ -f "$plan" ]; then
  plan_state=$(cat "$plan")
  plan_lines=$(wc -l < "$plan" | tr -d ' ')
  if [ "$plan_lines" -gt "$plan_limit" ]; then
    plan_state="$plan_state

WARNING: .claude/PLAN.md is $plan_lines lines (limit $plan_limit). It is an index;
move detail into the area file under .claude/plans/."
  fi
  # An area file the index does not name is one nobody will open.
  for area in "$root"/.claude/plans/*.md; do
    [ -e "$area" ] || continue
    name=".claude/plans/$(basename "$area")"
    grep -qF "$name" "$plan" || plan_state="$plan_state
WARNING: $name exists but .claude/PLAN.md does not name it."
  done
else
  plan_state=".claude/PLAN.md does not exist. Create it before starting multi-file work."
fi

# The migration head, because two people adding a migration in the same day is
# how this repository learned that alembic refuses a merged tree with "revision
# is present more than once" — and git reports no conflict, because the filenames
# differ. Knowing the head up front makes the next revision derivable.
#
# Read from the revision graph, not the file listing: a filename starts with
# alembic's random hex, so the last one alphabetically is not the newest (the
# listing once reported a revision three behind the real head). A head is a
# revision no file names as its down_revision; a merge's down_revision is a
# tuple, possibly over several lines. More than one head is itself the finding.
heads=$(awk '
  BEGIN { q = "[\"\047]"; id = q "[^\"\047]+" q }
  FNR == 1 { collecting = 0 }
  /^revision[[:space:]:=]/ {
    if (match($0, id)) rev[substr($0, RSTART + 1, RLENGTH - 2)] = FILENAME
  }
  /^down_revision[[:space:]:=]/ { collecting = 1; depth = 0 }
  collecting {
    line = $0
    while (match(line, id)) {
      down[substr(line, RSTART + 1, RLENGTH - 2)] = 1
      line = substr(line, RSTART + RLENGTH)
    }
    depth += gsub(/\(/, "(") - gsub(/\)/, ")")
    if (depth <= 0) collecting = 0
  }
  END {
    for (r in rev) if (!(r in down)) { n = split(rev[r], parts, "/"); print parts[n] }
  }
' "$root"/db/migrations/versions/*.py 2>/dev/null | sort)
head_count=$(printf '%s' "$heads" | grep -c .)
if [ "$head_count" -gt 1 ]; then
  head_rev="MULTIPLE HEADS, alembic will refuse to upgrade until they are merged: $(echo $heads)"
else
  head_rev="$heads"
fi

# Where this session started. The Stop hook compares HEAD against it to tell
# whether anything was committed, and therefore whether there is something this
# session learned that the plan (the index or an area file) should now say.
# Written here because this is the only moment that knows "before".
git rev-parse HEAD > "$root/.claude/.session-head" 2>/dev/null || true

cat <<EOF
Branch: $branch
Uncommitted files: $dirty
Migration head: ${head_rev:-none}

Recent commits:
$recent

Current plan (.claude/PLAN.md, the index; each area's detail is in .claude/plans/):
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
