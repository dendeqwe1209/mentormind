# Classical NN review-risk — MentorMind

## Purpose
Prioritise Human-in-the-Loop review of AI-generated WorkProfile drafts. The model
does **not** approve, reject, or publish knowledge. Human review and evidence
linkage remain the sole source of publication authority.

## Design
- **Production candidate:** `mentormind.nn`: small 8→12→1 ReLU MLP with sigmoid
  scoring, CPU only (Python standard library).
- **Research baseline preserved:** `mentormind.qnn`: 8-qubit variational statevector
  simulation; disabled by default. Its API and CLI remain available.
- Both consume the same 8 pre-review features from `mentormind.qnn.features`:
  `vlm_confidence`, `segment_duration`, `keyframe_count`,
  `segment_count`, `transcript_present`, `transcript_length`,
  `actor_known`, `keyframe_density`.
- Both can train from the existing SQLite `qnn_review_samples` table; QNN
  naming is retained for compatibility with already-collected data.
- **Important:** the legacy label heuristic is currently `reject OR error_tags
  OR version_before_review > 1`. This is a *review-priority proxy*, not a
  ground-truth estimate of an objectively incorrect WorkProfile. Audit it
  against reviewer decisions before reporting any result.

## Usage
```sh
uv run knowhow nn status
uv run knowhow nn train --epochs 240 --hidden-units 12 --lr 0.025 --seed 42
```

The training command must run in an environment that can access the SQLite
`KNOWHOW_PROFILE_DB` where expert reviews were actually recorded. It writes the
model to `KNOWHOW_NN_MODEL_PATH` (default
`data/work/nn/review_risk_model.json`); on Railway ensure the path is on the
persisted `/app/data/work` volume. The default relative path is *not*
guaranteed to point into a volume in every deployment: set
`KNOWHOW_NN_MODEL_PATH=/app/data/work/nn/review_risk_model.json` there.

Requirements: at least 40 labeled records, at least 10 records per class.
Training performs a deterministic stratified 80/20 holdout and early stopping.
Report validation metrics as **preliminary**, not a production benchmark.
Do not train on customer data without the agreed data-retention policy.

## Read-only API
- `GET /nn/status`: training-data counts, model status and held-out metrics.
- `GET /nn/profiles/{profile_id}/risk`: review priority score and coarse
  low/medium/high label. Returns `available=false` if disabled or untrained;
  never fabricates a score.
- `GET /qnn/status` and `GET /qnn/profiles/{profile_id}/risk` are retained
  for isolated research comparison.

Score thresholds (0.35 / 0.65) are heuristic **not calibrated probabilities**.
Do not make publication, safety or worker-evaluation decisions from the score.

## Production and evaluation gates
1. Merge via code review after unit tests, lint, type-check and frontend build.
2. Deploy code with `KNOWHOW_NN_ENABLED=true` and
   `KNOWHOW_QNN_ENABLED=false`, but do not assert model readiness until
   training has completed.
3. Continue labeling WorkProfiles through normal Human Review. On errors in
   optional snapshot/label telemetry, preserve the reviewer action.
4. Perform a locked evaluation on independently held-out, later-reviewed
   profiles; report PR-AUC, Recall@K, precision, F1, calibration and latency.
   Compare against a simple deterministic score and the QNN research baseline.
5. Require a distinct approval before enabling automated review-order changes.
   No automated approval/rejection is implemented here.

## Railway awareness
The Railway service `mentormind-app` is configured to serve a React build and
FastAPI on one domain, using a persistent volume at `/app/data/work`.
Code deployments and model-artifact deployment are separate actions. The
presence of a successful deployment does not demonstrate VLM, RAG, or review
business flows are healthy; run end-to-end smoke tests with *synthetic* data.
