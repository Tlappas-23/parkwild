#!/bin/sh
# The fortnightly refresh: for every live park, pull only the sightings that
# changed since the last run (iNaturalist updated_since, GBIF lastInterpreted),
# dedupe, re-export, rebuild the places, refresh the climate normals when they
# are older than a season, then publish one data PR for all of them. Cron runs
# it on the 1st and 15th at 03:00; it refuses to start while the park batch
# holds the database, and never runs twice at once.
#
#   scripts/refresh.sh            # normal
#   SINCE=2026-08-01 scripts/refresh.sh
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY=$ROOT/.venv/bin/python
STATE=$ROOT/data/batch
mkdir -p "$STATE"
LOCK=$STATE/refresh.lock
log() { echo "=== $(date '+%Y-%m-%d %H:%M') $*"; }
if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then log "already running; exit"; exit 0; fi
echo $$ > "$LOCK"; trap 'rm -f "$LOCK"' EXIT
if pgrep -f "scripts/parks_batch.sh" >/dev/null; then log "the park batch holds the database; try again next time"; exit 0; fi
NOW=$(date +%F)
SINCE=${SINCE:-$(cat "$STATE/last_refresh" 2>/dev/null || date -v-30d +%F)}
log "refresh since $SINCE"
PARKS=""
for d in "$ROOT"/data/export/*/; do
  p=$(basename "$d")
  [ -f "$d/species.json" ] || continue
  log "$p: sightings since $SINCE"
  $PY "$ROOT/scripts/track_a.py" ingest --park "$p" --since "$SINCE" > "$STATE/refresh_$p.log" 2>&1 || { log "$p: ingest failed (see refresh_$p.log)"; continue; }
  $PY "$ROOT/scripts/track_a.py" dedupe --park "$p" >> "$STATE/refresh_$p.log" 2>&1 || log "$p: dedupe failed"
  $PY "$ROOT/scripts/track_a.py" export --park "$p" >> "$STATE/refresh_$p.log" 2>&1 || { log "$p: export failed"; continue; }
  $PY "$ROOT/scripts/track_a.py" park-places --park "$p" >> "$STATE/refresh_$p.log" 2>&1 || log "$p: places failed"
  if [ ! -f "$d/climate.json" ] || [ -n "$(find "$d/climate.json" -mtime +90 2>/dev/null)" ]; then
    $PY "$ROOT/scripts/track_a.py" climate --park "$p" >> "$STATE/refresh_$p.log" 2>&1 || log "$p: climate failed"
  fi
  PARKS="$PARKS $p"
done
[ -n "$PARKS" ] && { log "publishing"; "$ROOT/scripts/publish_data.sh" "Fortnightly refresh: sightings since $SINCE" $PARKS >> "$STATE/publish.log" 2>&1 && log "PR opened" || log "publish failed"; }
echo "$NOW" > "$STATE/last_refresh"
log "done"
