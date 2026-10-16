import React, { useEffect, useMemo, useState } from "react";
import { api, mediaUrl } from "../api";
import { ConfirmDialog } from "./ConfirmDialog";
import {
  ErrorTag,
  ProfileDeleteResult,
  ProfilePatchRequest,
  ProfileStatus,
  ReasonSource,
  ReviewRequest,
  Segment,
  WorkProfile,
} from "../types";
import {
  CheckCircle,
  XCircle,
  Save,
  AlertTriangle,
  UserCheck,
  Filter,
  Video,
  RefreshCw,
  Shield,
  Pencil,
  Layers,
  Eye,
  Wrench,
  ShieldCheck,
  FileText,
  MessageSquareQuote,
  Trash2,
} from "lucide-react";

// ── Status badge class helper ─────────────────────────────────
function statusBadge(s: ProfileStatus) {
  const map: Record<ProfileStatus, string> = {
    draft:     "badge badge-draft",
    in_review: "badge badge-review",
    approved:  "badge badge-approved",
    rejected:  "badge badge-rejected",
  };
  return map[s] || "badge badge-muted";
}

const formatTime = (t?: number | null) => (t == null ? "—" : `${t.toFixed(1)}s`);

// What the open confirmation dialog would delete (spec 08 §3: every delete asks first).
// For a video, `steps` counts all its steps (filters ignored); null when they could not be listed.
type DeleteTarget =
  | { kind: "step"; profile: WorkProfile }
  | { kind: "steps"; ids: string[] }
  | { kind: "video"; videoId: string; steps: { total: number; published: number } | null };

// In the knowledge graph: the API says so (an approved step edited back to in_review still is).
const isPublished = (p: WorkProfile) => p.published ?? p.status === "approved";

// Vietnamese summary of DELETE /profiles/{id}, POST /profiles/delete or DELETE /videos/{id}.
function deletionMessage(r: ProfileDeleteResult): { type: "success" | "error"; text: string } {
  let text = `Đã xoá ${r.deleted.length} bước`;
  if (r.unpublished.length > 0) text += ` (${r.unpublished.length} bước đã duyệt được gỡ khỏi đồ thị tri thức)`;
  text += ".";
  if (r.failed.length > 0) {
    text += ` Chưa xoá được ${r.failed.length} bước: ${r.failed.map((f) => `${f.profile_id} — ${f.error}`).join("; ")}.`;
  }
  return { type: r.failed.length > 0 ? "error" : "success", text };
}

// Up to 3 keyframes of a step: first, middle and last (a merged step carries 3 per segment).
function pickKeyframes(keyframes: string[] = []): string[] {
  if (keyframes.length <= 3) return keyframes;
  return [keyframes[0], keyframes[Math.floor(keyframes.length / 2)], keyframes[keyframes.length - 1]];
}

// Process lines named in the filter; any other code typed at video upload is listed as-is.
const PROCESS_LABELS: Record<string, string> = {
  PACK01: "PACK01 — Packaging Line",
  ASSY02: "ASSY02 — Assembly Line",
};

export function ReviewProfilesTab({
  initialVideoId = null,
  initialProcessId = null,
}: {
  initialVideoId?: string | null;
  initialProcessId?: string | null;
}) {
  const [profiles,        setProfiles]        = useState<WorkProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<WorkProfile | null>(null);
  const [selectedProcess, setSelectedProcess] = useState<string>(initialProcessId ?? "PACK01");
  // Every process code that has steps (GET /profiles without a filter), for the process filter.
  const [knownProcesses,  setKnownProcesses]  = useState<string[]>([]);
  const [selectedStatus,  setSelectedStatus]  = useState<string>("");
  const [selectedVideo,   setSelectedVideo]   = useState<string>(initialVideoId ?? "");
  // Segments per video (GET /videos/{id}/segments) for the clip player; null = none saved for that video.
  const [segments,        setSegments]        = useState<Record<string, Segment[] | null>>({});
  const [loading,         setLoading]         = useState(false);
  // The action whose request is in flight: approve syncs Neo4j + pgvector (~5 s), so show it.
  const [pending,         setPending]         = useState<"approve" | "reject" | "save" | "delete-step" | "delete-steps" | "delete-video" | null>(null);
  // Steps ticked in the list for "Xoá các bước đã chọn", and the delete waiting for confirmation.
  const [checked,         setChecked]         = useState<string[]>([]);
  const [confirm,         setConfirm]         = useState<DeleteTarget | null>(null);
  const [actionMsg,       setActionMsg]       = useState<{ type: "success" | "error" | "warning"; text: string } | null>(null);

  // Editable form state
  const [step,         setStep]         = useState("");
  const [handAction,   setHandAction]   = useState("");
  const [keyPoint,     setKeyPoint]     = useState("");
  const [reason,       setReason]       = useState("");
  const [reasonSource, setReasonSource] = useState<ReasonSource | "">("");
  const [passCriteria, setPassCriteria] = useState("");

  // Review state
  const [reviewer,           setReviewer]           = useState("Lead Engineer (DENSO QA)");
  const [reviewComment,      setReviewComment]      = useState("");
  const [selectedErrorTags,  setSelectedErrorTags]  = useState<ErrorTag[]>([]);

  const loadProfiles = async () => {
    setLoading(true);
    try {
      const data = await api.getProfiles(
        selectedProcess || undefined,
        selectedStatus ? (selectedStatus as ProfileStatus) : undefined
      );
      setProfiles(data);
    } catch (err: any) {
      setActionMsg({ type: "error", text: err.message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadProfiles(); }, [selectedProcess, selectedStatus]);
  useEffect(() => { if (initialVideoId) setSelectedVideo(initialVideoId); }, [initialVideoId]);
  useEffect(() => { if (initialProcessId) setSelectedProcess(initialProcessId); }, [initialProcessId]);
  useEffect(() => {
    api
      .getProfiles()
      .then((all) => setKnownProcesses(Array.from(new Set(all.map((p) => p.process_id))).sort()))
      .catch(() => setKnownProcesses([]));
  }, []);
  const processOptions = useMemo(
    () => Array.from(new Set([...Object.keys(PROCESS_LABELS), ...knownProcesses, selectedProcess].filter(Boolean))),
    [knownProcesses, selectedProcess],
  );

  const videoIds = useMemo(
    () => Array.from(new Set(profiles.map((p) => p.evidence.video_id).filter((v): v is string => !!v))).sort(),
    [profiles],
  );
  // The steps of one video read in time order.
  const visible = useMemo(
    () =>
      profiles
        .filter((p) => !selectedVideo || p.evidence.video_id === selectedVideo)
        .sort(
          (a, b) =>
            (a.evidence.video_id ?? "").localeCompare(b.evidence.video_id ?? "") ||
            (a.evidence.t_start ?? 0) - (b.evidence.t_start ?? 0),
        ),
    [profiles, selectedVideo],
  );

  useEffect(() => {
    if (visible.length === 0) {
      setSelectedProfile(null);
    } else if (!selectedProfile || !visible.some((p) => p.profile_id === selectedProfile.profile_id)) {
      selectProfile(visible[0], true); // keep the message, e.g. that the selected step was just deleted
    }
  }, [visible]);

  // Only the ticked steps still on screen are deleted: a filter change never deletes hidden ones.
  const checkedVisible = visible.filter((p) => checked.includes(p.profile_id)).map((p) => p.profile_id);
  const allChecked = visible.length > 0 && checkedVisible.length === visible.length;
  const toggleChecked = (id: string) =>
    setChecked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  const toggleAll = () => setChecked(allChecked ? [] : visible.map((p) => p.profile_id));

  const selectedVideoId = selectedProfile?.evidence.video_id ?? null;
  useEffect(() => {
    if (!selectedVideoId || selectedVideoId in segments) return;
    api
      .getVideoSegments(selectedVideoId)
      .then((list) => setSegments((prev) => ({ ...prev, [selectedVideoId]: list })))
      .catch(() => setSegments((prev) => ({ ...prev, [selectedVideoId]: null })));
  }, [selectedVideoId]);

  const selectProfile = (p: WorkProfile, keepMessage = false) => {
    setSelectedProfile(p);
    setStep(p.step || "");
    setHandAction(p.hand_action || "");
    setKeyPoint(p.key_point || "");
    setReason(p.reason || "");
    setReasonSource(p.reason_source || "");
    setPassCriteria(p.pass_criteria || "");
    setReviewComment("");
    setSelectedErrorTags([]);
    if (!keepMessage) setActionMsg(null);
  };

  const hasReasonWithoutSource = reason.trim().length > 0 && !reasonSource;

  const handleSavePatch = async () => {
    if (!selectedProfile) return;
    try {
      const patchData: ProfilePatchRequest = {
        step,
        hand_action:   handAction || undefined,
        key_point:     keyPoint || undefined,
        reason:        reason.trim() ? reason : undefined,
        reason_source: reasonSource ? (reasonSource as ReasonSource) : null,
        pass_criteria: passCriteria || undefined,
      };
      setPending("save");
      const updated = await api.patchProfile(selectedProfile.profile_id, patchData);
      selectProfile(updated); // resets the form and the message: the confirmation comes after
      setActionMsg({ type: "success", text: `SAVED: Profile ${updated.profile_id} updated to v${updated.version} — status IN_REVIEW.` });
      loadProfiles();
    } catch (err: any) {
      setActionMsg({ type: "error", text: `WRITE ERROR: ${err.message}` });
    } finally {
      setPending(null);
    }
  };

  const handleApprove = async () => {
    if (!selectedProfile) return;
    if (hasReasonWithoutSource) {
      setActionMsg({ type: "warning", text: "AC-08 VIOLATION: reason_source must be set before approving." });
      return;
    }
    try {
      const req: ReviewRequest = {
        action:   "approve",
        reviewer: reviewer.trim() || "QA Engineer",
        comment:  reviewComment || "Meets operation standard",
      };
      setPending("approve");
      const updated = await api.reviewProfile(selectedProfile.profile_id, req);
      selectProfile(updated); // resets the form and the message: the confirmation comes after
      setActionMsg({ type: "success", text: `APPROVED: ${updated.profile_id} verified & synced to Neo4j Knowledge Graph.` });
      loadProfiles();
    } catch (err: any) {
      setActionMsg({ type: "error", text: `APPROVE FAILED: ${err.message}` });
    } finally {
      setPending(null);
    }
  };

  const handleReject = async () => {
    if (!selectedProfile) return;
    if (!reviewComment.trim()) {
      setActionMsg({ type: "error", text: "AC-03 REQUIRED: A rejection comment is mandatory." });
      return;
    }
    try {
      const req: ReviewRequest = {
        action:     "reject",
        reviewer:   reviewer.trim() || "QA Engineer",
        comment:    reviewComment.trim(),
        error_tags: selectedErrorTags,
      };
      setPending("reject");
      const updated = await api.reviewProfile(selectedProfile.profile_id, req);
      selectProfile(updated); // resets the form and the message: the confirmation comes after
      setActionMsg({ type: "warning", text: `REJECTED: ${updated.profile_id} — status set to REJECTED.` });
      loadProfiles();
    } catch (err: any) {
      setActionMsg({ type: "error", text: `ERROR: ${err.message}` });
    } finally {
      setPending(null);
    }
  };

  const handleDelete = async (target: DeleteTarget) => {
    setConfirm(null);
    setActionMsg(null);
    try {
      if (target.kind === "video") {
        setPending("delete-video");
        const r = await api.deleteVideo(target.videoId);
        const msg = deletionMessage(r);
        setActionMsg(
          r.failed.length > 0
            ? { type: "error", text: `${msg.text} Tệp của video ${r.video_id} được giữ lại cho tới khi xoá được các bước này.` }
            : { type: "success", text: `Đã xoá video ${r.video_id} — ${msg.text} Đã xoá ${r.files_removed} tệp trên máy chủ.` },
        );
        if (r.failed.length === 0) {
          setSelectedVideo("");
          setSegments((prev) => {
            const next = { ...prev };
            delete next[r.video_id];
            return next;
          });
        }
        setChecked((prev) => prev.filter((id) => !r.deleted.includes(id)));
      } else {
        setPending(target.kind === "step" ? "delete-step" : "delete-steps");
        const r =
          target.kind === "step"
            ? await api.deleteProfile(target.profile.profile_id)
            : await api.deleteProfiles(target.ids);
        setActionMsg(deletionMessage(r));
        setChecked((prev) => prev.filter((id) => !r.deleted.includes(id)));
      }
      await loadProfiles();
    } catch (err: any) {
      setActionMsg({ type: "error", text: `XOÁ THẤT BẠI: ${err.message}` });
    } finally {
      setPending(null);
    }
  };

  const publishedAmong = (ids: string[]) =>
    profiles.filter((p) => ids.includes(p.profile_id) && isPublished(p)).length;

  // Counts every step of the video, not only those the filters show, before asking to confirm.
  const askDeleteVideo = async (videoId: string) => {
    let steps: { total: number; published: number } | null = null;
    try {
      const all = (await api.getProfiles()).filter((p) => p.evidence.video_id === videoId);
      steps = { total: all.length, published: all.filter(isPublished).length };
    } catch {
      steps = null; // the dialog then speaks without numbers
    }
    setConfirm({ kind: "video", videoId, steps });
  };

  const confirmTitle = (t: DeleteTarget) =>
    t.kind === "step" ? "Xoá bước này?" : t.kind === "steps" ? `Xoá ${t.ids.length} bước đã chọn?` : "Xoá video này?";

  const confirmBody = (t: DeleteTarget) => {
    if (t.kind === "video") {
      return (
        <>
          <p>
            Video <strong>{t.videoId}</strong>: {t.steps ? <strong>{t.steps.total} bước</strong> : "mọi bước"} của video
            (kể cả bước đang bị bộ lọc ẩn) bị xoá khỏi hàng duyệt, cùng tệp video, keyframe, clip và transcript trên máy chủ.
          </p>
          {t.steps ? (
            t.steps.published > 0 && (
              <p>
                {t.steps.published} bước trong số đó đang có trong đồ thị tri thức: cũng bị gỡ khỏi đồ thị tri thức và kho
                tìm kiếm, trợ lý sẽ không trích dẫn nữa.
              </p>
            )
          ) : (
            <p>Bước đã duyệt của video (nếu có) cũng bị gỡ khỏi đồ thị tri thức và kho tìm kiếm.</p>
          )}
        </>
      );
    }
    const ids = t.kind === "step" ? [t.profile.profile_id] : t.ids;
    const approved = publishedAmong(ids);
    return (
      <>
        {t.kind === "step" ? (
          <p>
            Bước <strong>{t.profile.profile_id}</strong> — “{t.profile.step}” bị xoá khỏi hàng duyệt cùng lịch sử duyệt của nó.
          </p>
        ) : (
          <p>
            {ids.length} bước bị xoá khỏi hàng duyệt cùng lịch sử duyệt: <strong>{ids.join(", ")}</strong>.
          </p>
        )}
        {approved > 0 && (
          <p>
            {t.kind === "step" ? "Bước này" : `${approved} bước trong số đó`} đang có trong đồ thị tri thức (đã duyệt, kể cả
            khi đã sửa sau lúc duyệt): cũng bị gỡ khỏi đồ thị tri thức và kho tìm kiếm, trợ lý sẽ không trích dẫn nữa.
          </p>
        )}
      </>
    );
  };

  const toggleErrorTag = (tag: ErrorTag) => {
    setSelectedErrorTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const ERROR_TAGS: { id: ErrorTag; label: string }[] = [
    { id: "missed_step",       label: "Missed Step" },
    { id: "hallucinated_step", label: "Hallucinated Step" },
    { id: "wrong_order",       label: "Wrong Order" },
    { id: "wrong_object",      label: "Wrong Object" },
    { id: "wrong_action",      label: "Wrong Action" },
    { id: "other",             label: "Other Defect" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      {/* ── Production Line Filter Bar ── */}
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <div className="card-icon ci-red">
              <Filter size={14} />
            </div>
            Line Inspection Filter
          </div>
          <span className="badge badge-red">DENSO PACK01 // ST-04</span>
        </div>
        <div className="filter-bar">
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontFamily: "var(--font-display)", fontSize: "0.78rem", fontWeight: 700, color: "var(--text-secondary)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              Process Line:
            </span>
            <select
              id="filter-process"
              className="form-select"
              style={{ width: 220, fontFamily: "var(--font-mono)", fontSize: "0.82rem" }}
              value={selectedProcess}
              onChange={(e) => setSelectedProcess(e.target.value)}
            >
              {processOptions.map((code) => (
                <option key={code} value={code}>{PROCESS_LABELS[code] ?? code}</option>
              ))}
            </select>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontFamily: "var(--font-display)", fontSize: "0.78rem", fontWeight: 700, color: "var(--text-secondary)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              Status:
            </span>
            <select
              id="filter-status"
              className="form-select"
              style={{ width: 180, fontFamily: "var(--font-mono)", fontSize: "0.82rem" }}
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
            >
              <option value="">All Statuses</option>
              <option value="draft">Draft</option>
              <option value="in_review">In Review</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontFamily: "var(--font-display)", fontSize: "0.78rem", fontWeight: 700, color: "var(--text-secondary)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              Video:
            </span>
            <select
              id="filter-video"
              className="form-select"
              style={{ width: 230, fontFamily: "var(--font-mono)", fontSize: "0.82rem" }}
              value={selectedVideo}
              onChange={(e) => setSelectedVideo(e.target.value)}
            >
              <option value="">Tất cả video</option>
              {videoIds.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
              {selectedVideo && !videoIds.includes(selectedVideo) && <option value={selectedVideo}>{selectedVideo}</option>}
            </select>
            <button
              id="btn-delete-video"
              className="btn btn-danger btn-sm"
              disabled={!selectedVideo || pending !== null}
              onClick={() => askDeleteVideo(selectedVideo)}
              title={selectedVideo ? `Xoá video ${selectedVideo} và mọi bước của nó` : "Chọn một video để xoá"}
            >
              {pending === "delete-video" ? <div className="spinner" /> : <Trash2 size={13} />}
              {pending === "delete-video" ? "Đang xoá…" : "Xoá video này"}
            </button>
          </div>

          <button id="btn-refresh" className="btn btn-ghost btn-sm" onClick={loadProfiles} style={{ marginLeft: "auto" }}>
            <RefreshCw size={13} />
            Refresh Queue
          </button>
        </div>
      </div>

      {/* ── Action Notification Message ── */}
      {actionMsg && (
        <div className={`alert alert-${actionMsg.type === "success" ? "success" : actionMsg.type === "warning" ? "warning" : "error"}`}>
          <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
          <span>{actionMsg.text}</span>
        </div>
      )}

      {/* ── Two-Panel Industrial Layout ── */}
      <div className="review-layout">

        {/* Left Column — Sticky Profile List */}
        <div className="card profile-sidebar-card">
          <div className="card-header">
            <div className="card-title">
              <div className="card-icon ci-cyan">
                <Layers size={14} />
              </div>
              Work Profiles
              <span className="badge badge-cyan" style={{ marginLeft: "0.3rem" }}>{visible.length}</span>
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", color: "var(--text-muted)", letterSpacing: "0.06em" }}>
              QUEUE
            </span>
          </div>

          <div className="profile-bulk-bar">
            <label style={{ display: "flex", alignItems: "center", gap: "0.45rem", cursor: "pointer" }}>
              <input
                id="check-all-profiles"
                type="checkbox"
                className="profile-check"
                checked={allChecked}
                disabled={visible.length === 0 || pending !== null}
                onChange={toggleAll}
              />
              Chọn tất cả
            </label>
            <button
              id="btn-delete-selected"
              className="btn btn-danger btn-sm"
              disabled={checkedVisible.length === 0 || pending !== null}
              onClick={() => setConfirm({ kind: "steps", ids: checkedVisible })}
            >
              {pending === "delete-steps" ? <div className="spinner" /> : <Trash2 size={13} />}
              {pending === "delete-steps" ? "Đang xoá…" : `Xoá các bước đã chọn (${checkedVisible.length})`}
            </button>
          </div>

          <div className="profile-list" style={{ maxHeight: "calc(100vh - 290px)" }}>
            {loading ? (
              <div className="loading-center">
                <div className="spinner" />
                <span>Reading Station DB…</span>
              </div>
            ) : visible.length === 0 ? (
              <div className="empty-state">
                <FileText size={32} />
                <p>No profiles match current filter criteria.</p>
              </div>
            ) : (
              visible.map((p) => {
                const isSel = selectedProfile?.profile_id === p.profile_id;
                return (
                  <div
                    key={p.profile_id}
                    className={`profile-item ${isSel ? "selected" : ""}`}
                    onClick={() => selectProfile(p)}
                  >
                    <input
                      type="checkbox"
                      className="profile-check"
                      aria-label={`Chọn ${p.profile_id} để xoá`}
                      checked={checked.includes(p.profile_id)}
                      disabled={pending !== null}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => toggleChecked(p.profile_id)}
                    />
                    <div className="profile-step-num">{String(p.step_order).padStart(2, "0")}</div>
                    <div className="profile-info">
                      <div className="profile-step-text">{p.step}</div>
                      <div className="profile-meta">
                        {p.profile_id} · {formatTime(p.evidence.t_start)}–{formatTime(p.evidence.t_end)} · v{p.version} ·{" "}
                        <span style={{ color: p.confidence >= 0.9 ? "var(--status-success)" : "var(--status-warning)", fontWeight: 600 }}>
                          {(p.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                    <span className={statusBadge(p.status)}>{p.status.replace("_", " ")}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column — Detail Inspection & Sign-off Console */}
        {selectedProfile ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

            {/* Profile Overview & Telemetry Banner */}
            <div className="card">
              <div className="card-body" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.65rem", marginBottom: "0.45rem", flexWrap: "wrap" }}>
                    <h2 style={{ fontFamily: "var(--font-display)", fontSize: "1.45rem", fontWeight: 700, color: "var(--text-pure)", letterSpacing: "0.02em" }}>
                      {selectedProfile.profile_id}
                    </h2>
                    <span className={statusBadge(selectedProfile.status)}>{selectedProfile.status.replace("_", " ")}</span>
                    <span className="mono-tag">v{selectedProfile.version}.0</span>
                  </div>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.74rem", color: "var(--text-muted)", letterSpacing: "0.03em" }}>
                    PROCESS: <strong style={{ color: "var(--text-pure)" }}>{selectedProfile.process_id}</strong>
                    {" · "} PIPELINE: <strong style={{ color: "var(--accent-cyan)" }}>{selectedProfile.generated_by.toUpperCase()}</strong>
                    {" · "} CLASSIFICATION: <strong style={{ color: "var(--text-secondary)" }}>{selectedProfile.data_classification}</strong>
                  </p>
                </div>

                <div style={{ textAlign: "right", flexShrink: 0 }}>
                  <div style={{ fontFamily: "var(--font-display)", fontSize: "0.68rem", fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: "0.2rem" }}>
                    Vision AI Confidence
                  </div>
                  <div style={{ fontFamily: "var(--font-display)", fontSize: "1.45rem", fontWeight: 700, color: selectedProfile.confidence >= 0.9 ? "var(--status-success)" : "var(--status-warning)" }}>
                    {(selectedProfile.confidence * 100).toFixed(1)}%
                  </div>
                  <div className="confidence-wrap" style={{ marginTop: "0.25rem" }}>
                    <div className="confidence-track" style={{ width: 110 }}>
                      <div className="confidence-fill" style={{ width: `${selectedProfile.confidence * 100}%` }} />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Visual Evidence — 3-Frame Machine Vision Viewfinder */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <div className="card-icon ci-cyan">
                    <Video size={14} />
                  </div>
                  Visual Evidence — Machine Vision CCTV
                </div>
                <span className="mono-tag">
                  FEED: {selectedProfile.evidence.video_id || "CAM-01-PACK"} · {selectedProfile.evidence.t_start?.toFixed(1)}s – {selectedProfile.evidence.t_end?.toFixed(1)}s
                </span>
              </div>

              {(() => {
                const evidence = selectedProfile.evidence;
                const keyframes = pickKeyframes(evidence.keyframes);
                const videoSegments = evidence.video_id ? segments[evidence.video_id] : undefined;
                const clipSegment = videoSegments?.find((s) => s.segment_id === evidence.segment_ids?.[0]);
                const clipUrl = mediaUrl(clipSegment?.clip_path);
                // The clip covers its whole segment; play only the step: from t_start, pause at t_end.
                const stepStart = clipSegment ? Math.max(0, (evidence.t_start ?? clipSegment.t_start) - clipSegment.t_start) : 0;
                const stepEnd = clipSegment ? (evidence.t_end ?? clipSegment.t_end) - clipSegment.t_start : 0;
                return (
                  <>
                    <div className="cctv-grid">
                      {keyframes.length > 0
                        ? keyframes.map((path, i) => (
                            <div key={path} className="cctv-frame has-image">
                              <img src={mediaUrl(path) ?? undefined} alt={`Keyframe ${i + 1}`} loading="lazy" />
                              <span className="cctv-label">KEYFRAME {i + 1}</span>
                            </div>
                          ))
                        : ["ĐẦU", "GIỮA", "CUỐI"].map((label) => (
                            <div key={label} className="cctv-frame">
                              <div className="cctv-crosshair" />
                              <span className="cctv-label">{label} // CHƯA CÓ KEYFRAME</span>
                            </div>
                          ))}
                    </div>
                    {clipUrl ? (
                      <video
                        key={selectedProfile.profile_id}
                        className="evidence-clip"
                        src={clipUrl}
                        controls
                        playsInline
                        preload="metadata"
                        onLoadedMetadata={(e) => { e.currentTarget.currentTime = stepStart; }}
                        onPlay={(e) => { if (e.currentTarget.currentTime >= stepEnd) e.currentTarget.currentTime = stepStart; }}
                        onTimeUpdate={(e) => { if (e.currentTarget.currentTime >= stepEnd) e.currentTarget.pause(); }}
                      />
                    ) : (
                      <p style={{ padding: "0 1.35rem 1.1rem", fontSize: "0.9rem", color: "var(--text-muted)" }}>
                        {evidence.video_id
                          ? "Chưa có clip cho bước này (video chưa được cắt đoạn qua trang Tải dữ liệu)."
                          : "Bước này không gắn với video."}
                      </p>
                    )}
                  </>
                );
              })()}
            </div>

            {/* Knowledge Field Editor */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <div className="card-icon ci-red">
                    <Wrench size={14} />
                  </div>
                  Operational Know-How Editor
                </div>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", color: "var(--text-muted)" }}>
                  STANDARD SPEC 08
                </span>
              </div>

              <div className="card-body">
                <div className="data-grid data-grid-2">
                  <div className="form-group" style={{ gridColumn: "1 / -1" }}>
                    <label className="form-label">
                      <Pencil size={12} color="var(--denso-red)" />
                      Step Action Name (Must start with active verb)
                    </label>
                    <input
                      id="input-step"
                      className="form-input"
                      style={{ fontWeight: 600, fontSize: "0.95rem" }}
                      value={step}
                      onChange={(e) => setStep(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      <Eye size={12} color="var(--accent-cyan)" />
                      Hand Action Observed
                    </label>
                    <textarea
                      id="input-hand-action"
                      className="form-textarea"
                      value={handAction}
                      onChange={(e) => setHandAction(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      <AlertTriangle size={12} color="var(--status-warning)" />
                      Key Point / Critical Observation
                    </label>
                    <textarea
                      id="input-key-point"
                      className="form-textarea"
                      value={keyPoint}
                      onChange={(e) => setKeyPoint(e.target.value)}
                    />
                  </div>

                  <div className="form-group" style={{ gridColumn: "1 / -1" }}>
                    <label className="form-label">
                      <MessageSquareQuote size={12} color="var(--accent-cyan)" />
                      Lời chuyên gia về bước này (transcript)
                    </label>
                    {selectedProfile.evidence.transcript_excerpt ? (
                      <blockquote
                        id="transcript-excerpt"
                        style={{ margin: 0, padding: "0.6rem 0.9rem", borderLeft: "3px solid var(--accent-cyan)", background: "var(--bg-surface)", fontStyle: "italic" }}
                      >
                        “{selectedProfile.evidence.transcript_excerpt}”
                      </blockquote>
                    ) : null}
                    {selectedProfile.evidence.transcript_excerpt && selectedProfile.reason && selectedProfile.reason_source === "expert_verbal" && selectedProfile.status === "in_review" ? (
                      <div id="reason-proposed" className="alert alert-info" style={{ margin: "0.5rem 0 0" }}>
                        <span>
                          Lý do bên dưới do AI trích từ đúng lời chuyên gia ở trên (propose-reasons). Kiểm tra lại, sửa nếu cần, rồi Duyệt.
                        </span>
                      </div>
                    ) : null}
                    {selectedProfile.evidence.transcript_excerpt ? null : (
                      <div id="transcript-missing" className="alert alert-info" style={{ margin: 0 }}>
                        <span>
                          Không có lời chuyên gia nào nói về bước này (video không có tiếng, hoặc lúc làm bước này chuyên gia không nói), nên AI không đề xuất lý do.
                          Nếu chuyên gia biết vì sao làm như vậy, nhập vào ô lý do bên dưới và chọn nguồn EXPERT_INTERVIEW.
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      Expert Know-How Reason
                      {reason.trim().length > 0 && <span style={{ color: "var(--status-danger)", marginLeft: "0.35rem" }}>* AC-08</span>}
                    </label>
                    <textarea
                      id="input-reason"
                      className="form-textarea"
                      placeholder="Explicit rationale from expert operator…"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      Reason Source Classification
                      {hasReasonWithoutSource && <span style={{ color: "var(--status-danger)", marginLeft: "0.35rem" }}>* MANDATORY</span>}
                    </label>
                    <select
                      id="select-reason-source"
                      className="form-select"
                      value={reasonSource}
                      onChange={(e) => setReasonSource(e.target.value as ReasonSource)}
                      style={{ borderColor: hasReasonWithoutSource ? "var(--status-danger)" : undefined, fontFamily: "var(--font-mono)" }}
                    >
                      <option value="">— SELECT SOURCE —</option>
                      <option value="expert_verbal">EXPERT_VERBAL (Recorded during run)</option>
                      <option value="expert_interview">EXPERT_INTERVIEW (Structured post-shift Q&amp;A)</option>
                    </select>
                  </div>

                  <div className="form-group" style={{ gridColumn: "1 / -1" }}>
                    <label className="form-label">
                      <CheckCircle size={12} color="var(--status-success)" />
                      Pass Criteria &amp; Acceptance Standard
                    </label>
                    <input
                      id="input-pass-criteria"
                      className="form-input"
                      value={passCriteria}
                      onChange={(e) => setPassCriteria(e.target.value)}
                    />
                  </div>
                </div>

                {hasReasonWithoutSource && (
                  <div className="alert alert-warning" style={{ marginTop: "1rem" }}>
                    <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
                    <span><strong>AC-08 RULE:</strong> A valid Reason Source is mandatory when Reason is filled. Approval is locked until selected.</span>
                  </div>
                )}
              </div>
            </div>

            {/* QA Verification & Station Sign-Off Console */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <div className="card-icon ci-green">
                    <ShieldCheck size={14} />
                  </div>
                  QA Verification &amp; Station Sign-Off
                </div>
                <span className="badge badge-green">STATION SIGN-OFF</span>
              </div>

              <div className="card-body">
                <div className="data-grid data-grid-2" style={{ marginBottom: "1.1rem" }}>
                  <div className="form-group">
                    <label className="form-label">
                      <UserCheck size={12} />
                      Lead Reviewer / QA Engineer
                    </label>
                    <input
                      id="input-reviewer"
                      className="form-input"
                      value={reviewer}
                      onChange={(e) => setReviewer(e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">
                      Review Comment / Audit Notes
                    </label>
                    <input
                      id="input-review-comment"
                      className="form-input"
                      placeholder="Engineer notes or rejection cause…"
                      value={reviewComment}
                      onChange={(e) => setReviewComment(e.target.value)}
                    />
                  </div>
                </div>

                <div style={{ marginBottom: "1.25rem" }}>
                  <div className="section-label">
                    <span className="section-label-text">Defect &amp; Error Tagging Matrix</span>
                  </div>
                  <div className="chip-list">
                    {ERROR_TAGS.map(({ id, label }) => {
                      const sel = selectedErrorTags.includes(id);
                      return (
                        <button
                          key={id}
                          type="button"
                          onClick={() => toggleErrorTag(id)}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.4rem",
                            padding: "0.38rem 0.85rem",
                            borderRadius: "var(--r-xs)",
                            border: sel ? "1px solid var(--status-danger)" : "1px solid var(--border-tech)",
                            background: sel ? "var(--status-danger-bg)" : "var(--bg-surface)",
                            color: sel ? "var(--status-danger-text)" : "var(--text-secondary)",
                            fontFamily: "var(--font-display)",
                            fontSize: "0.78rem",
                            fontWeight: 700,
                            cursor: "pointer",
                            letterSpacing: "0.04em",
                            textTransform: "uppercase",
                            transition: "all 120ms ease",
                          }}
                        >
                          {sel ? "✓" : "+"} {label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 1fr 1fr", gap: "0.85rem" }}>
                  <button id="btn-approve" className="btn btn-success btn-lg" onClick={handleApprove} disabled={hasReasonWithoutSource || pending !== null}>
                    {pending === "approve" ? <div className="spinner" /> : <CheckCircle size={16} />}
                    {pending === "approve" ? "Đang duyệt…" : <>Approve &amp; Verify</>}
                  </button>
                  <button id="btn-reject" className="btn btn-danger btn-lg" onClick={handleReject} disabled={pending !== null}>
                    {pending === "reject" ? <div className="spinner" /> : <XCircle size={16} />}
                    {pending === "reject" ? "Đang từ chối…" : "Reject Step"}
                  </button>
                  <button id="btn-save" className="btn btn-primary btn-lg" onClick={handleSavePatch} disabled={pending !== null}>
                    {pending === "save" ? <div className="spinner" /> : <Save size={16} />}
                    {pending === "save" ? "Đang lưu…" : `Save Draft v${selectedProfile.version + 1}`}
                  </button>
                  <button
                    id="btn-delete-step"
                    className="btn btn-danger btn-lg"
                    onClick={() => setConfirm({ kind: "step", profile: selectedProfile })}
                    disabled={pending !== null}
                  >
                    {pending === "delete-step" ? <div className="spinner" /> : <Trash2 size={16} />}
                    {pending === "delete-step" ? "Đang xoá…" : "Xoá bước"}
                  </button>
                </div>
              </div>
            </div>

          </div>
        ) : (
          <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 450 }}>
            <div className="empty-state">
              <Shield size={44} />
              <p>Select an operational profile from the queue to start the verification audit.</p>
            </div>
          </div>
        )}
      </div>

      {confirm && (
        <ConfirmDialog title={confirmTitle(confirm)} onConfirm={() => handleDelete(confirm)} onCancel={() => setConfirm(null)}>
          {confirmBody(confirm)}
        </ConfirmDialog>
      )}
    </div>
  );
}
