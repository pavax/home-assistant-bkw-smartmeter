#!/usr/bin/env bash
# Verify bkw_smartmeter in Home Assistant (Docker).
# From repo root: ./scripts/verify-docker.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERIFY_DIR="${ROOT}/scripts/mybkw-verification"
COMPOSE_FILE="${VERIFY_DIR}/docker-compose.yml"

dc() {
  docker compose -f "${COMPOSE_FILE}" --project-directory "${VERIFY_DIR}" "$@"
}

echo "==> Starting Home Assistant (first start may take 2–3 minutes)"
dc up -d --remove-orphans

deadline=$((SECONDS + 300))
until curl -sf -o /dev/null http://127.0.0.1:8123/; do
  if (( SECONDS > deadline )); then
    echo "Home Assistant did not become ready within 5 minutes." >&2
    dc logs --tail 80 homeassistant
    exit 1
  fi
  sleep 5
done
echo "Home Assistant UI is up."

echo "==> Running configuration check inside container"
dc exec -T homeassistant python -m homeassistant --config /config --script check_config

echo "==> Scanning logs for bkw_smartmeter load errors"
logs=$(dc logs homeassistant 2>&1 || true)
for pat in \
  "Error loading custom integration bkw_smartmeter" \
  "Setup failed for custom integration bkw_smartmeter" \
  "Unable to import custom integration bkw_smartmeter"; do
  if echo "$logs" | grep -Fq "$pat"; then
    echo "Found integration error: ${pat}" >&2
    dc logs --tail 50 homeassistant | grep -i bkw_smartmeter || true
    exit 1
  fi
done

echo "==> Done"
echo "Open http://127.0.0.1:8123 → Add integration → BKW Smart Meter"
echo "Stop: docker compose -f scripts/mybkw-verification/docker-compose.yml --project-directory scripts/mybkw-verification down"
