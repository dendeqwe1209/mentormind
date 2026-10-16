#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
WORK_DIR="${KNOWHOW_WORK_DIR:-/app/data/work}"
PROFILE_DB="${KNOWHOW_PROFILE_DB:-${WORK_DIR}/profiles.sqlite}"
mkdir -p "$WORK_DIR" "$(dirname "$PROFILE_DB")"

CONTRACT_PATH="/app/docs/contracts/work_profile.schema.json"
if [[ ! -f "$CONTRACT_PATH" ]]; then
  echo "[railway] Missing WorkProfile contract: $CONTRACT_PATH" >&2
  exit 1
fi
echo "[railway] WorkProfile contract ready."


# Safe diagnostics: never print the secret value.
echo "[railway] Provider auth diagnostics..."
python - <<'PY'
import os
from mentormind.core.config import get_settings
from mentormind.core.providers.vlm.factory import vlm_config_from_settings

s = get_settings()
cfg = vlm_config_from_settings(s)
raw = (os.getenv("OPENROUTER_API_KEY") or "").strip()
resolved = cfg.api_key.get_secret_value().strip() if cfg.api_key else ""
print(
    "[railway] VLM provider=%s model=%s OPENROUTER_API_KEY_present=%s KNOWHOW_VLM_API_KEY_present=%s resolved_key_present=%s"
    % (
        s.vlm_provider,
        s.vlm_model,
        bool(raw),
        bool((os.getenv("KNOWHOW_VLM_API_KEY") or "").strip()),
        bool(resolved),
    ),
    flush=True,
)
PY

if [[ "${KNOWHOW_VLM_PROVIDER:-}" == "openrouter" ]]; then
  if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    OPENROUTER_AUTH_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' \
      -H "Authorization: Bearer ${OPENROUTER_API_KEY}" \
      https://openrouter.ai/api/v1/key || true)"
    echo "[railway] OpenRouter auth probe HTTP ${OPENROUTER_AUTH_STATUS}"
  else
    echo "[railway] OpenRouter auth probe skipped: OPENROUTER_API_KEY is empty"
  fi
fi

if [[ "${KNOWHOW_BOOTSTRAP_DATABASES:-true}" == "true" && -n "${KNOWHOW_PG_DSN:-}" ]]; then
  echo "[railway] Initialising PostgreSQL/pgvector schema..."
  for i in $(seq 1 30); do
    if psql "$KNOWHOW_PG_DSN" -v ON_ERROR_STOP=1 -f /app/infra/postgres/init.sql >/tmp/pg-init.log 2>&1; then
      echo "[railway] PostgreSQL ready."
      break
    fi
    if [[ "$i" == "30" ]]; then
      cat /tmp/pg-init.log >&2 || true
      echo "[railway] PostgreSQL bootstrap failed." >&2
      exit 1
    fi
    sleep 2
  done
fi

if [[ "${KNOWHOW_BOOTSTRAP_DATABASES:-true}" == "true" && -n "${KNOWHOW_NEO4J_URI:-}" ]]; then
  echo "[railway] Initialising Neo4j schema..."
  for i in $(seq 1 30); do
    if knowhow kg init >/tmp/neo4j-init.log 2>&1; then
      echo "[railway] Neo4j ready."
      break
    fi
    if [[ "$i" == "30" ]]; then
      cat /tmp/neo4j-init.log >&2 || true
      echo "[railway] Neo4j bootstrap failed." >&2
      exit 1
    fi
    sleep 2
  done
fi

echo "[railway] Starting MentorMind on port ${PORT}..."
exec uvicorn mentormind.backend.app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips='*'
