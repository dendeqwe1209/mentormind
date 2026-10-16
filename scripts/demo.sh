#!/usr/bin/env bash
# `make demo` — the end-to-end flow of spec 08 §4 (PRD-AC-01, spec 08 AC-07).
#
# Preflight first: every command the flow needs is checked with `--help`. Until a module lands
# its command is missing, and the demo stops BEFORE starting anything, printing which spec/task
# still owes it — it never reports a partial run as success.
#
#   KNOWHOW_DEMO_OFFLINE=1 (default when no cloud key is set): fake VLM/LLM, no network.
set -euo pipefail
cd "$(dirname "$0")/.."

KNOWHOW="uv run --quiet knowhow"
SAMPLES=data/samples
API=http://127.0.0.1:${KNOWHOW_API_PORT:-8000}

if [[ -z "${KNOWHOW_DEMO_OFFLINE:-}" ]]; then
  if [[ -n "${DASHSCOPE_API_KEY:-}${OPENROUTER_API_KEY:-}${SILICONFLOW_API_KEY:-}" ]]; then
    KNOWHOW_DEMO_OFFLINE=0
  else
    KNOWHOW_DEMO_OFFLINE=1
  fi
fi
if [[ "$KNOWHOW_DEMO_OFFLINE" == "1" ]]; then
  export KNOWHOW_VLM_PROVIDER=fake KNOWHOW_LLM_PROVIDER=fake
  echo "[demo] chế độ offline: VLM/LLM giả lập, không gọi mạng."
fi

# ---- preflight ---------------------------------------------------------------------------
# "group command | owner" for every step below.
REQUIRED=(
  "kg init|spec 05 T05-1"
  "sigma gen-mock|spec 07"
  "kg load-sigma|spec 05/07"
  "ingest run|spec 02"
  "ingest index|spec 02 T02-6"
  "video segment|spec 03"
  "vlm describe|spec 04"
  "agent ask|spec 06"
  "agent rca|spec 06"
)
missing=0
for entry in "${REQUIRED[@]}"; do
  cmd=${entry%%|*}
  owner=${entry##*|}
  # shellcheck disable=SC2086
  if $KNOWHOW $cmd --help >/dev/null 2>&1; then
    printf '  [x] knowhow %-16s\n' "$cmd"
  else
    printf '  [ ] knowhow %-16s chưa có (%s)\n' "$cmd" "$owner"
    missing=$((missing + 1))
  fi
done
for file in "$SAMPLES/review_decisions.json"; do
  if [[ -f "$file" ]]; then
    printf '  [x] %s\n' "$file"
  else
    printf '  [ ] %s chưa có (spec 08 T08-6)\n' "$file"
    missing=$((missing + 1))
  fi
done
if ((missing > 0)); then
  echo "[demo] DỪNG: còn $missing mục chưa có — chưa chạy bước nào." >&2
  exit 1
fi

# ---- 1. infrastructure + Sigma mock ------------------------------------------------------
make up
$KNOWHOW kg init
$KNOWHOW sigma gen-mock
$KNOWHOW kg load-sigma --classification synthetic

# ---- 2. documents ------------------------------------------------------------------------
$KNOWHOW ingest run "$SAMPLES/docs" --classification synthetic
$KNOWHOW ingest index

# ---- 3. videos: segment -> describe (drafts) ---------------------------------------------
shopt -s nullglob
for video in "$SAMPLES"/video/*.{mp4,mov,mkv,webm}; do
  $KNOWHOW video segment "$video" --classification synthetic
done
for segments in data/work/video/*/segments.json; do
  $KNOWHOW vlm describe --segments "$segments"
done

# ---- 4. simulated expert review through the API (spec 08 §2) -----------------------------
uv run --quiet uvicorn mentormind.backend.app.main:app --port "${API##*:}" &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do curl -fs "$API/health" >/dev/null && break; sleep 1; done
uv run --quiet python - "$API" "$SAMPLES/review_decisions.json" <<'PY'
import json, sys, urllib.request

api, path = sys.argv[1], sys.argv[2]
for decision in json.load(open(path, encoding="utf-8")):
    profile_id = decision.pop("profile_id")
    request = urllib.request.Request(
        f"{api}/profiles/{profile_id}/review",
        data=json.dumps(decision).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(request).read()
    print(f"[demo] {decision['action']} {profile_id}")
PY

# ---- 5. questions + RCA, then the UI -----------------------------------------------------
$KNOWHOW agent ask "Bước đặt linh kiện A làm thế nào?" --process PACK01
$KNOWHOW agent ask "Vì sao phải đặt linh kiện A nghiêng?" --process PACK01
$KNOWHOW agent ask "Giá cổ phiếu DENSO hôm nay?" --process PACK01
$KNOWHOW agent rca --lot "$($KNOWHOW sigma lots --process PACK01 | head -n 1)"
echo "[demo] xong. UI: http://localhost:5173 (cd mentormind/frontend && npm run dev)"
