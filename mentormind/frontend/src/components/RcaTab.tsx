import React, { useEffect, useState } from "react";
import { api } from "../api";
import { LotRecord, RcaReport } from "../types";
import {
  Search,
  CheckCircle2,
  AlertOctagon,
  ArrowRight,
  ShieldCheck,
  FileSpreadsheet,
  Cpu,
  Info,
  Zap,
  AlertTriangle,
  TrendingDown,
  Layers,
  Sparkles,
} from "lucide-react";

// ── Likelihood badge ──────────────────────────────────────────
function LikelihoodBadge({ l }: { l: string }) {
  if (l === "high")   return <span className="badge badge-rejected">HIGH LIKELIHOOD</span>;
  if (l === "medium") return <span className="badge badge-review">MEDIUM</span>;
  return                     <span className="badge badge-muted">LOW</span>;
}

export function RcaTab() {
  const [lots,          setLots]          = useState<LotRecord[]>([]);
  const [selectedLotId, setSelectedLotId] = useState<string>("");
  const [customSymptom, setCustomSymptom] = useState<string>("");
  const [loading,       setLoading]       = useState(false);
  const [report,        setReport]        = useState<RcaReport | null>(null);
  const [errorMsg,      setErrorMsg]      = useState<string | null>(null);

  useEffect(() => {
    api
      .getSigmaLots()
      .then((data) => {
        setLots(data);
        // Preselect the first lot with a defect: that is what an RCA starts from.
        const flagged = data.find((lot) => lot.status === "NG") ?? data[0];
        if (flagged) setSelectedLotId(flagged.lot_id);
      })
      .catch((err) => console.error(err));
  }, []);

  const handleInvestigate = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.investigateRca(selectedLotId || undefined, customSymptom || undefined);
      setReport(res);
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      {/* ── Sigma Integration Control Panel ── */}
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <div className="card-icon ci-danger">
              <AlertOctagon size={14} color="var(--danger)" />
            </div>
            Root Cause Analysis — Sigma MES 5-Why Engine
          </div>
          <span className="badge badge-red">DEFECT TRACEABILITY</span>
        </div>

        <div className="card-body">
          <div className="data-grid data-grid-2" style={{ marginBottom: "1.1rem" }}>
            <div className="form-group">
              <label className="form-label">
                <FileSpreadsheet size={12} color="var(--cyan)" />
                Select Defective Production Lot (MES Feed)
              </label>
              <select
                id="select-lot"
                className="form-select"
                style={{ fontFamily: "var(--font-mono)", fontSize: "0.82rem" }}
                value={selectedLotId}
                onChange={(e) => setSelectedLotId(e.target.value)}
              >
                {/* Spec 08 §3 page 3: a symptom alone, without a lot. */}
                <option value="">— Không chọn lot (chỉ dùng triệu chứng) —</option>
                {lots.map((lot) => (
                  <option key={lot.lot_id} value={lot.lot_id}>
                    {lot.lot_id} · {lot.part_number} · {lot.produced_at} · {lot.status === "NG" ? lot.defect_type : "OK"}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">
                <Cpu size={12} color="var(--blue)" />
                Mô tả triệu chứng (dùng khi không chọn lot)
              </label>
              <input
                id="input-custom-symptom"
                className="form-input"
                style={{ fontFamily: "var(--font-body)" }}
                placeholder="e.g. Carton bottom staple misalignment > 3mm at ST-04…"
                value={customSymptom}
                onChange={(e) => setCustomSymptom(e.target.value)}
              />
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              id="btn-investigate"
              className="btn btn-primary btn-lg"
              onClick={handleInvestigate}
              disabled={loading || (!selectedLotId && !customSymptom.trim())}
              style={{ minWidth: 220 }}
            >
              {loading ? <div className="spinner" /> : <Search size={16} />}
              {loading ? "Running 5-Why Analysis…" : "Investigate Root Cause"}
            </button>
          </div>
        </div>
      </div>

      {/* ── Error Notification ── */}
      {errorMsg && (
        <div className="alert alert-error">
          <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 2 }} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* ── Loading State ── */}
      {loading && (
        <div className="card">
          <div className="card-body">
            <div className="loading-center" style={{ padding: "2.5rem 1rem" }}>
              <div className="spinner spinner-lg" />
              <span style={{ fontSize: "0.95rem", color: "var(--text-secondary)" }}>
                Running cross-reference analysis against Knowledge Graph &amp; MES logs…
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ── RCA Report ── */}
      {!loading && report && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

          {/* Report Header Banner */}
          <div className="card" style={{ background: "var(--status-danger-bg)", borderColor: "var(--status-danger-border)" }}>
            <div className="card-body">
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.68rem", fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.08em", marginBottom: "0.35rem", textTransform: "uppercase" }}>
                    DEFECT TRACEABILITY REPORT
                  </div>
                  <h2 style={{ fontFamily: "var(--font-display)", fontSize: "1.45rem", fontWeight: 800, color: "var(--text-pure)", marginBottom: "0.45rem" }}>
                    {report.lot_id ? `LOT: ${report.lot_id}` : "Custom Symptom Incident"}
                  </h2>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--danger)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                      Symptom:
                    </span>
                    <span style={{ fontSize: "0.9rem", color: "var(--text-main)", fontWeight: 500 }}>
                      {report.symptom}
                    </span>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "0.65rem", flexWrap: "wrap" }}>
                  <span className="badge badge-rejected" style={{ padding: "0.35rem 0.75rem", fontSize: "0.72rem" }}>
                    <TrendingDown size={11} /> DEFECT DETECTED
                  </span>
                  <span className="badge badge-cyan" style={{ padding: "0.35rem 0.75rem", fontSize: "0.72rem" }}>
                    <Zap size={11} /> {report.hypotheses.length} HYPOTHESES
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* TWO-COLUMN PRECISION DASHBOARD GRID */}
          <div className="rca-grid">

            {/* Left Column: 5-Why Causal Chain */}
            <div className="rca-col-main">
              {report.five_whys.length > 0 && (
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">
                      <div className="card-icon ci-cyan">
                        <ArrowRight size={14} color="var(--cyan)" />
                      </div>
                      5-Why Causal Chain
                    </div>
                    <span className="badge badge-cyan">{report.five_whys.length} STEPS</span>
                  </div>

                  <div className="card-body">
                    <div className="why-chain">
                      {report.five_whys.map((w) => (
                        <div key={w.order} className="why-step">
                          <div className="why-node">{w.order < 10 ? `0${w.order}` : w.order}</div>
                          <div className="why-content">
                            <div className="why-step-header">
                              <span className="why-step-badge">
                                <Zap size={12} color="var(--accent-cyan)" />
                                WHY #{w.order}
                              </span>
                              {w.verified && (
                                <span className="badge badge-green">
                                  <CheckCircle2 size={11} /> VERIFIED
                                </span>
                              )}
                            </div>

                            <div className="why-q-block">
                              <span className="why-q-tag">Q</span>
                              <span className="why-q-text">{w.question}</span>
                            </div>

                            <div className="why-a-block">
                              <span className="why-a-tag">A</span>
                              <span className="why-a-text">{w.answer}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Right Column: Hypotheses, Countermeasures, Related Lots */}
            <div className="rca-col-side" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

              {/* Hypotheses */}
              {report.hypotheses.length > 0 && (
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">
                      <div className="card-icon ci-danger">
                        <Zap size={14} color="var(--danger)" />
                      </div>
                      Failure Hypotheses
                    </div>
                    <span className="badge badge-muted">{report.hypotheses.length} IDENTIFIED</span>
                  </div>

                  <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    {report.hypotheses.map((h, idx) => (
                      <div key={idx} className="hypothesis-card">
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", marginBottom: "0.45rem" }}>
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.74rem", fontWeight: 700, color: "var(--text-muted)" }}>
                            H{idx + 1}
                          </span>
                          <LikelihoodBadge l={h.likelihood} />
                        </div>
                        <p style={{ fontSize: "0.86rem", color: "var(--text-main)", lineHeight: 1.55, margin: "0 0 0.5rem 0" }}>
                          {h.hypothesis}
                        </p>
                        {h.evidence_refs.length > 0 && (
                          <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                            {h.evidence_refs.map((ref, ri) => (
                              <span key={ri} className="mono-tag" style={{ fontSize: "0.65rem" }}>{ref}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Preventive Actions & Countermeasures */}
              {report.preventive_actions.length > 0 && (
                <div className="card" style={{ borderColor: "rgba(16,185,129,0.25)" }}>
                  <div className="card-header">
                    <div className="card-title">
                      <div className="card-icon ci-green">
                        <ShieldCheck size={14} color="var(--success)" />
                      </div>
                      Preventive Actions (Kaizen)
                    </div>
                    <span className="badge badge-green">COUNTERMEASURES</span>
                  </div>

                  <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                    {report.preventive_actions.map((action, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: "0.75rem",
                          padding: "0.75rem 0.95rem",
                          background: "var(--status-success-bg)",
                          border: "1px solid var(--status-success-border)",
                          borderRadius: "10px",
                        }}
                      >
                        <div
                          style={{
                            width: 22,
                            height: 22,
                            borderRadius: 11,
                            background: "var(--success)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            flexShrink: 0,
                            marginTop: 1,
                          }}
                        >
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", fontWeight: 700, color: "#fff" }}>
                            {idx + 1}
                          </span>
                        </div>
                        <span style={{ fontSize: "0.85rem", color: "var(--text-main)", lineHeight: 1.55 }}>
                          {action}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Related Lots Pattern Match */}
              {report.related_lots.length > 0 && (
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">
                      <div className="card-icon ci-warning">
                        <Layers size={14} color="var(--warning)" />
                      </div>
                      Related Lots (Pattern Match)
                    </div>
                  </div>
                  <div className="card-body">
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem" }}>
                      {report.related_lots.map((lot, idx) => (
                        <span key={idx} className="mono-tag" style={{ fontSize: "0.75rem" }}>
                          {lot}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Disclaimer */}
              <div className="alert alert-info" style={{ margin: 0 }}>
                <Info size={15} style={{ flexShrink: 0, marginTop: 2 }} />
                <span style={{ fontSize: "0.8rem", lineHeight: 1.5 }}>{report.disclaimer}</span>
              </div>

            </div>
          </div>

        </div>
      )}

      {/* ── Empty State ── */}
      {!loading && !report && !errorMsg && (
        <div className="card">
          <div className="card-body">
            <div className="empty-state" style={{ padding: "3rem 1.5rem" }}>
              <AlertOctagon size={42} style={{ color: "var(--text-muted)", opacity: 0.5, marginBottom: "0.75rem" }} />
              <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", maxWidth: 460 }}>
                Select a Sigma defect lot or enter a custom symptom above, then click <strong>Investigate Root Cause</strong> to run the automated 5-Why analysis.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
