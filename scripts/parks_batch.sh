#!/bin/sh
# Bring parks live unattended, in groups. For each park: the whole of Track A
# (iNaturalist research-grade and GBIF sightings, dedupe, export) unless the
# export already exists, then whichever of landmarks, roads, things to do and
# places is missing; after every GROUP parks, a data-only PR through
# publish_data.sh, so parks appear on the site as they finish rather than all
# at the end. Safe to restart: finished work is skipped. A park that fails is
# logged and skipped; the rest carry on. Logs: data/batch/<park>.log.
#
#   nohup scripts/parks_batch.sh key1 key2 ... > data/batch/batch.log 2>&1 &
#   GROUP=4 scripts/parks_batch.sh ...
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY=$ROOT/.venv/bin/python
GROUP=${GROUP:-6}
mkdir -p "$ROOT/data/batch"
log() { echo "=== $(date '+%Y-%m-%d %H:%M') $*"; }
publish() {
  log "publishing:$*"
  "$ROOT/scripts/publish_data.sh" "More parks:$*" "$@" >> "$ROOT/data/batch/publish.log" 2>&1 && log "PR opened" || log "publish failed (see data/batch/publish.log)"
}
pending=""; n=0
for p in "$@"; do
  d="$ROOT/data/export/$p"
  if [ -f "$d/species.json" ] && [ -f "$d/cells.geojson" ]; then
    log "$p: already exported; filling in what is missing"
  else
    log "$p: sightings (iNaturalist + GBIF), dedupe, export"
    if ! $PY "$ROOT/scripts/track_a.py" all --park "$p" > "$ROOT/data/batch/$p.log" 2>&1; then log "$p: Track A failed (see data/batch/$p.log); skipped"; continue; fi
  fi
  for step in landmarks:landmarks.json roads:roads.json amenities:amenities.json park-places:places.json climate:climate.json; do
    cmd=${step%%:*}; file=${step##*:}
    [ -f "$d/$file" ] && continue
    log "$p: $cmd"
    $PY "$ROOT/scripts/track_a.py" "$cmd" --park "$p" >> "$ROOT/data/batch/$p.log" 2>&1 || log "$p: $cmd failed (continuing)"
  done
  pending="$pending $p"; n=$((n + 1))
  if [ $((n % GROUP)) -eq 0 ]; then publish $pending; pending=""; fi
done
[ -n "$pending" ] && publish $pending
log "batch done"
