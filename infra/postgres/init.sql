
-- spec 01 FR-05: extensions the vector store (spec 05) needs, created on first start.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- MentorMind / DENSO Factory Hacks
-- PostgreSQL + pgvector schema v1.2
-- Goal: Case -> Evidence -> Knowledge -> Expert Review -> Approved Knowledge -> RAG
--
-- Sources of truth (CLAUDE.md: the contract wins over prose):
--   * docs/contracts/work_profile.schema.json -> public.knowledge_units (one row = one WorkProfile)
--   * constitution art. 2 -> data_classification in {public, synthetic, factory_confidential}
--   * constitution art. 3 -> reason only from the expert (expert_verbal | expert_interview)
--   * spec 01 FR-05c, spec 02 FR-07, spec 05 FR-06 -> ONE vector table, public.knowhow_chunks
--     (KNOWHOW_VECTOR_TABLE), shared by document and work_profile chunks via source_type.
--
-- IMPORTANT:
-- 1) Embedding dimension = 1024 (KNOWHOW_EMBED_DIM, bge-m3). Change vector(1024) BEFORE the
--    first run if the embedding model changes.
-- 2) Runtime architecture: Frontend -> FastAPI -> PostgreSQL. The frontend never connects to
--    PostgreSQL directly; authorization lives in the API layer for the MVP.
-- 3) Docker bootstrap (/docker-entrypoint-initdb.d/init.sql): runs only when the data
--    directory is initialised for the first time. Changing this file needs `make down` plus
--    removing the pgdata volume to take effect.
-- 4) Every time value that mirrors a contract/spec model (evidence, transcript) is in SECONDS
--    (t_start / t_end), like the contract — not milliseconds.

begin;

create extension if not exists pgcrypto;
create extension if not exists vector;
create extension if not exists unaccent;

-- =========================================================
-- 0. Shared vocabulary
-- =========================================================
-- Constitution art. 2. Unknown data defaults to the strictest label (fail closed).
do $$
begin
  if not exists (select 1 from pg_type where typname = 'data_classification') then
    create domain public.data_classification as text
      check (value in ('public', 'synthetic', 'factory_confidential'));
  end if;
end
$$;

-- Spec 05: lexical search with the `simple` parser plus `unaccent` (Postgres has no Vietnamese
-- dictionary). unaccent() is not IMMUTABLE, so it cannot sit in a generated column itself; a
-- text search configuration can, because to_tsvector(regconfig, text) is immutable.
do $$
begin
  if not exists (select 1 from pg_ts_config where cfgname = 'mm_unaccent') then
    create text search configuration public.mm_unaccent (copy = pg_catalog.simple);
    alter text search configuration public.mm_unaccent
      alter mapping for hword, hword_part, word with public.unaccent, pg_catalog.simple;
  end if;
end
$$;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- =========================================================
-- 1. User / Expert profile (people, not WorkProfiles)
-- =========================================================
create table if not exists public.profiles (
  id uuid primary key default gen_random_uuid(),
  display_name text not null,
  employee_code text,
  role text not null default 'engineer'
    check (role in ('admin','expert','engineer','reviewer')),
  department text,
  expertise jsonb not null default '[]'::jsonb,
  is_demo boolean not null default false,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- =========================================================
-- 2. Manufacturing process / station
-- =========================================================
-- process_code is the Sigma process code (contract: WorkProfile.process_id, e.g. PACK01).
create table if not exists public.processes (
  id uuid primary key default gen_random_uuid(),
  process_code text not null unique,
  process_name text not null,
  department text,
  station_code text,
  description text,
  status text not null default 'active'
    check (status in ('active','inactive','archived')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- =========================================================
-- 3. Knowledge case = one captured work/interview/problem-solving case (BRD §10, PRD §4)
-- =========================================================
create table if not exists public.knowledge_cases (
  id uuid primary key default gen_random_uuid(),
  case_code text not null unique,
  process_id uuid references public.processes(id) on delete set null,
  expert_id uuid references public.profiles(id) on delete set null,

  title text not null,
  description text,

  capture_mode text not null default 'document_only'
    check (capture_mode in (
      'work_video',
      'expert_interview',
      'review_session',
      'document_only',
      'mixed'
    )),

  scenario_type text not null default 'normal'
    check (scenario_type in (
      'normal',
      'exception',
      'abnormal',
      'troubleshooting',
      'quality_issue',
      'unknown'
    )),

  lot_code text,
  part_code text,
  equipment_code text,

  -- Provenance (who supplied the data); sensitivity is data_classification below.
  source_label text not null default 'public'
    check (source_label in ('public','denso_internal','partner')),
  data_classification public.data_classification not null default 'factory_confidential',

  status text not null default 'draft'
    check (status in ('draft','processing','in_review','verified','rejected','archived')),

  started_at timestamptz,
  ended_at timestamptz,

  metadata jsonb not null default '{}'::jsonb,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- =========================================================
-- 4. Raw/derived assets: video/audio/PDF/XLSX/image/log/CSV...
--    A row may represent a public source not yet copied into project/object storage.
-- =========================================================
create table if not exists public.assets (
  id uuid primary key default gen_random_uuid(),
  asset_code text unique,
  file_name text not null,
  asset_type text not null
    check (asset_type in (
      'video','audio','image','pdf','xlsx','csv','document','drawing','machine_log','sensor_data','other'
    )),
  mime_type text,

  source_label text not null default 'public'
    check (source_label in ('public','denso_internal','partner')),
  data_classification public.data_classification not null default 'factory_confidential',

  availability_status text not null default 'available'
    check (availability_status in ('available','restricted','unavailable')),

  origin_url text,
  storage_bucket text,
  storage_path text,

  language_code text,
  has_transcript boolean not null default false,
  transcript_language_code text,

  sha256 text,
  file_size_bytes bigint,
  duration_ms bigint,

  license_note text,
  description text,
  metadata jsonb not null default '{}'::jsonb,

  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint asset_has_location
    check (origin_url is not null or storage_path is not null)
);

-- A reusable SOP/drawing can support many cases.
create table if not exists public.case_assets (
  case_id uuid not null references public.knowledge_cases(id) on delete cascade,
  asset_id uuid not null references public.assets(id) on delete cascade,
  relation_type text not null default 'evidence'
    check (relation_type in ('evidence','reference','input','output','derived')),
  note text,
  created_at timestamptz not null default now(),
  primary key (case_id, asset_id, relation_type)
);

-- =========================================================
-- 5. Video/audio transcript (spec 03 TranscriptSegment: seconds)
-- =========================================================
create table if not exists public.transcript_segments (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  segment_index integer not null,
  t_start double precision not null default 0 check (t_start >= 0),
  t_end double precision check (t_end is null or t_end >= t_start),
  speaker_label text,
  speaker_profile_id uuid references public.profiles(id) on delete set null,
  language_code text,
  text text not null,
  confidence numeric(5,4) check (confidence is null or (confidence >= 0 and confidence <= 1)),
  -- spec 03: inline commentary or video-cued recall (architecture §4).
  source text not null default 'inline'
    check (source in ('inline','cued_recall','manual','imported')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(asset_id, segment_index)
);

-- =========================================================
-- 6. Parsed/OCR document chunks (spec 02 DocumentChunk) — the parse record.
--    Search goes through public.knowhow_chunks (section 9b), not this table.
-- =========================================================
create table if not exists public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets(id) on delete cascade,
  chunk_id text unique,                      -- spec 02: f"{doc_id}#p{page}-{index}"
  chunk_index integer not null,
  page_number integer,
  section_title text,
  kind text not null default 'text'
    check (kind in ('text','table','figure_caption','drawing_note')),
  content text not null,
  bbox jsonb,
  parser_name text,
  parser_version text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(asset_id, chunk_index)
);

-- =========================================================
-- 7. Signals the expert was observing
-- =========================================================
create table if not exists public.case_signals (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references public.knowledge_cases(id) on delete cascade,
  asset_id uuid references public.assets(id) on delete set null,

  observed_at_ms bigint check (observed_at_ms is null or observed_at_ms >= 0),
  signal_type text not null,
  signal_name text not null,

  value_text text,
  value_number double precision,
  unit text,

  is_abnormal boolean,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- =========================================================
-- 8. Final outcome / confirmed result of a case
-- =========================================================
create table if not exists public.case_outcomes (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references public.knowledge_cases(id) on delete cascade,

  result text,
  final_cause text,
  final_action text,
  quality_result text,
  resolved boolean,
  reoccurred boolean,

  metrics jsonb not null default '{}'::jsonb,

  verified_by uuid references public.profiles(id) on delete set null,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique(case_id)
);

-- =========================================================
-- 9. Knowledge unit = one WorkProfile (contract v1.0), column for column.
--    Contract field -> column: every top-level field keeps its name; `expert` is split into
--    expert_id / expert_display_name; `review` into reviewer / reviewed_at / review_comment /
--    review_error_tags; `evidence` and `model_info` stay JSON objects of the contract shape.
--    The BRD layers the contract does not carry yet (context, observation, conditions,
--    decision, expected_outcome) are extra nullable columns.
-- =========================================================
create table if not exists public.knowledge_units (
  id uuid primary key default gen_random_uuid(),

  schema_version text not null default '1.0' check (schema_version = '1.0'),
  profile_id text not null unique check (profile_id ~ '^WP-[A-Z0-9]{3,}-[0-9]{3}$'),
  process_id text not null
    references public.processes(process_code) on update cascade on delete restrict,
  step_order integer not null check (step_order >= 1),
  step text not null check (char_length(step) >= 3),
  actor text check (actor is null or actor in ('human','robot','machine')),
  hand_action text,
  objects jsonb not null default '[]'::jsonb check (jsonb_typeof(objects) = 'array'),
  key_point text,
  reason text,
  reason_source text
    check (reason_source is null or reason_source in ('expert_verbal','expert_interview')),
  exceptions jsonb not null default '[]'::jsonb check (jsonb_typeof(exceptions) = 'array'),
  pass_criteria text,
  equipment_id text,
  part_numbers jsonb not null default '[]'::jsonb check (jsonb_typeof(part_numbers) = 'array'),
  expert_id text,
  expert_display_name text,
  evidence jsonb not null
    check (jsonb_typeof(evidence) = 'object' and evidence ? 'video_id'),
  confidence numeric(5,4) not null check (confidence >= 0 and confidence <= 1),
  generated_by text not null check (generated_by in ('vlm','ocr','human')),
  model_info jsonb check (model_info is null or jsonb_typeof(model_info) = 'object'),
  data_classification public.data_classification not null,
  status text not null default 'draft'
    check (status in ('draft','in_review','approved','rejected')),
  reviewer text,
  reviewed_at timestamptz,
  review_comment text,
  review_error_tags jsonb not null default '[]'::jsonb
    check (
      jsonb_typeof(review_error_tags) = 'array'
      and review_error_tags <@ '["missed_step","hallucinated_step","wrong_order","wrong_object","wrong_action","other"]'::jsonb
    ),
  created_at timestamptz not null default now(),
  version integer not null default 1 check (version >= 1),

  -- Links to the case model and people (optional: the contract identifies them by code).
  case_id uuid references public.knowledge_cases(id) on delete set null,
  contributor_id uuid references public.profiles(id) on delete set null,
  knowledge_type text not null default 'work_step'
    check (knowledge_type in (
      'work_step','rule','quality_criterion','diagnostic','exception','troubleshooting',
      'lesson_learned'
    )),

  -- BRD §10 layers beyond the contract.
  context text,
  observation text,
  conditions jsonb not null default '[]'::jsonb,
  decision text,
  expected_outcome text,

  created_by uuid references public.profiles(id) on delete set null,
  updated_at timestamptz not null default now(),

  -- Contract allOf[0], constitution art. 3: a VLM draft never carries a reason.
  constraint vlm_draft_has_no_reason
    check (not (generated_by = 'vlm' and status = 'draft'
                and (reason is not null or reason_source is not null))),
  -- Contract allOf[1]: a reason says which expert channel it came from.
  constraint reason_has_expert_source
    check (reason is null or reason_source is not null),
  -- Contract allOf[2], BR-07: approval is attributable.
  constraint approved_is_attributed
    check (status <> 'approved' or (reviewer is not null and reviewed_at is not null))
);

-- =========================================================
-- 9b. The ONE vector table (spec 01 FR-05c, spec 02 FR-07, spec 05 FR-06).
--     Name = KNOWHOW_VECTOR_TABLE. Document chunks and APPROVED work_profile chunks side by
--     side, told apart by source_type; upsert by chunk_id so re-runs never duplicate.
-- =========================================================
create table if not exists public.knowhow_chunks (
  chunk_id text primary key,
  source_type text not null
    check (source_type in ('work_profile','document','video_segment','sigma')),
  -- Citation.ref_id (spec 05): profile_id, doc_id, segment_id, lot_id...
  ref_id text not null,
  kind text,                                  -- spec 02 ChunkKind for documents
  text text not null,
  process_ids text[] not null default '{}',
  part_numbers text[] not null default '{}',
  data_classification public.data_classification not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector(1024),
  search_tsv tsvector generated always as (
    to_tsvector('public.mm_unaccent'::regconfig, coalesce(text, ''))
  ) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- PRD-FR-06 in the schema: a work_profile chunk may only exist for an approved profile when
-- that profile is stored here (spec 08 may keep profiles in SQLite; then the loader is the gate).
create or replace function public.knowhow_chunks_only_approved()
returns trigger
language plpgsql
as $$
declare
  profile_status text;
begin
  if new.source_type = 'work_profile' then
    select ku.status into profile_status
    from public.knowledge_units ku
    where ku.profile_id = new.ref_id;
    if found and profile_status <> 'approved' then
      raise exception 'work_profile chunk % refused: profile % is %, not approved',
        new.chunk_id, new.ref_id, profile_status;
    end if;
  end if;
  return new;
end;
$$;

-- ... and leaving `approved` removes the profile's chunks (spec 05: unload_profile).
create or replace function public.unindex_unapproved_profile()
returns trigger
language plpgsql
as $$
begin
  if old.status = 'approved' and new.status <> 'approved' then
    delete from public.knowhow_chunks
    where source_type = 'work_profile' and ref_id = old.profile_id;
  end if;
  return new;
end;
$$;

-- =========================================================
-- 10. Provenance: each knowledge claim points back to evidence (seconds, like the contract)
-- =========================================================
create table if not exists public.knowledge_evidence (
  id uuid primary key default gen_random_uuid(),
  knowledge_unit_id uuid not null references public.knowledge_units(id) on delete cascade,
  asset_id uuid not null references public.assets(id) on delete cascade,

  transcript_segment_id uuid references public.transcript_segments(id) on delete set null,
  document_chunk_id uuid references public.document_chunks(id) on delete set null,
  signal_id uuid references public.case_signals(id) on delete set null,

  t_start double precision check (t_start is null or t_start >= 0),
  t_end double precision check (t_end is null or t_end >= 0),
  page_number integer,

  evidence_role text not null default 'support'
    check (evidence_role in ('support','context','reason','exception','outcome','conflict')),

  excerpt text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),

  constraint valid_evidence_time
    check (t_start is null or t_end is null or t_end >= t_start)
);

-- =========================================================
-- 11. Expert verification (spec 08 review events)
-- =========================================================
create table if not exists public.knowledge_reviews (
  id uuid primary key default gen_random_uuid(),
  knowledge_unit_id uuid not null references public.knowledge_units(id) on delete cascade,
  -- Contract review.reviewer is a code (e.g. EXP-001); reviewer_id links a person when known.
  reviewer text not null,
  reviewer_id uuid references public.profiles(id) on delete set null,

  decision text not null
    check (decision in ('approve','reject','request_change')),

  comment text,
  corrected_payload jsonb,
  error_tags jsonb not null default '[]'::jsonb
    check (
      jsonb_typeof(error_tags) = 'array'
      and error_tags <@ '["missed_step","hallucinated_step","wrong_order","wrong_object","wrong_action","other"]'::jsonb
    ),

  reviewed_at timestamptz not null default now(),

  -- Spec 08 AC-03: rejecting requires a reason.
  constraint reject_has_comment
    check (decision <> 'reject' or nullif(btrim(comment), '') is not null)
);

-- Snapshots preserve audit/version history.
create table if not exists public.knowledge_versions (
  id uuid primary key default gen_random_uuid(),
  knowledge_unit_id uuid not null references public.knowledge_units(id) on delete cascade,
  version integer not null,
  snapshot jsonb not null,
  change_note text,
  changed_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  unique(knowledge_unit_id, version)
);

-- =========================================================
-- 12. Evaluation / Golden Set
-- =========================================================
create table if not exists public.evaluation_questions (
  id uuid primary key default gen_random_uuid(),
  qid text not null unique,
  process_id uuid references public.processes(id) on delete set null,

  question_type text not null
    check (question_type in ('how','why','exception','relation','out_of_scope')),
  question text not null,
  expected_answer text,
  expected_behavior text not null default 'answer'
    check (expected_behavior in ('answer','abstain')),

  expected_citations jsonb not null default '[]'::jsonb,
  tags jsonb not null default '[]'::jsonb,

  source_label text not null default 'public'
    check (source_label in ('public','denso_internal','partner')),
  active boolean not null default true,

  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.evaluation_runs (
  id uuid primary key default gen_random_uuid(),
  run_name text not null,
  model_name text,
  retriever_name text,
  config jsonb not null default '{}'::jsonb,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  created_by uuid references public.profiles(id) on delete set null
);

create table if not exists public.evaluation_results (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.evaluation_runs(id) on delete cascade,
  question_id uuid not null references public.evaluation_questions(id) on delete cascade,

  answer text,
  citations jsonb not null default '[]'::jsonb,

  retrieval_metrics jsonb not null default '{}'::jsonb,
  answer_metrics jsonb not null default '{}'::jsonb,

  passed boolean,
  latency_ms integer,
  error_tag text,

  created_at timestamptz not null default now(),
  unique(run_id, question_id)
);

-- =========================================================
-- 13. Indexes
-- =========================================================
create index if not exists idx_cases_process
  on public.knowledge_cases(process_id);

create index if not exists idx_cases_status
  on public.knowledge_cases(status);

create index if not exists idx_assets_type
  on public.assets(asset_type);

create index if not exists idx_assets_source
  on public.assets(source_label, data_classification);

create unique index if not exists idx_assets_sha256_unique
  on public.assets(sha256)
  where sha256 is not null;

create index if not exists idx_transcript_asset_time
  on public.transcript_segments(asset_id, t_start);

create index if not exists idx_doc_chunks_asset
  on public.document_chunks(asset_id, chunk_index);

create index if not exists idx_signals_case
  on public.case_signals(case_id, observed_at_ms);

create index if not exists idx_knowledge_process_status
  on public.knowledge_units(process_id, status);

create index if not exists idx_knowledge_case
  on public.knowledge_units(case_id);

-- Vector table: filters of spec 02 FR-07 / spec 05 (source_type, kind, process_ids, label).
create index if not exists idx_chunks_source_kind
  on public.knowhow_chunks(source_type, kind);

create index if not exists idx_chunks_ref
  on public.knowhow_chunks(source_type, ref_id);

create index if not exists idx_chunks_process_ids
  on public.knowhow_chunks using gin(process_ids);

create index if not exists idx_chunks_classification
  on public.knowhow_chunks(data_classification);

create index if not exists idx_chunks_fts
  on public.knowhow_chunks using gin(search_tsv);

create index if not exists idx_chunks_embedding_hnsw
  on public.knowhow_chunks
  using hnsw (embedding vector_cosine_ops)
  where embedding is not null;

create index if not exists idx_evidence_knowledge
  on public.knowledge_evidence(knowledge_unit_id);

create index if not exists idx_reviews_knowledge
  on public.knowledge_reviews(knowledge_unit_id, reviewed_at desc);

-- =========================================================
-- 14. Triggers
-- =========================================================
drop trigger if exists trg_profiles_updated_at on public.profiles;
create trigger trg_profiles_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

drop trigger if exists trg_processes_updated_at on public.processes;
create trigger trg_processes_updated_at
before update on public.processes
for each row execute function public.set_updated_at();

drop trigger if exists trg_cases_updated_at on public.knowledge_cases;
create trigger trg_cases_updated_at
before update on public.knowledge_cases
for each row execute function public.set_updated_at();

drop trigger if exists trg_assets_updated_at on public.assets;
create trigger trg_assets_updated_at
before update on public.assets
for each row execute function public.set_updated_at();

drop trigger if exists trg_outcomes_updated_at on public.case_outcomes;
create trigger trg_outcomes_updated_at
before update on public.case_outcomes
for each row execute function public.set_updated_at();

drop trigger if exists trg_knowledge_updated_at on public.knowledge_units;
create trigger trg_knowledge_updated_at
before update on public.knowledge_units
for each row execute function public.set_updated_at();

drop trigger if exists trg_knowledge_unindex on public.knowledge_units;
create trigger trg_knowledge_unindex
after update of status on public.knowledge_units
for each row execute function public.unindex_unapproved_profile();

drop trigger if exists trg_chunks_updated_at on public.knowhow_chunks;
create trigger trg_chunks_updated_at
before update on public.knowhow_chunks
for each row execute function public.set_updated_at();

drop trigger if exists trg_chunks_only_approved on public.knowhow_chunks;
create trigger trg_chunks_only_approved
before insert or update on public.knowhow_chunks
for each row execute function public.knowhow_chunks_only_approved();

drop trigger if exists trg_eval_questions_updated_at on public.evaluation_questions;
create trigger trg_eval_questions_updated_at
before update on public.evaluation_questions
for each row execute function public.set_updated_at();

-- =========================================================
-- 15. Access-control boundary
-- =========================================================
-- This bootstrap targets plain PostgreSQL, not Supabase.
-- Authorization is enforced by the FastAPI application layer for the MVP.
-- Do not expose PostgreSQL directly to the frontend.

-- =========================================================
-- 16. Convenience views
-- =========================================================
-- Verified knowledge with its attribution (PRD-FR-11): contributor, reviewer, evidence.
create or replace view public.approved_knowledge_view as
select
  ku.id,
  ku.profile_id,
  ku.process_id,
  p.process_name,
  ku.step_order,
  ku.step,
  ku.actor,
  ku.hand_action,
  ku.objects,
  ku.key_point,
  ku.reason,
  ku.reason_source,
  ku.exceptions,
  ku.pass_criteria,
  ku.equipment_id,
  ku.part_numbers,
  ku.expert_id,
  ku.expert_display_name,
  ku.reviewer,
  ku.reviewed_at,
  ku.evidence,
  ku.confidence,
  ku.data_classification,
  ku.knowledge_type,
  ku.context,
  ku.observation,
  ku.conditions,
  ku.decision,
  ku.expected_outcome,
  ku.version,
  ku.updated_at
from public.knowledge_units ku
left join public.processes p on p.process_code = ku.process_id
where ku.status = 'approved';

-- =========================================================
-- 17. File/object storage
-- =========================================================
-- Plain PostgreSQL does not provide Supabase Storage buckets.
-- Binary files stay outside PostgreSQL (local/object storage).
-- The assets table stores origin_url / storage_bucket / storage_path metadata.

commit;
