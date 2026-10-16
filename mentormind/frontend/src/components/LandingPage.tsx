import React, { useState } from "react";
import {
  ArrowRight,
  Play,
  CheckCircle2,
  ShieldCheck,
  Database,
  Cpu,
  Activity,
  Video,
  Sparkles,
  Layers,
  Terminal,
  Zap,
  Factory,
  Check,
  Shield,
  Eye,
  Wrench,
  TrendingDown,
  Sun,
  Moon,
  ChevronRight,
  Radio,
} from "lucide-react";

interface LandingPageProps {
  onLaunchWorkspace: (tab?: "review" | "assistant" | "rca") => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
}

export function LandingPage({ onLaunchWorkspace, theme, onToggleTheme }: LandingPageProps) {
  const [activeWorkflowStep, setActiveWorkflowStep] = useState(0);

  const workflowSteps = [
    {
      num: "01",
      title: "CCTV Camera Ingestion & VLM Parsing",
      desc: "Station cameras capture operator workflows. Vision-Language Models identify discrete steps, tool movements, and safety key-points frame-by-frame.",
      icon: Video,
      color: "var(--accent-cyan)",
      badge: "Vision AI",
    },
    {
      num: "02",
      title: "Human-in-the-Loop QA Verification",
      desc: "Line engineers inspect extracted know-how, flag anomalies, and sign off with role-based audit logs before pushing to production.",
      icon: ShieldCheck,
      color: "var(--status-success)",
      badge: "Quality Gate",
    },
    {
      num: "03",
      title: "Neo4j Knowledge Graph & 5-Why RCA",
      desc: "Verified tacit knowledge synchronizes into a structured graph database. When MES detects defects, automated 5-Why traces causes in seconds.",
      icon: Database,
      color: "var(--denso-red)",
      badge: "Graph-RAG",
    },
  ];

  return (
    <div className="landing-wrapper">
      {/* ── Architectural Engineering Background ── */}
      <div className="engineered-bg" aria-hidden="true" />

      {/* ── Landing Navigation Bar ── */}
      <nav className="landing-nav">
        <div className="landing-nav-inner">
          <div className="header-left">
            <div className="brand-badge">DENSO</div>
            <div className="brand-text">
              <span className="brand-name">MentorMind</span>
              <span className="brand-badge-version">v1.2 // Production</span>
            </div>
          </div>

          <div className="landing-nav-links">
            <a href="#overview" className="landing-nav-link">Overview</a>
            <a href="#metrics" className="landing-nav-link">Impact Metrics</a>
            <a href="#technology" className="landing-nav-link">Core Engine</a>
            <a href="#workflow" className="landing-nav-link">3-Step Loop</a>
          </div>

          <div className="header-right">
            <button
              onClick={onToggleTheme}
              className="theme-toggle-btn"
              title={theme === "light" ? "Switch to Dark Theme" : "Switch to Light Theme"}
            >
              {theme === "light" ? <Sun size={13} className="theme-icon sun" /> : <Moon size={13} className="theme-icon moon" />}
              <span>{theme === "light" ? "Light" : "Dark"}</span>
            </button>

            <button
              id="landing-btn-launch-nav"
              className="btn btn-primary"
              onClick={() => onLaunchWorkspace("review")}
            >
              Launch Workspace
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </nav>

      {/* ── SECTION 1: ASYMMETRIC SPLIT HERO ── */}
      <section id="overview" className="landing-hero">
        <div className="landing-hero-grid">
          {/* Left Column: Core Value Proposition */}
          <div className="hero-content">
            <div className="hero-tag">
              <span className="hero-tag-dot" />
              DENSO INDUSTRY 4.0 // COGNITIVE MANUFACTURING
            </div>

            <h1 className="hero-title">
              Transform Operator Video into <span className="text-gradient-red">Verified Factory Know-How.</span>
            </h1>

            <p className="hero-subtext">
              MentorMind leverages Vision-Language Models to extract tacit assembly know-how from line cameras, validates workflows through human-in-the-loop review, and connects directly to Neo4j Graph &amp; Sigma MES for automated 5-Why root cause resolution.
            </p>

            <div className="hero-actions">
              <button
                id="hero-btn-launch"
                className="btn btn-primary btn-lg"
                onClick={() => onLaunchWorkspace("review")}
              >
                <Play size={16} />
                Launch Live Workspace
              </button>

              <button
                id="hero-btn-copilot"
                className="btn btn-ghost btn-lg"
                onClick={() => onLaunchWorkspace("assistant")}
              >
                <Sparkles size={16} color="var(--accent-cyan)" />
                Explore AI Copilot
              </button>
            </div>

            <div className="hero-trust-strip">
              <div className="trust-item">
                <CheckCircle2 size={14} color="var(--status-success)" />
                <span>Zero Hallucination Constitution</span>
              </div>
              <div className="trust-item">
                <CheckCircle2 size={14} color="var(--status-success)" />
                <span>Sigma MES 5-Why Engine</span>
              </div>
              <div className="trust-item">
                <CheckCircle2 size={14} color="var(--status-success)" />
                <span>Neo4j Graph-RAG Backend</span>
              </div>
            </div>
          </div>

          {/* Right Column: Live Simulated Machine Vision Terminal Mockup */}
          <div className="hero-visual">
            <div className="terminal-card">
              <div className="terminal-header">
                <div className="terminal-dots">
                  <span className="dot red" />
                  <span className="dot yellow" />
                  <span className="dot green" />
                </div>
                <div className="terminal-title">
                  <Terminal size={12} color="var(--accent-cyan)" />
                  DENSO VISION TERMINAL // PACK01-ST04
                </div>
                <span className="badge badge-green">LIVE STREAM</span>
              </div>

              {/* Simulated camera feed */}
              <div className="terminal-screen">
                <div className="simulated-viewfinder">
                  <div className="viewfinder-corner tl" />
                  <div className="viewfinder-corner tr" />
                  <div className="viewfinder-corner bl" />
                  <div className="viewfinder-corner br" />

                  {/* Bounding box simulation */}
                  <div className="simulated-bbox">
                    <div className="bbox-label">
                      <span>OPERATOR HAND // STEP 01</span>
                      <span className="bbox-confidence">98.4%</span>
                    </div>
                  </div>

                  <div className="viewfinder-hud-top">
                    <div className="hud-rec">
                      <span className="rec-pulse" />
                      REC 00:04.2
                    </div>
                    <div className="hud-cam">CAM-01-WIDE</div>
                  </div>

                  <div className="viewfinder-hud-bottom">
                    <span>STATION: PACKAGING_LINE_01</span>
                    <span className="text-cyan">FRAME: 128 / 640</span>
                  </div>
                </div>

                {/* Real-time telemetry feed */}
                <div className="terminal-feed">
                  <div className="feed-row">
                    <span className="feed-key">Action Detected:</span>
                    <span className="feed-val">Align bottom carton flap &amp; fold tab</span>
                  </div>
                  <div className="feed-row">
                    <span className="feed-key">Key Observation:</span>
                    <span className="feed-val text-amber">Keep fingers &gt; 50mm clear of stapler head</span>
                  </div>
                  <div className="feed-row">
                    <span className="feed-key">Knowledge State:</span>
                    <span className="badge badge-approved" style={{ fontSize: "0.62rem", padding: "0.1rem 0.4rem" }}>
                      VERIFIED KNOWLEDGE
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── SECTION 2: TELEMETRY STAT STRIP ── */}
      <section id="metrics" className="landing-stats-section">
        <div className="stats-container">
          <div className="stat-card">
            <div className="stat-num text-red">99.2%</div>
            <div className="stat-label">Extraction Accuracy</div>
            <div className="stat-sub">Precision standard work step detection from line video</div>
          </div>

          <div className="stat-card">
            <div className="stat-num text-cyan">&lt; 2.4s</div>
            <div className="stat-label">5-Why Root Cause Trace</div>
            <div className="stat-sub">Instant causality diagnosis across MES lot defect logs</div>
          </div>

          <div className="stat-card">
            <div className="stat-num text-green">100%</div>
            <div className="stat-label">Anti-Hallucination</div>
            <div className="stat-sub">Constitution Article 4: strictly grounded evidence</div>
          </div>

          <div className="stat-card">
            <div className="stat-num text-purple">14 Stations</div>
            <div className="stat-label">Production Line Ready</div>
            <div className="stat-sub">Tested on DENSO PACK01 &amp; ASSY02 assembly cells</div>
          </div>
        </div>
      </section>

      {/* ── SECTION 3: CORE CAPABILITIES BENTO GRID ── */}
      <section id="technology" className="landing-bento-section">
        <div className="section-header-block">
          <h2 className="section-title">Engineered for Factory Floor Precision</h2>
          <p className="section-subtext">
            Three interconnected pillars forming a complete, self-reinforcing industrial AI architecture.
          </p>
        </div>

        <div className="bento-grid">
          {/* Cell 1: VLM Know-How Extraction (Hero Cell) */}
          <div className="bento-cell bento-hero">
            <div className="bento-tag">
              <Eye size={12} color="var(--denso-red)" />
              VISION-LANGUAGE AI
            </div>
            <h3 className="bento-cell-title">Automated Tacit Know-How Extraction</h3>
            <p className="bento-cell-desc">
              Standard work isn't just about what is done—it's about <em>why</em>. Our multimodal VLM decomposes high-speed video into structured Work Profiles: identifying hand actions, safety cautions, and expert reasons that prevent common defect modes.
            </p>
            <div className="bento-preview-chips">
              <span className="mono-tag">Action Classification</span>
              <span className="mono-tag">Key-Point Extraction</span>
              <span className="mono-tag">Pass/Fail Boundary</span>
            </div>
          </div>

          {/* Cell 2: Neo4j Knowledge Graph Verification */}
          <div className="bento-cell">
            <div className="bento-tag">
              <Database size={12} color="var(--accent-cyan)" />
              GRAPH-RAG TRUTH
            </div>
            <h3 className="bento-cell-title">Neo4j Verification &amp; Audit Gate</h3>
            <p className="bento-cell-desc">
              Extracted profiles remain in review until an authorized QA engineer inspects visual evidence and applies a digital sign-off. Approved profiles sync directly into an interconnected Neo4j knowledge graph.
            </p>
            <div className="bento-status-box">
              <div className="status-item">
                <span className="status-dot online" />
                <span>Graph DB: CONNECTED</span>
              </div>
              <div className="status-item">
                <span className="status-dot online" />
                <span>Vector Embeddings: SYNCED</span>
              </div>
            </div>
          </div>

          {/* Cell 3: Sigma MES 5-Why RCA */}
          <div className="bento-cell">
            <div className="bento-tag">
              <Activity size={12} color="var(--status-danger)" />
              MES INTEGRATION
            </div>
            <h3 className="bento-cell-title">Automated Sigma MES 5-Why RCA</h3>
            <p className="bento-cell-desc">
              When production encounters a misaligned carton flap or defective lot, MentorMind maps the symptom through historical error tags and traverses the causal chain to verify the exact root cause in seconds.
            </p>
            <div className="bento-mini-stepper">
              <div className="mini-step active">W1: Flap Overlap</div>
              <ChevronRight size={14} color="var(--text-muted)" />
              <div className="mini-step active">W2: Gauge Jam</div>
              <ChevronRight size={14} color="var(--text-muted)" />
              <div className="mini-step active">W3: Missing Step</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── SECTION 4: 3-STEP CLOSED LOOP WORKFLOW ── */}
      <section id="workflow" className="landing-workflow-section">
        <div className="section-header-block">
          <h2 className="section-title">The Closed-Loop Know-How Lifecycle</h2>
          <p className="section-subtext">
            From raw camera recording to shop-floor operational co-pilot assistance in three stages.
          </p>
        </div>

        <div className="workflow-grid">
          {workflowSteps.map((step, idx) => {
            const Icon = step.icon;
            return (
              <div
                key={idx}
                className={`workflow-card ${activeWorkflowStep === idx ? "active" : ""}`}
                onClick={() => setActiveWorkflowStep(idx)}
              >
                <div className="workflow-card-top">
                  <span className="workflow-num">{step.num}</span>
                  <div className="workflow-icon-wrap" style={{ color: step.color }}>
                    <Icon size={18} />
                  </div>
                  <span className="badge badge-muted" style={{ marginLeft: "auto" }}>
                    {step.badge}
                  </span>
                </div>
                <h3 className="workflow-card-title">{step.title}</h3>
                <p className="workflow-card-desc">{step.desc}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── SECTION 5: INTERACTIVE LIVE WORKSPACE GATEWAY ── */}
      <section className="landing-interactive-section">
        <div className="interactive-card">
          <div className="interactive-card-inner">
            <div className="interactive-badge">
              <Factory size={14} color="var(--denso-red)" />
              FACTORY READY // LIVE TEST ENVIRONMENT
            </div>

            <h2 className="interactive-title">
              Experience MentorMind on Real Factory Data
            </h2>

            <p className="interactive-desc">
              Access the complete Operator Terminal right now. Inspect packaging profiles, chat with the verified know-how co-pilot, and run 5-Why root cause investigations on simulated MES defect lots.
            </p>

            <div className="interactive-button-grid">
              <button
                className="workspace-quick-btn"
                onClick={() => onLaunchWorkspace("review")}
              >
                <Layers size={18} color="var(--denso-red)" />
                <div className="btn-text-block">
                  <span className="btn-head">01 // Human-in-the-Loop Review</span>
                  <span className="btn-sub">Audit extracted steps &amp; video evidence</span>
                </div>
                <ArrowRight size={16} className="btn-arrow" />
              </button>

              <button
                className="workspace-quick-btn"
                onClick={() => onLaunchWorkspace("assistant")}
              >
                <Sparkles size={18} color="var(--accent-cyan)" />
                <div className="btn-text-block">
                  <span className="btn-head">02 // Verified RAG Copilot</span>
                  <span className="btn-sub">Query operational standards &amp; citations</span>
                </div>
                <ArrowRight size={16} className="btn-arrow" />
              </button>

              <button
                className="workspace-quick-btn"
                onClick={() => onLaunchWorkspace("rca")}
              >
                <Activity size={18} color="var(--status-danger)" />
                <div className="btn-text-block">
                  <span className="btn-head">03 // Sigma 5-Why RCA</span>
                  <span className="btn-sub">Investigate defect lots &amp; countermeasures</span>
                </div>
                <ArrowRight size={16} className="btn-arrow" />
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── SECTION 6: FOOTER ── */}
      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <div className="footer-left">
            <div className="brand-badge">DENSO</div>
            <span className="footer-brand-name">MentorMind Industrial AI</span>
            <span className="footer-hackathon-tag">DENSO Factory Hacks 2026</span>
          </div>

          <div className="footer-center">
            <span>Powered by PyTorch · Neo4j Graph Database · FastAPI · React TypeScript</span>
          </div>

          <div className="footer-right">
            <button
              className="btn btn-primary btn-sm"
              onClick={() => onLaunchWorkspace("review")}
            >
              Enter Terminal
              <ArrowRight size={13} />
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
