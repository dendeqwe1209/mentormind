export type ProfileStatus = "draft" | "in_review" | "approved" | "rejected";
export type ReasonSource = "expert_verbal" | "expert_interview";
export type ErrorTag =
  | "missed_step"
  | "hallucinated_step"
  | "wrong_order"
  | "wrong_object"
  | "wrong_action"
  | "other";

export interface Evidence {
  video_id?: string | null;
  t_start?: number | null;
  t_end?: number | null;
  segment_ids?: string[];
  keyframes?: string[];
  transcript_excerpt?: string | null;
  document_refs?: string[];
}

export interface ReviewInfo {
  reviewer: string;
  reviewed_at: string;
  comment?: string | null;
  error_tags?: ErrorTag[];
}

export interface ExceptionItem {
  case: string;
  handling: string;
}

export interface WorkProfile {
  schema_version: "1.0";
  profile_id: string;
  process_id: string;
  step_order: number;
  step: string;
  hand_action?: string | null;
  objects: string[];
  key_point?: string | null;
  reason?: string | null;
  reason_source?: ReasonSource | null;
  exceptions: ExceptionItem[];
  pass_criteria?: string | null;
  equipment_id?: string | null;
  part_numbers: string[];
  evidence: Evidence;
  confidence: number;
  generated_by: "vlm" | "ocr" | "human";
  data_classification: "public" | "synthetic" | "factory_confidential";
  status: ProfileStatus;
  review?: ReviewInfo | null;
  created_at: string;
  version: number;
  // GET /profiles only: the knowledge graph serves this step (approved, or edited after approval),
  // so deleting it also removes it from the graph and the search store (spec 08 §2).
  published?: boolean;
}

export interface ReviewRequest {
  action: "approve" | "reject";
  reviewer: string;
  comment?: string;
  error_tags?: ErrorTag[];
}

export interface ProfilePatchRequest {
  step?: string;
  hand_action?: string;
  objects?: string[];
  key_point?: string;
  reason?: string;
  reason_source?: ReasonSource | null;
  pass_criteria?: string;
}

export interface Citation {
  source_type: "work_profile" | "document" | "video_segment" | "sigma" | "video";
  ref_id: string;
  title?: string | null;
  t_start?: number | null;
  t_end?: number | null;
  excerpt?: string | null;
  keyframe_url?: string | null;
}

export interface AssistantAnswer {
  answer: string;
  refused: boolean;
  suggested_expert?: string;
  citations: Citation[];
}

export interface Hypothesis {
  hypothesis: string;
  likelihood: "high" | "medium" | "low";
  evidence_refs: string[];
}

export interface WhyStep {
  order: number;
  question: string;
  answer: string;
  verified: boolean;
}

export interface RcaReport {
  lot_id?: string;
  symptom: string;
  hypotheses: Hypothesis[];
  five_whys: WhyStep[];
  related_lots: string[];
  preventive_actions: string[];
  disclaimer: string;
}

export interface LotRecord {
  lot_id: string;
  process_id: string;
  part_number: string;
  produced_at: string;
  defect_type?: string;
  status: string;
}

export type DataClassification = "public" | "synthetic" | "factory_confidential";
export type JobStatus = "queued" | "running" | "done" | "failed";

export interface JobResponse<T = unknown> {
  job_id: string;
  kind: string;
  status: JobStatus;
  result?: T | null;
  error?: string | null;
  created_at?: string | null;
  finished_at?: string | null;
}

// Result of a POST /ingest/documents job (spec 08 §2).
export interface DocumentIngestFile {
  name: string;
  doc_id?: string | null;
  extractor?: string | null;
  pages: number;
  chunks: number;
  skipped: boolean;
  error?: string | null;
}

export interface DocumentIngestResult {
  classification: DataClassification;
  files: DocumentIngestFile[];
  chunks_indexed: number;
}

// Spec 03 §3 — what POST /videos returns (also kept as video.json next to the upload).
export interface VideoAsset {
  video_id: string;
  path: string;
  duration_s: number;
  fps: number;
  has_audio: boolean;
  process_id?: string | null;
  data_classification: DataClassification;
}

// Spec 03 §3 — one cut of a video (GET /videos/{id}/segments).
export interface Segment {
  segment_id: string;
  video_id: string;
  index: number;
  t_start: number;
  t_end: number;
  method: "scene" | "hand_activity" | "fixed_window";
  motion_score?: number | null;
  keyframes: string[];
  clip_path: string;
  data_classification: DataClassification;
}

export type CutMethod = "hand_activity" | "scene" | "fixed_window";
export type VideoStage = "cut" | "transcribe" | "describe" | "merge" | "reasons";

// Result of a POST /videos/{id}/process job (spec 08 §2).
export interface VideoProcessResult {
  video_id: string;
  process_id: string;
  method: CutMethod;
  method_used?: CutMethod | null;
  segments: number;
  profiles: string[];
  failed_segments: string[];
  transcript_lines: number;
  steps_with_excerpt: number;
  reasons_filled: number;
  progress?: { stage: VideoStage; done: number; total: number } | null;
}

// Deletions (spec 08 §2 "Xoá dữ liệu").
export interface DeleteFailure {
  profile_id: string;
  error: string;
}

export interface ProfileDeleteResult {
  deleted: string[];
  // Of `deleted`: approved steps also removed from Neo4j + pgvector.
  unpublished: string[];
  // Approved steps kept because the graph / vector store could not drop them.
  failed: DeleteFailure[];
}

export interface VideoDeleteResult extends ProfileDeleteResult {
  video_id: string;
  files_removed: number;
}

// GET /documents: one indexed document (a data/work/chunks/<doc_id>.jsonl).
export interface DocumentInfo {
  doc_id: string;
  name: string;
  title?: string | null;
  data_classification?: DataClassification | null;
  extractor?: string | null;
  chunks: number;
}

export interface DocumentDeleteResult {
  doc_id: string;
  chunks_deleted: number;
  chunk_file_removed: boolean;
  uploads_removed: number;
}
