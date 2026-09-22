#!/bin/sh
# Renders alertmanager.yml.template into /out/alertmanager.yml, substituting
# the one placeholder with $ALERTMANAGER_WEBHOOK_URL. A plain file rather than
# an inline `entrypoint:` string in docker-compose.yml: the escaping needed to
# survive both Compose's own $$ handling and the shell in one YAML string is
# exactly the kind of thing that looks right and silently isn't — measured
# once already while writing this (the first version left the literal
# placeholder text `${ALERTMANAGER_WEBHOOK_URL}` in the rendered file because
# it sat inside single quotes, so nothing ever expanded it).
set -eu

if [ -z "${ALERTMANAGER_WEBHOOK_URL:-}" ]; then
  # No webhook configured yet: keep the `webhook` receiver (so
  # `route.receiver: webhook` still resolves) but drop its one integration.
  # A receiver with zero configured integrations is valid Alertmanager
  # config — "matched, delivered nowhere" — but a `webhook_configs` entry
  # with an empty url is NOT: Alertmanager refuses to start on it
  # ("unsupported scheme \"\" for URL", crash-looping the container) —
  # measured, not assumed, while writing this.
  sed '/webhook_configs:/,/send_resolved: true/d' /template/alertmanager.yml.template > /out/alertmanager.yml
else
  # Escape sed's own special replacement characters (the `|` delimiter this
  # script uses, `&` which sed reads as "the matched text", and `\`) so a
  # webhook URL containing any of them substitutes as literal text instead
  # of corrupting the output.
  esc_url=$(printf '%s' "$ALERTMANAGER_WEBHOOK_URL" | sed -e 's/[&|\]/\\&/g')
  sed "s|__ALERTMANAGER_WEBHOOK_URL__|$esc_url|" /template/alertmanager.yml.template > /out/alertmanager.yml
fi
