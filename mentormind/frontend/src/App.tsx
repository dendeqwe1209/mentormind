import React, { useEffect, useState } from "react";
import { api } from "./api";
import { ReviewProfilesTab } from "./components/ReviewProfilesTab";
import { AssistantTab } from "./components/AssistantTab";
import { RcaTab } from "./components/RcaTab";
import { UploadTab } from "./components/UploadTab";
import { LandingPage } from "./components/LandingPage";
import {
  CheckSquare,
  Bot,
  Activity,
  Database,
  Radio,
  Sun,
  Moon,
  Home,
  Upload,
} from "lucide-react";

export default function App() {
  const [viewMode, setViewMode] = useState<"landing" | "workspace">(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("view") === "workspace" || params.get("tab") || window.location.hash.includes("workspace")) return "workspace";
    return "landing";
  });
  const [activeTab, setActiveTab] = useState<"review" | "assistant" | "rca" | "upload">(() => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get("tab");
    if (tab === "assistant" || tab === "rca" || tab === "review" || tab === "upload") return tab;
    return "review";
  });
  // Set by "Duyệt các bước này" on the upload page: the review page opens on that video's steps,
  // under the process code typed at upload (any code, not only the demo lines).
  const [reviewTarget, setReviewTarget] = useState<{ videoId: string; processId: string } | null>(null);
  const [healthStatus, setHealthStatus] = useState<{ status: string; neo4j: string; postgres: string } | null>(null);
  const [apiError, setApiError] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("mentormind_theme") as "light" | "dark" | null;
    return saved || "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("mentormind_theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  useEffect(() => {
    const checkHealth = () => {
      api
        .getHealth()
        .then((res) => {
          setHealthStatus(res);
          setApiError(false);
        })
        .catch(() => {
          setApiError(true);
        });
    };
    checkHealth();
    const timer = setInterval(checkHealth, 15000);
    return () => clearInterval(timer);
  }, []);

  const isOnline = !apiError;

  const handleLaunchWorkspace = (tab?: "review" | "assistant" | "rca") => {
    if (tab) setActiveTab(tab);
    setViewMode("workspace");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (viewMode === "landing") {
    return (
      <LandingPage
        onLaunchWorkspace={handleLaunchWorkspace}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    );
  }

  return (
    <div className="app-container">
      {/* ── Architectural Engineering Background ── */}
      <div className="engineered-bg" aria-hidden="true" />

      {/* ── Enterprise Header ── */}
      <header className="app-header">
        <div className="header-left">
          <div className="brand-badge" onClick={() => setViewMode("landing")} style={{ cursor: "pointer" }} title="Return to Landing Page">
            DENSO
          </div>
          <div className="brand-text">
            <span className="brand-name" onClick={() => setViewMode("landing")} style={{ cursor: "pointer" }}>
              MentorMind
            </span>
            <span className="brand-badge-version">v1.2 // Production</span>
          </div>
          <span className="brand-tagline">Quality Know-How &amp; RCA Platform</span>
        </div>

        <div className="header-right">
          {/* Button to go back to Landing Page */}
          <button
            id="btn-back-landing"
            className="btn btn-ghost btn-sm"
            onClick={() => setViewMode("landing")}
            title="Return to Landing Page Overview"
          >
            <Home size={13} />
            <span>Overview</span>
          </button>

          {/* Integrated System Health Status */}
          <div className="system-health-strip">
            <div className="health-item" title={isOnline ? "Backend API Operational" : "Backend API Offline"}>
              <span className={`status-dot ${isOnline ? "online" : "offline"}`} />
              <span>API</span>
            </div>
            <div className="health-divider" />
            <div className="health-item" title={`Neo4j Knowledge Graph: ${healthStatus?.neo4j || "ready"}`}>
              <Database size={12} className="health-icon" />
              <span>Graph DB</span>
            </div>
            <div className="health-divider" />
            <div className="health-item" title={`PostgreSQL Vector Store: ${healthStatus?.postgres || "ready"}`}>
              <Radio size={12} className="health-icon" />
              <span>Vector DB</span>
            </div>
          </div>

          {/* Theme Switcher */}
          <button
            id="theme-toggle"
            onClick={toggleTheme}
            className="theme-toggle-btn"
            title={theme === "light" ? "Switch to Dark Mode" : "Switch to Light Mode"}
          >
            {theme === "light" ? (
              <Sun size={13} className="theme-icon sun" />
            ) : (
              <Moon size={13} className="theme-icon moon" />
            )}
            <span>{theme === "light" ? "Light" : "Dark"}</span>
          </button>
        </div>
      </header>

      {/* ── Navigation Tabs ── */}
      <nav className="tabs-nav">
        <div className="tabs-container">
          <button
            id="tab-review"
            className={`tab-btn ${activeTab === "review" ? "active" : ""}`}
            onClick={() => setActiveTab("review")}
          >
            <CheckSquare size={15} />
            <span>Human-in-the-Loop Review</span>
          </button>

          <button
            id="tab-assistant"
            className={`tab-btn ${activeTab === "assistant" ? "active" : ""}`}
            onClick={() => setActiveTab("assistant")}
          >
            <Bot size={15} />
            <span>Know-How Assistant</span>
          </button>

          <button
            id="tab-rca"
            className={`tab-btn ${activeTab === "rca" ? "active" : ""}`}
            onClick={() => setActiveTab("rca")}
          >
            <Activity size={15} />
            <span>Root Cause Analysis (5-Why)</span>
          </button>

          <button
            id="tab-upload"
            className={`tab-btn ${activeTab === "upload" ? "active" : ""}`}
            onClick={() => setActiveTab("upload")}
          >
            <Upload size={15} />
            <span>Tải dữ liệu</span>
          </button>
        </div>
      </nav>

      {/* ── Main Content ── */}
      <main className="main-content">
        {activeTab === "review"    && <ReviewProfilesTab initialVideoId={reviewTarget?.videoId ?? null} initialProcessId={reviewTarget?.processId ?? null} />}
        {activeTab === "assistant" && <AssistantTab />}
        {activeTab === "rca"       && <RcaTab />}
        {activeTab === "upload"    && (
          <UploadTab
            onReviewVideo={(videoId, processId) => {
              setReviewTarget({ videoId, processId });
              setActiveTab("review");
            }}
          />
        )}
      </main>
    </div>
  );
}
