import React, { useEffect, useRef, useState } from "react";
import { api, ApiError, mediaUrl } from "../api";
import {
  CutMethod,
  DataClassification,
  JobResponse,
  JobStatus,
  ProfileStatus,
  VideoProcessResult,
  VideoStage,
  WorkProfile,
} from "../types";
import { AlertTriangle, CheckCircle2, Clapperboard, ListChecks, RotateCcw, Scissors, ShieldCheck, Upload } from "lucide-react";

// Spec 08 §3, page 4 "Tải dữ liệu" — video: POST /videos, POST /videos/{id}/process, then poll GET /jobs/{id}.
const ACCEPTED_TYPES = "video/*,.mkv";
const POLL_INTERVAL_MS = 3000;
// The job runs for minutes (one VLM call per 10 s window, twice): remember it across reloads.
const STORAGE_KEY = "mentormind_video_job";

const CLASSIFICATION_LABELS: Record<DataClassification, string> = {
  public:               "Công khai",
  synthetic:            "Dữ liệu tổng hợp",
  factory_confidential: "Mật – dữ liệu nhà máy",
};

const JOB_STATUS: Record<JobStatus, { label: string; badge: string }> = {
  queued:  { label: "Đang chờ",   badge: "badge badge-draft" },
  running: { label: "Đang phân tích", badge: "badge badge-review" },
  done:    { label: "Hoàn tất",   badge: "badge badge-approved" },
  failed:  { label: "Lỗi",        badge: "badge badge-rejected" },
};

// Spec 03 FR-03: how the video is cut into segments; a missing library falls back down this list.
const METHOD_LABELS: Record<CutMethod, string> = {
  hand_activity: "Theo nhịp tay (MediaPipe)",
  scene:         "Theo cảnh (PySceneDetect)",
  fixed_window:  "Cố định 10 giây",
};

// Spec 08 §2: the stages of a video job, in order, with what `done/total` counts in each.
const STAGES: { id: VideoStage; label: string; unit: string }[] = [
  { id: "cut",        label: "Cắt đoạn",            unit: "đoạn" },
  { id: "transcribe", label: "Nhận dạng lời nói",    unit: "giây audio" },
  { id: "describe",   label: "VLM mô tả",            unit: "lượt đoạn (A, B)" },
  { id: "merge",      label: "Gộp bước",             unit: "" },
  { id: "reasons",    label: "Đề xuất lý do",        unit: "bước có lời chuyên gia" },
];

const STATUS_LABELS: Record<ProfileStatus, string> = {
  draft:     "Nháp",
  in_review: "Đang duyệt",
  approved:  "Đã duyệt",
  rejected:  "Từ chối",
};

interface TrackedJob {
  jobId: string;
  videoId: string;
  fileName: string;
  processId: string;
  startedAt: number;
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function loadTracked(): TrackedJob | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as TrackedJob) : null;
  } catch {
    return null;
  }
}

function saveTracked(job: TrackedJob | null) {
  try {
    if (job) localStorage.setItem(STORAGE_KEY, JSON.stringify(job));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage blocked: tracking only lasts while the page stays open
  }
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail; // the API's own messages are Vietnamese
    if (err.status === 422) return "Yêu cầu không hợp lệ: cần một tệp video, mã công đoạn và nhãn dữ liệu.";
    return `Máy chủ báo lỗi (mã ${err.status}). Vui lòng thử lại.`;
  }
  return "Không kết nối được tới máy chủ API. Kiểm tra backend đang chạy rồi thử lại.";
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  return minutes > 0 ? `${minutes} phút ${total % 60} giây` : `${total} giây`;
}

const formatTime = (t?: number | null) => (t == null ? "—" : `${t.toFixed(1)}s`);

export function UploadVideoCard({ onReview }: { onReview: (videoId: string, processId: string) => void }) {
  const [file,           setFile]           = useState<File | null>(null);
  const [processId,      setProcessId]      = useState("PACK01");
  const [method,         setMethod]         = useState<CutMethod | "">("");
  const [classification, setClassification] = useState<DataClassification | "">("");
  const [busy,           setBusy]           = useState(false);
  const [tracked,        setTracked]        = useState<TrackedJob | null>(() => loadTracked());
  const [job,            setJob]            = useState<JobResponse<VideoProcessResult> | null>(null);
  const [steps,          setSteps]          = useState<WorkProfile[]>([]);
  const [errorMsg,       setErrorMsg]       = useState<string | null>(null);
  const [now,            setNow]            = useState(Date.now());
  const fileInput = useRef<HTMLInputElement>(null);

  // Polling stops when the user leaves the tab and resumes from localStorage when they come back.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!tracked) return;
    let cancelled = false;
    const follow = async () => {
      try {
        for (;;) {
          const current = await api.getJob<VideoProcessResult>(tracked.jobId);
          if (cancelled || !mounted.current) return;
          setJob(current);
          if (current.status === "done") {
            const all = await api.getProfiles(tracked.processId);
            if (cancelled || !mounted.current) return;
            setSteps(
              all
                .filter((p) => p.evidence.video_id === tracked.videoId)
                .sort((a, b) => (a.evidence.t_start ?? 0) - (b.evidence.t_start ?? 0)),
            );
            return;
          }
          if (current.status === "failed") return;
          await sleep(POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (!cancelled && mounted.current) setErrorMsg(describeError(err));
      }
    };
    follow();
    return () => {
      cancelled = true;
    };
  }, [tracked]);

  // Elapsed-time display while the job runs.
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [job]);

  const handleUpload = async () => {
    if (!file || !classification || !processId.trim()) return;
    setBusy(true);
    setErrorMsg(null);
    setJob(null);
    setSteps([]);
    try {
      const asset = await api.uploadVideo(file, processId.trim(), classification);
      const { job_id } = await api.processVideo(asset.video_id, method || null);
      const next: TrackedJob = {
        jobId: job_id,
        videoId: asset.video_id,
        fileName: file.name,
        processId: asset.process_id || processId.trim(),
        startedAt: Date.now(),
      };
      saveTracked(next);
      setTracked(next);
    } catch (err) {
      setErrorMsg(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReset = () => {
    saveTracked(null);
    setTracked(null);
    setJob(null);
    setSteps([]);
    setErrorMsg(null);
    setFile(null);
    if (fileInput.current) fileInput.current.value = "";
  };

  const result = job?.result ?? null;
  const progress = result?.progress ?? null;
  const percent = progress && progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
  const stageIndex = progress ? STAGES.findIndex((s) => s.id === progress.stage) : -1;
  const running = !!tracked && (!job || job.status === "queued" || job.status === "running");
  const canUpload = !busy && !running && !!file && classification !== "" && processId.trim() !== "";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <div className="card-icon ci-red">
              <Clapperboard size={14} color="var(--denso-red)" />
            </div>
            Tải video thao tác
          </div>
          <span className="badge badge-cyan">MP4 · MOV · MKV · WEBM</span>
        </div>

        <div className="card-body">
          <div className="data-grid data-grid-2" style={{ marginBottom: "1.1rem" }}>
            <div className="form-group" style={{ gridColumn: "1 / -1" }}>
              <label className="form-label" htmlFor="input-video">
                <Clapperboard size={12} color="var(--denso-red)" />
                Tệp video
              </label>
              {/* Hidden: the native button's text follows the browser language, ours is Vietnamese. */}
              <input
                id="input-video"
                ref={fileInput}
                type="file"
                accept={ACCEPTED_TYPES}
                hidden
                disabled={busy || running}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <button
                  id="btn-choose-video"
                  type="button"
                  className="btn btn-ghost"
                  disabled={busy || running}
                  onClick={() => fileInput.current?.click()}
                >
                  <Clapperboard size={14} />
                  Chọn video…
                </button>
                <span style={{ fontSize: "0.9rem", color: file ? "var(--text-high)" : "var(--text-muted)" }}>
                  {file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB` : "Chưa chọn video"}
                </span>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="input-video-process">
                <ListChecks size={12} color="var(--accent-cyan)" />
                Mã công đoạn
              </label>
              <input
                id="input-video-process"
                className="form-input"
                value={processId}
                disabled={busy || running}
                onChange={(e) => setProcessId(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="select-video-method">
                <Scissors size={12} color="var(--accent-cyan)" />
                Cách cắt đoạn
              </label>
              <select
                id="select-video-method"
                className="form-select"
                value={method}
                disabled={busy || running}
                onChange={(e) => setMethod(e.target.value as CutMethod | "")}
              >
                <option value="">Mặc định của máy chủ (KNOWHOW_VIDEO_METHOD)</option>
                {(Object.keys(METHOD_LABELS) as CutMethod[]).map((m) => (
                  <option key={m} value={m}>{METHOD_LABELS[m]}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="select-video-classification">
                <ShieldCheck size={12} color="var(--accent-cyan)" />
                Nhãn dữ liệu (bắt buộc)
              </label>
              <select
                id="select-video-classification"
                className="form-select"
                value={classification}
                disabled={busy || running}
                onChange={(e) => setClassification(e.target.value as DataClassification)}
              >
                <option value="" disabled>— Chọn nhãn dữ liệu —</option>
                {(Object.keys(CLASSIFICATION_LABELS) as DataClassification[]).map((c) => (
                  <option key={c} value={c}>{CLASSIFICATION_LABELS[c]}</option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
            <span style={{ fontSize: "0.9rem", color: "var(--text-muted)" }}>
              Video được cắt thành đoạn, có audio thì nhận dạng lời chuyên gia; VLM mô tả từng đoạn thành các bước nháp, mỗi bước kèm lời nói về chính nó.
            </span>
            <button id="btn-upload-video" className="btn btn-primary btn-lg" onClick={handleUpload} disabled={!canUpload}>
              {busy ? <div className="spinner" /> : <Upload size={16} />}
              {busy ? "Đang tải lên…" : "Tải lên & phân tích"}
            </button>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="alert alert-error">
          <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 2 }} />
          <span>{errorMsg}</span>
        </div>
      )}

      {tracked && (
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <div className="card-icon ci-green">
                <ListChecks size={14} color="var(--status-success)" />
              </div>
              Phân tích video
            </div>
            {job && <span className={JOB_STATUS[job.status].badge}>{JOB_STATUS[job.status].label}</span>}
          </div>

          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <span className="mono-tag">{tracked.fileName}</span>
              <span className="mono-tag">{tracked.videoId}</span>
              <span className="mono-tag">{tracked.processId}</span>
              <span className="mono-tag">{tracked.jobId}</span>
            </div>

            {running && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                <div id="video-stages" style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                  {STAGES.map((stage, i) => (
                    <span
                      key={stage.id}
                      className={`badge ${i < stageIndex ? "badge-approved" : i === stageIndex ? "badge-review" : "badge-muted"}`}
                    >
                      {i < stageIndex ? "✓ " : ""}{i + 1}. {stage.label}
                    </span>
                  ))}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem" }}>
                  <span>
                    {progress && stageIndex >= 0
                      ? STAGES[stageIndex].unit && progress.total > 0
                        ? `${STAGES[stageIndex].label}: ${Math.round(progress.done)}/${Math.round(progress.total)} ${STAGES[stageIndex].unit}`
                        : `${STAGES[stageIndex].label}…`
                      : "Đang đọc video…"}
                  </span>
                  <span style={{ color: "var(--text-muted)" }}>Đã chạy {formatElapsed(now - tracked.startedAt)}</span>
                </div>
                <div className="confidence-track" style={{ width: "100%", height: 10 }}>
                  <div className="confidence-fill" style={{ width: `${percent}%` }} />
                </div>
                <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                  Có thể chuyển trang khác; quay lại đây vẫn theo dõi tiếp.
                </span>
              </div>
            )}

            {job?.status === "failed" && (
              <div className="alert alert-error">
                <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 2 }} />
                <span>Phân tích thất bại: {job.error || "không rõ nguyên nhân."}</span>
              </div>
            )}

            {job?.status === "done" && result && (
              <>
                <div className="alert alert-success">
                  <CheckCircle2 size={15} style={{ flexShrink: 0, marginTop: 2 }} />
                  <span>
                    Hoàn tất: cắt {METHOD_LABELS[result.method_used ?? result.method]?.toLowerCase()}
                    {result.method_used && result.method_used !== result.method && ` (không dùng được ${METHOD_LABELS[result.method].toLowerCase()})`}
                    {" "}→ {result.segments} đoạn → <strong>{result.profiles.length} bước nháp</strong> chờ chuyên gia duyệt.
                    {result.failed_segments.length > 0 && ` ${result.failed_segments.length} đoạn VLM trả lỗi.`}
                    {result.transcript_lines === 0
                      ? " Không nhận được lời nói nào: lý do (reason) để trống, chuyên gia nhập khi duyệt."
                      : ` Lời nói: ${result.transcript_lines} câu, ${result.steps_with_excerpt} bước có lời chuyên gia, ${result.reasons_filled} bước được đề xuất lý do (chờ duyệt).`}
                  </span>
                </div>

                <div style={{ overflowX: "auto" }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Keyframe</th>
                        <th>Bước</th>
                        <th>Thời gian</th>
                        <th>Trạng thái</th>
                      </tr>
                    </thead>
                    <tbody>
                      {steps.map((p, i) => {
                        const keyframe = mediaUrl(p.evidence.keyframes?.[Math.min(1, (p.evidence.keyframes?.length ?? 1) - 1)]);
                        return (
                          <tr key={p.profile_id}>
                            <td className="num">{i + 1}</td>
                            <td>
                              {keyframe ? (
                                <img src={keyframe} alt={p.step} style={{ width: 120, borderRadius: 4, display: "block" }} />
                              ) : (
                                "—"
                              )}
                            </td>
                            <td>
                              <div style={{ fontWeight: 600 }}>{p.step}</div>
                              <div className="mono" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{p.profile_id}</div>
                            </td>
                            <td className="mono">{formatTime(p.evidence.t_start)} – {formatTime(p.evidence.t_end)}</td>
                            <td><span className="badge badge-draft">{STATUS_LABELS[p.status]}</span></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end", flexWrap: "wrap" }}>
              {job?.status === "done" && (
                <button id="btn-review-video" className="btn btn-success btn-lg" onClick={() => onReview(tracked.videoId, tracked.processId)}>
                  <ListChecks size={16} />
                  Duyệt các bước này
                </button>
              )}
              {!running && (
                <button id="btn-reset-video" className="btn btn-ghost" onClick={handleReset}>
                  <RotateCcw size={14} />
                  Tải video khác
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
