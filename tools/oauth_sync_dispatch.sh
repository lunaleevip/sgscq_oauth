#!/bin/sh
set -eu

BASE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
TOKEN_FILE="${GITHUB_DISPATCH_TOKEN_FILE:-$BASE_DIR/github_dispatch_token}"
REPO="${GITHUB_REPO:-lunaleevip/sgscq_oauth}"
LOG="${SYNC_LOG:-$BASE_DIR/oauth-sync-dispatch.log}"
AFDIAN_FULL_STATE_FILE="${AFDIAN_FULL_SYNC_STATE_FILE:-$BASE_DIR/last-afdian-full-hour}"
BILI_INCREMENTAL_STATE_FILE="${BILI_INCREMENTAL_SYNC_STATE_FILE:-$BASE_DIR/last-bili-incremental-slot}"
BILI_FULL_STATE_FILE="${BILI_FULL_SYNC_STATE_FILE:-$BASE_DIR/last-bili-full-slot}"

if [ ! -r "$TOKEN_FILE" ]; then
  echo "$(date -Iseconds) missing github dispatch token file: $TOKEN_FILE" >> "$LOG"
  exit 1
fi

TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
if [ -z "$TOKEN" ]; then
  echo "$(date -Iseconds) empty github dispatch token file: $TOKEN_FILE" >> "$LOG"
  exit 1
fi

dispatch() {
  event="$1"
  out="$BASE_DIR/last-$event.out"
  payload="{\"event_type\":\"$event\",\"client_payload\":{\"source\":\"vps_cron\",\"time\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}}"
  code="$(curl -sS -o "$out" -w '%{http_code}' \
    -X POST "https://api.github.com/repos/$REPO/dispatches" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Accept: application/vnd.github+json' \
    -H 'Content-Type: application/json' \
    -H 'User-Agent: sgscq-oauth-vps-cron' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    -d "$payload")"
  if [ "$code" = "204" ]; then
    echo "$(date -Iseconds) $event dispatched" >> "$LOG"
    rm -f "$out"
    return 0
  fi
  echo "$(date -Iseconds) $event failed HTTP $code $(head -c 500 "$out" 2>/dev/null || true)" >> "$LOG"
  return 1
}

slot() {
  divisor="$1"
  day="$(date -u +%Y%m%d)"
  hour="$(date -u +%H)"
  hour="${hour#0}"
  if [ -z "$hour" ]; then
    hour=0
  fi
  printf '%s-%s\n' "$day" "$((hour / divisor))"
}

dispatch_hourly_afdian_full_if_due() {
  current_hour="$(date -u +%Y%m%d%H)"
  last_hour="$(cat "$AFDIAN_FULL_STATE_FILE" 2>/dev/null || true)"
  if [ "$last_hour" = "$current_hour" ]; then
    return 1
  fi

  if ! dispatch afdian_full; then
    return 1
  fi
  printf '%s\n' "$current_hour" > "$AFDIAN_FULL_STATE_FILE"
  return 0
}

dispatch_bili_if_due() {
  current_full_slot="$(slot 12)"
  last_full_slot="$(cat "$BILI_FULL_STATE_FILE" 2>/dev/null || true)"
  current_incremental_slot="$(slot 2)"
  last_incremental_slot="$(cat "$BILI_INCREMENTAL_STATE_FILE" 2>/dev/null || true)"

  if [ "$last_full_slot" != "$current_full_slot" ]; then
    dispatch bili_followers_full
    printf '%s\n' "$current_full_slot" > "$BILI_FULL_STATE_FILE"
    printf '%s\n' "$current_incremental_slot" > "$BILI_INCREMENTAL_STATE_FILE"
    return 0
  fi

  if [ "$last_incremental_slot" != "$current_incremental_slot" ]; then
    dispatch bili_followers
    printf '%s\n' "$current_incremental_slot" > "$BILI_INCREMENTAL_STATE_FILE"
    return 0
  fi

  echo "$(date -Iseconds) bili followers skipped; current 2h slot already dispatched" >> "$LOG"
  return 1
}

ran_afdian_full=0
if dispatch_hourly_afdian_full_if_due; then
  ran_afdian_full=1
fi

if [ "$ran_afdian_full" != "1" ]; then
  dispatch afdian_incremental
fi

dispatch_bili_if_due || true

# Douyin follower sync runs locally on the VPS because browser-signed
# follower URLs cannot be regenerated reliably by GitHub Actions.
