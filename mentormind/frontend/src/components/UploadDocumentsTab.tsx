import React, { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { ConfirmDialog } from "./ConfirmDialog";
import {
  DataClassification,
  DocumentInfo,
  DocumentIngestFile,
  DocumentIngestResult,
  JobResponse,
  JobStatus,
} from "../types";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FileText,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Upload,
} from "lucide-react";

// Spec 08 §3, page 4 "Tải tài liệu": upload -> POST /ingest/documents, then poll GET /jobs/{id}.
const ACCEPTED_TYPES = ".pdf,.docx,.xlsx,.pptx";
const POLL_INTERVAL_MS = 2000;
const STORAGE_KEY = "mentormind_document_job";

const CLASSIFICATION_LABELS: Record<DataClassification, string> = {
  public:               "Công khai",
  synthetic:            "Dữ liệu tổng hợp",
  factory_confidential: "Mật – dữ liệu nhà máy",
};

const JOB_STATUS: Record<JobStatus, { label: string; badge: string }> = {
  queued:  { label: "Đang chờ",   badge: "badge badge-draft" },
  running: { label: "Đang xử lý", badge: "badge badge-review" },
  done:    { label: "Hoàn tất",   badge: "badge badge-approved" },
  failed:  { label: "Lỗi",        badge: "badge badge-rejected" },
};

interface TrackedJob {
  jobId: string;
  fileNames: string[];
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

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  return minutes > 0 ? `${minutes} phút ${total % 60} giây` : `${total} giây`;
}

// Vietnamese message for the user; never a stack trace.
function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail; // the API's own messages are Vietnamese
    if (err.status === 422) return "Yêu cầu không hợp lệ: cần ít nhất một tệp và một nhãn dữ liệu.";
    return `Máy chủ báo lỗi (mã ${err.status}). Vui lòng thử lại.`;
  }
  return "Không kết nối được tới máy chủ API. Kiểm tra backend đang chạy rồi thử lại.";
}

function FileOutcome({ file }: { file: DocumentIngestFile }) {
  if (file.error) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", alignItems: "flex-start" }}>
        <span className="badge badge-rejected">Lỗi</span>
        <span style={{ color: "var(--status-danger-text)" }}>{file.error}</span>
      </div>
    );
  }
  if (file.skipped) return <span className="badge badge-muted">Bỏ qua – định dạng không hỗ trợ</span>;
  return <span className="badge badge-approved">Xong</span>;
}

export function UploadDocumentsTab() {
  const [files,          setFiles]          = useState<File[]>([]);
  const [classification, setClassification] = useState<DataClassification | "">("");
  const [busy,           setBusy]           = useState(false);
  const [tracked,        setTracked]        = useState<TrackedJob | null>(() => loadTracked());
  const [job,            setJob]            = useState<JobResponse<DocumentIngestResult> | null>(null);
  const [errorMsg,       setErrorMsg]       = useState<string | null>(null);
  const [now,            setNow]            = useState(Date.now());
  // Indexed documents (GET /documents) and their deletion; null = not loaded yet.
  const [documents,      setDocuments]      = useState<DocumentInfo[] | null>(null);
  const [docsError,      setDocsError]      = useState<string | null>(null);
  const [deleting,       setDeleting]       = useState<string | null>(null);
  const [toDelete,       setToDelete]       = useState<DocumentInfo | null>(null);
  const [docMsg,         setDocMsg]         = useState<{ type: "success" | "error"; text: string } | null>(null);
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
          const current = await api.getJob<DocumentIngestResult>(tracked.jobId);
          if (cancelled || !mounted.current) return;
          setJob(current);
          if (current.status === "done" || current.status === "failed") return;
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
  const running = job !== null && (job.status === "queued" || job.status === "running");
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);

  const loadDocuments = async () => {
    try {
      const list = await api.getDocuments();
      if (!mounted.current) return;
      setDocuments(list);
      setDocsError(null);
    } catch (err) {
      if (mounted.current) setDocsError(describeError(err));
    }
  };

  // On open, and once a document job ends (its files join the list).
  const jobEnded = job?.status === "done" || job?.status === "failed";
  useEffect(() => { loadDocuments(); }, [jobEnded]);

  const handleDeleteDocument = async (doc: DocumentInfo) => {
    setToDelete(null);
    setDeleting(doc.doc_id);
    setDocMsg(null);
    try {
      const r = await api.deleteDocument(doc.doc_id);
      setDocMsg({
        type: "success",
        text: `Đã xoá ${doc.name} (${doc.doc_id}): ${r.chunks_deleted} chunk khỏi kho tìm kiếm, ${r.uploads_removed} tệp tải lên.`,
      });
      await loadDocuments();
    } catch (err) {
      setDocMsg({ type: "error", text: `Không xoá được ${doc.name}: ${describeError(err)}` });
    } finally {
      setDeleting(null);
    }
  };

  const handleUpload = async () => {
    if (files.length === 0 || !classification) return;
    setBusy(true);
    setErrorMsg(null);
    setJob(null);
    try {
      const { job_id } = await api.uploadDocuments(files, classification);
      const next: TrackedJob = { jobId: job_id, fileNames: files.map((f) => f.name), startedAt: Date.now() };
      saveTracked(next);
      setTracked(next);
    } catch (err) {
      setErrorMsg(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  const result = job?.result ?? null;
  const locked = busy || running || (tracked !== null && job === null && errorMsg === null);
  const canUpload = !locked && files.length > 0 && classification !== "";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      {/* ── Upload form ── */}
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <div className="card-icon ci-cyan">
              <Upload size={14} color="var(--accent-cyan)" />
            </div>
            Tải tài liệu vào kho tri thức
          </div>
          <span className="badge badge-cyan">PDF · DOCX · XLSX · PPTX</span>
        </div>

        <div className="card-body">
          <div className="data-grid data-grid-2" style={{ marginBottom: "1.1rem" }}>
            <div className="form-group">
              <label className="form-label" htmlFor="input-documents">
                <FileText size={12} color="var(--accent-cyan)" />
                Tệp tài liệu
              </label>
              {/* Hidden: the native button's text follows the browser language, ours is Vietnamese. */}
              <input
                id="input-documents"
                ref={fileInput}
                type="file"
                multiple
                accept={ACCEPTED_TYPES}
                hidden
                disabled={locked}
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <button
                  id="btn-choose-documents"
                  type="button"
                  className="btn btn-ghost"
                  disabled={locked}
                  onClick={() => fileInput.current?.click()}
                >
                  <FileText size={14} />
                  Chọn tệp…
                </button>
                {files.length === 0 ? (
                  <span style={{ fontSize: "0.9rem", color: "var(--text-muted)" }}>Chưa chọn tệp nào</span>
                ) : (
                  <div className="chip-list">
                    {files.map((f) => (
                      <span key={f.name} className="mono-tag">{f.name}</span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="select-classification">
                <ShieldCheck size={12} color="var(--accent-cyan)" />
                Nhãn dữ liệu (bắt buộc)
              </label>
              <select
                id="select-classification"
                className="form-select"
                value={classification}
                disabled={locked}
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
              {files.length === 0 || !classification
                ? "Chọn ít nhất một tệp và nhãn dữ liệu để tải lên."
                : `${files.length} tệp · nhãn: ${CLASSIFICATION_LABELS[classification]}`}
            </span>
            <button
              id="btn-upload-documents"
              className="btn btn-primary btn-lg"
              onClick={handleUpload}
              disabled={!canUpload}
            >
              {locked ? <div className="spinner" /> : <Upload size={16} />}
              {busy ? "Đang tải lên…" : locked ? "Đang xử lý…" : "Tải lên & xử lý"}
            </button>
          </div>
        </div>
      </div>

      {/* ── Error ── */}
      {errorMsg && (
        <div className="alert alert-error">
          <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 2 }} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* ── Job progress & per-file result ── */}
      {job && (
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              <div className="card-icon ci-green">
                <Database size={14} color="var(--status-success)" />
              </div>
              Kết quả xử lý
            </div>
            <span className={JOB_STATUS[job.status].badge}>{JOB_STATUS[job.status].label}</span>
          </div>

          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div className="chip-list">
              {tracked?.fileNames.map((name) => (
                <span key={name} className="mono-tag">{name}</span>
              ))}
              <span className="mono-tag">{job.job_id}</span>
            </div>

            {running && (
              <div className="loading-center" style={{ padding: "1.5rem 1rem" }}>
                <div className="spinner spinner-lg" />
                <span>Đang tách chunk và đưa vào kho tìm kiếm… (tự cập nhật mỗi 2 giây)</span>
                {tracked && <span>Đã chạy {formatElapsed(now - tracked.startedAt)}</span>}
              </div>
            )}

            {job.status === "failed" && (
              <div className="alert alert-error">
                <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 2 }} />
                <span>Xử lý thất bại: {job.error || "không rõ nguyên nhân."}</span>
              </div>
            )}

            {job.status === "done" && result && (
              <div className="alert alert-success">
                <CheckCircle2 size={15} style={{ flexShrink: 0, marginTop: 2 }} />
                <span>
                  Hoàn tất: tài liệu đã được tách chunk và index với nhãn{" "}
                  <strong>{CLASSIFICATION_LABELS[result.classification]}</strong>.
                </span>
              </div>
            )}

            {result && result.files.length > 0 && (
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Tệp</th>
                      <th>doc_id</th>
                      <th>Extractor</th>
                      <th className="num">Số trang</th>
                      <th className="num">Số chunk</th>
                      <th>Kết quả</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.files.map((f) => (
                      <tr key={f.name}>
                        <td>{f.name}</td>
                        <td className="mono">{f.doc_id ?? "—"}</td>
                        <td>{f.extractor ?? "—"}</td>
                        <td className="num">{f.pages}</td>
                        <td className="num">{f.chunks}</td>
                        <td><FileOutcome file={f} /></td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={4}>Tổng số chunk đã index</td>
                      <td className="num">{result.chunks_indexed}</td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Indexed documents (GET /documents) with delete ── */}
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <div className="card-icon ci-cyan">
              <Database size={14} color="var(--accent-cyan)" />
            </div>
            Tài liệu đã index
            {documents && <span className="badge badge-cyan" style={{ marginLeft: "0.3rem" }}>{documents.length}</span>}
          </div>
          <button id="btn-refresh-documents" className="btn btn-ghost btn-sm" onClick={loadDocuments} disabled={deleting !== null}>
            <RefreshCw size={13} />
            Tải lại
          </button>
        </div>

        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {docMsg && (
            <div className={`alert alert-${docMsg.type}`}>
              {docMsg.type === "success"
                ? <CheckCircle2 size={15} style={{ flexShrink: 0, marginTop: 2 }} />
                : <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 2 }} />}
              <span>{docMsg.text}</span>
            </div>
          )}

          {docsError ? (
            <div className="alert alert-error">
              <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 2 }} />
              <span>Không đọc được danh sách tài liệu: {docsError}</span>
            </div>
          ) : documents === null ? (
            <div className="loading-center" style={{ padding: "1.5rem 1rem" }}>
              <div className="spinner" />
              <span>Đang đọc danh sách tài liệu…</span>
            </div>
          ) : documents.length === 0 ? (
            <span style={{ fontSize: "0.9rem", color: "var(--text-muted)" }}>Chưa có tài liệu nào trong kho tìm kiếm.</span>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Tệp</th>
                    <th>doc_id</th>
                    <th>Nhãn dữ liệu</th>
                    <th className="num">Số chunk</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {documents.map((d) => (
                    <tr key={d.doc_id}>
                      <td>{d.name}</td>
                      <td className="mono">{d.doc_id}</td>
                      <td>{d.data_classification ? CLASSIFICATION_LABELS[d.data_classification] : "—"}</td>
                      <td className="num">{d.chunks}</td>
                      <td style={{ textAlign: "right" }}>
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => setToDelete(d)}
                          disabled={deleting !== null}
                        >
                          {deleting === d.doc_id ? <div className="spinner" /> : <Trash2 size={13} />}
                          {deleting === d.doc_id ? "Đang xoá…" : "Xoá"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {toDelete && (
        <ConfirmDialog title="Xoá tài liệu này?" onConfirm={() => handleDeleteDocument(toDelete)} onCancel={() => setToDelete(null)}>
          <p>
            Tài liệu <strong>{toDelete.name}</strong> ({toDelete.doc_id}, {toDelete.chunks} chunk) bị gỡ khỏi kho tìm kiếm:
            trợ lý sẽ không trích dẫn nó nữa.
          </p>
          <p>Tệp chunk và tệp đã tải lên trên máy chủ cũng bị xoá.</p>
        </ConfirmDialog>
      )}
    </div>
  );
}
