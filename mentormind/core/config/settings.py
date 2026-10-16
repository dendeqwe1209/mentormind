"""Settings read from ``KNOWHOW_*`` environment variables (spec 01 FR-03).

Sources, later wins: ``.env`` at the repo root (gitignored; ``.env.example`` is the template),
then the real process environment. ``.env`` holds the vendor API keys too — ``.secrets/README.md``
is only the guide for obtaining them. Every module reads configuration through
:func:`get_settings` — never ``os.environ`` directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
#: The one dotenv file: ``KNOWHOW_*`` settings and the vendor API keys live side by side.
ENV_FILE = REPO_ROOT / ".env"

JsonMode = Literal["auto", "json_schema", "json_object", "off"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KNOWHOW_",
        env_file=(ENV_FILE,),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Knowledge base (spec 01 §4, spec 05) ---------------------------------------------
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("change-me")
    vector_backend: Literal["pgvector", "memory"] = "pgvector"
    pg_dsn: str = "postgresql://knowhow:change-me@localhost:5432/knowhow"
    vector_table: str = "knowhow_chunks"
    embed_dim: int = 1024
    embed_model: str = "BAAI/bge-m3"
    # "hashing" is a no-model stand-in for dev; it must not fill a table that bge-m3 will later use.
    # "remote" = the same bge-m3 on the team's inference server (KNOWHOW_INFERENCE_URL, spec 02 FR-07d).
    embedder: Literal["bge-m3", "hashing", "remote"] = "bge-m3"

    # --- Document ingest (spec 02) ----------------------------------------------------------
    process_id_regex: str = r"\b[A-Z]{3,5}\d{2}\b"
    # Default matches DENSO-style numbers (AA123456-7890); confirm against the samples (spec 02b §4.4).
    part_number_regex: str = r"\b[A-Z]{2}\d{6}-\d{4}\b"
    # Matches of process_id_regex that are not processes (ISO27, REV01...).
    process_id_stoplist: list[str] = []
    # Where Docling runs (spec 02 FR-02c): here (ingest extra) or on the team's inference server.
    doc_extractor: Literal["docling", "remote"] = "docling"
    # Command of the mmore install used as the degraded PDF fallback (not a project extra).
    mmore_bin: str = "mmore"
    # bge-m3 matches the embedder; "whitespace" is for offline runs and undercounts CJK.
    token_counter: Literal["bge-m3", "whitespace"] = "bge-m3"
    chunk_min_tokens: int = 300
    chunk_max_tokens: int = 800
    chunk_overlap_tokens: int = 50
    # Share of IPA/Greek letters above which a page's text layer is reported as mis-encoded (FR-02b).
    text_quality_max_odd_ratio: float = 0.05

    # --- VLM (spec 04) ----------------------------------------------------------------------
    # Registry name of the provider (``knowhow vlm providers`` lists them).
    vlm_provider: str = "local_openai"
    # Empty = the provider's default endpoint / default Qwen3-VL-8B model id.
    vlm_base_url: str | None = None
    vlm_model: str | None = None
    # Empty = the provider's own key variable (e.g. OPENROUTER_API_KEY in .env).
    vlm_api_key: SecretStr | None = None
    vlm_fps: float = 4.0
    vlm_max_frames: int = 48
    # FR-07. The default server is Ollama with the Q4 model, which thinks (~8k tokens for a few
    # frames) before it answers: 2048 tokens left the JSON empty, 90 s was too short.
    vlm_timeout_s: float = 900.0
    vlm_max_retries: int = 3  # FR-07
    vlm_json_mode: JsonMode = "auto"
    vlm_max_tokens: int = 16384
    # JSON merged into every request body: vendor sampling knobs (e.g. {"presence_penalty": 1.5},
    # which stops Qwen3-VL from looping step lists).
    vlm_extra_body: dict[str, Any] = {}
    # Spec 04 §3: a sentence of the expert belongs to the step whose [t_start - lead, t_end + lag]
    # overlaps it most (experts explain just before acting and comment just after).
    transcript_lead_s: float = 2.0
    transcript_lag_s: float = 3.0
    # Spec 04 §3: where pass A puts a step inside its segment (processing.vlm.passes.step_times).
    # segment = the steps tile the segment in start order; model = the VLM's own ~1 s spans. Tiling
    # matched the hand-labelled LASI steps better (time recall 0.59 -> 0.85, mean IoU 0.34 -> 0.50).
    vlm_step_times: Literal["segment", "model"] = "segment"
    # Spec 04 §3: VLM/LLM requests one video job keeps in flight (passes A and B together, then the
    # reason proposals). 1 = one at a time, as before. A server that batches (vLLM) decodes several
    # answers for about the price of one: a Thinking model's job is then several times shorter.
    vlm_concurrency: int = Field(default=1, ge=1, le=16)

    # --- LLM (spec 06; also spec 04 pass C / propose-reasons) ---------------------------------
    # Empty = the LLM is the VLM: same provider, server, model and key as KNOWHOW_VLM_* (the
    # Qwen3-VL server answers text too). Set it to use another LLM; then empty base URL / model
    # = that provider's default (qwen_api: qwen-plus, local_openai: the Ollama qwen3-vl:8b).
    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    # Room for the thinking and the answer of the Q4 model on Ollama (agents, pass C, ragas judge).
    llm_timeout_s: float = 900.0
    llm_max_retries: int = 3
    llm_json_mode: JsonMode = "auto"
    llm_max_tokens: int = 8192
    llm_extra_body: dict[str, Any] = {}

    # --- Video capture (spec 03) -------------------------------------------------------------
    # Cutting method when a call names none (spec 03 FR-03): hand_activity (one operator, continuous
    # footage) | scene (edited video with shot changes) | fixed_window (10 s windows).
    video_method: Literal["hand_activity", "scene", "fixed_window"] = "hand_activity"
    # MediaPipe hand model of `hand_activity` cuts (FR-03), fetched once, SHA-256 pinned.
    video_hand_model: Path = REPO_ROOT / "data" / "work" / "models" / "hand_landmarker.task"

    # --- Speech-to-text (spec 03 FR-07c) -----------------------------------------------------
    # Registry name of the ASR provider (`knowhow video providers` lists them): faster_whisper runs
    # here, remote on the team's inference server (KNOWHOW_INFERENCE_URL). Never a third-party API.
    asr_provider: str = "faster_whisper"
    # Empty = the provider's default model (faster_whisper: "small", downloaded once).
    asr_model: str | None = None
    asr_device: str = "cpu"
    # CTranslate2 quantisation: int8 keeps Whisper small around 0.5 GB of RAM on a CPU.
    asr_compute_type: str = "int8"
    # Language of the expert's speech; empty = detected per file (any language Whisper knows:
    # a Thai expert's words stay Thai, and so do the reasons quoted from them). Set to force one.
    asr_language: str | None = None
    asr_beam_size: int = 5
    # Voice activity detection (Silero, bundled): skips silence and music before decoding.
    asr_vad: bool = True

    # --- Team inference server (spec 02 FR-02c/FR-07d, spec 03 FR-07c) ------------------------
    # The heavy CPU models — Whisper (KNOWHOW_ASR_PROVIDER=remote), Docling/OCR
    # (KNOWHOW_DOC_EXTRACTOR=remote), bge-m3 (KNOWHOW_EMBEDDER=remote) — on the team's own server.
    # Base URL of its API, e.g. https://host/v1 (``user:pass@`` basic auth allowed, never shown in
    # errors). Local or cloud is judged from the URL like the VLM's: a private address or a host
    # in KNOWHOW_LOCAL_HOSTS is local; anything else is cloud and never gets factory_confidential data.
    inference_url: str | None = None
    # Bearer token; empty = KNOWHOW_VLM_API_KEY (usually the same server); both empty = no header.
    inference_api_key: SecretStr | None = None
    # One request may be a 30-minute recording through Whisper on a CPU: minutes, not seconds.
    inference_timeout_s: float = 1800.0
    inference_max_retries: int = 2

    # --- Outbound guard for cloud calls (spec 01 FR-09b, spec 04 FR-02c) ---------------------
    # Mask PII in text sent to cloud providers. False = refuse instead (LeakGuard always runs).
    guard_mask_text: bool = True
    # Pixelate faces in frames sent to cloud VLMs (YuNet model fetched once, SHA-256 pinned).
    guard_blur_faces: bool = True
    guard_face_model: Path = REPO_ROOT / "data" / "work" / "models" / "face_detection_yunet_2023mar.onnx"
    # One JSON line per cloud call, counts only. Empty = no audit log.
    guard_audit_dir: Path | None = REPO_ROOT / "data" / "work" / "audit"
    # Site-specific codes to mask, entity -> regex, e.g. {"EQUIPMENT": "SIGMA-EQ-\\d+"}.
    guard_extra_patterns: dict[str, str] = {}
    # Public hostnames that are really the team's own server (e.g. an ngrok tunnel to it), so
    # local_openai / openai_compatible calls to them count as local (spec 04 AC-23).
    local_hosts: list[str] = []

    # --- Agents (spec 06) -----------------------------------------------------------------
    # Work Assistant guard 1: refuse when the best spec 05 score is below this. That score is RRF
    # (1/(60+vector rank) + 1/(60+keyword rank) + 0.1 graph bonus, ~0.133 at most), so it only
    # stops "nothing found": 0.02 ~ no passage near the top of either ranking.
    assist_min_score: float = 0.02
    # Work Assistant guard 2: refuse (no LLM call) when the best bge-m3 cosine between the
    # question and a passage is below this. LASI golden set 2026-10-04: on-topic >= 0.435, 3 of 5
    # off-topic < 0.40 (the other two go on to guard 3, the LLM's answerable=false).
    assist_min_cosine: float = 0.40
    # One JSON line per agent call (spec 06 FR-04). Empty = no trace.
    trace_dir: Path | None = REPO_ROOT / "data" / "work" / "traces"
    # /assistant/ask and /rca/investigate: mock = the routers' demo answers, live = the agents.
    api_agents: Literal["mock", "live"] = "mock"

    # --- Evaluation (spec 09) --------------------------------------------------------------
    # Who computes the four Ragas metrics: ragas = the ``ragas`` package (``eval`` extra),
    # builtin = the project's own prompts with the same definitions (no ragas/langchain needed).
    eval_judge: Literal["ragas", "builtin"] = "ragas"
    # ragas judge only: parallel judge calls (match the server: vLLM max_num_seqs; Ollama runs one
    # request at a time unless OLLAMA_NUM_PARALLEL is raised) and the time one ragas job may take
    # (empty = the judge LLM's own timeout, so ragas never gives up before the provider does).
    eval_max_workers: int = 4
    eval_timeout_s: float | None = None
    # Judge LLM of the Ragas metrics; empty = the agent's KNOWHOW_LLM_* (FR-02).
    eval_llm_provider: str | None = None
    eval_llm_base_url: str | None = None
    eval_llm_model: str | None = None

    # --- REST API (spec 08) -----------------------------------------------------------------
    app_name: str = "MentorMind Know-How API"
    # Spec 08 FR-05: only the UI's origin (Vite dev server by default).
    cors_origins: list[str] = ["http://localhost:5173"]

    # --- Stores & adapters (spec 07, 08) ----------------------------------------------------
    profile_db: Path = Path("data/work/profiles.sqlite")
    # Where `vlm describe` keeps drafts: auto = spec 08 store if present, else JSON file.
    profile_sink: Literal["auto", "store", "file"] = "auto"
    sigma_adapter: str = "csv"
    sigma_csv_dir: Path = Path("data/mock_sigma")
    work_dir: Path = Path("data/work")
    samples_dir: Path = Path("data/samples")

    # Where provider-specific API keys are looked up after the process environment.
    secrets_file: Path = ENV_FILE


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings (cached; tests build ``Settings`` directly)."""
    return Settings()
