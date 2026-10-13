#!/bin/sh
# Make the artifact folder writable by the unprivileged user, then drop root and run the command.
set -e
mkdir -p "$ARTIFACT_ROOT"
if [ "$(id -u)" = "0" ]; then
  find "$ARTIFACT_ROOT" -not -user app -exec chown app:app {} +
  exec setpriv --reuid=app --regid=app --init-groups "$@"
fi
exec "$@"
