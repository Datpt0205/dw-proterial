#!/usr/bin/env bash
# PreToolUse(Bash) hook. Fires before a command runs; exit 2 blocks it and sends
# stderr back as feedback. Registered in .claude/settings.json.
#
# Why a hook and not a rule or a skill: both of those are advice, and advice is
# forgotten exactly when a change is large enough to matter. This runs at the one
# moment that cannot be skipped — the commit — and it runs the mechanical checks
# itself rather than asking for them to be remembered.
#
# It only speaks up for `git commit`. Every other command passes through.
#
# To disable: touch .claude/no-commit-gate
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$root" || exit 0

[ -f "$root/.claude/no-commit-gate" ] && exit 0

input=$(cat)

if command -v jq >/dev/null 2>&1; then
  command_line=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')
else
  command_line=$(printf '%s' "$input" | tr ',' '\n' | grep -o '"command"[^,]*' | head -1)
fi

case "$command_line" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

# --- the mechanical half: invariants this repository has actually broken ------
if ! invariants=$(uv run python scripts/verify_invariants.py 2>&1); then
  {
    echo "Repository invariants FAILED — do not commit this yet."
    echo
    printf '%s\n' "$invariants"
  } >&2
  exit 2
fi

# --- the judgement half: only the questions this diff actually raises ---------
staged=$(git diff --cached --name-only 2>/dev/null)
[ -z "$staged" ] && staged=$(git diff --name-only HEAD 2>/dev/null)
[ -z "$staged" ] && exit 0

questions=""
add() { questions="${questions}  - $1"$'\n'; }

if printf '%s' "$staged" | grep -q '^db/migrations/'; then
  add "A migration changed. Does every new tenant table have RLS enabled, forced
    and a policy, and a cross-tenant negative test? Does every new column with a
    fixed set of values have a CHECK constraint? Is every foreign key indexed on
    its own side, and is its ON DELETE deliberate?"
fi

if printf '%s' "$staged" | grep -qE 'executor\.py|autonomy\.py|langchain_tools\.py|sub_agents\.py|agent_factory\.py|approval'; then
  add "An approval or autonomy path changed. Does this widen what an agent does
    unasked? Is the gate tested where the effect happens, not only through the
    layer above it that would have caught it anyway? Mutation-check it: revert the
    gate and confirm a test goes red."
fi

if printf '%s' "$staged" | grep -qE 'membership_lookup|caching_lookup|access_context|identity\.py|auth|^apps/api/src/dw_api/routes/'; then
  add "An authorization path changed. Is the new field carried through the cache
    serialiser, and does a cache entry written before it existed read as the
    RESTRICTIVE value? Is there a negative test for the caller who should be
    refused? For a ROUTE: does every id in the path get checked against the
    caller's OWN tenant before anything acts on it, and does 'not yours' answer
    the same as 'never existed'?"
fi

if printf '%s' "$staged" | grep -qE 'memory|knowledge|evidence'; then
  add "Memory or knowledge changed. Is the write on the audit trail? Can the
    provenance chain still be walked in SQL from the stored item to the source?"
fi

if printf '%s' "$staged" | grep -qE 'Dockerfile|docker-compose'; then
  add "An image or compose file changed. Did you scan the built image
    (trivy, HIGH+ with a fix available)? Is every referenced image actually
    pullable, and does every service that runs submitted code still have its
    pids limit, read-only root and init?"
fi

if printf '%s' "$staged" | grep -qE '^\.github/workflows/|^Makefile$'; then
  add "A CI step changed. Did you watch a real run of it, or only read the YAML?
    A step can read as configured and never execute — the trivy gate downloaded a
    release tag that did not exist, curl without --fail piped the 404 page into
    tar, and the step reported a corrupt archive while scanning nothing. Confirm
    the step both RAN and can still go red."
fi

if printf '%s' "$staged" | grep -qE 'pyproject\.toml|package\.json|uv\.lock|pnpm-lock'; then
  add "A dependency changed. Did you RUN the new version rather than trust its
    docs — the list of what a library installs, and the behaviour you are
    relying on, are both free to change between releases."
fi

[ -z "$questions" ] && exit 0

# Raised once per change, not once per attempt. Blocking every retry would make
# the commit unreachable — the questions would be asked and never answerable.
# The marker is the diff itself: answer them, run the same commit again and it
# passes; change a file and they are asked again about the new state.
#
# This guarantees the questions are RAISED, which is the part that was being
# forgotten. It cannot guarantee they were answered honestly, and pretending
# otherwise would be the same decoration this repository keeps finding.
seen_file="$root/.claude/.commit-gate-seen"
fingerprint=$( (printf '%s' "$staged"; git diff --cached 2>/dev/null; git diff HEAD 2>/dev/null) | sha256sum | cut -d' ' -f1)
if [ -f "$seen_file" ] && [ "$(cat "$seen_file")" = "$fingerprint" ]; then
  exit 0
fi
printf '%s' "$fingerprint" > "$seen_file"

{
  echo "Before committing, answer these for the files in this change."
  echo "Answer them in your reply — if one does not apply, say why in one line."
  echo "Then run the same commit again; it will pass."
  echo
  printf '%s' "$questions"
  echo "Full list and the counts behind it: .claude/rules/failure-modes.md"
} >&2
exit 2
