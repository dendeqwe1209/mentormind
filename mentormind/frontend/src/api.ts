import {
  AssistantAnswer,
  CutMethod,
  DataClassification,
  DocumentDeleteResult,
  DocumentInfo,
  JobResponse,
  LotRecord,
  ProfileDeleteResult,
  ProfilePatchRequest,
  ProfileStatus,
  QnnRiskResponse,
  QnnStatusResponse,
  RcaReport,
  ReviewRequest,
  Segment,
  VideoAsset,
  VideoDeleteResult,
  WorkProfile,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// An HTTP error from the API; `detail` is FastAPI's `detail` field when the body had one.
export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  let errMsg = `${res.status} ${res.statusText}`;
  let detail: unknown;
  try {
    const errJson = await res.json();
    detail = errJson.detail;
    if (errJson.detail) {
      errMsg = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
    }
  } catch {
    // ignore json parse error
  }
  return new ApiError(res.status, errMsg, detail);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  const res = await fetch(url, { ...options, headers });
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}

// Multipart variant: no Content-Type header, so the browser sets multipart/form-data with its boundary.
async function requestForm<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { method: "POST", body });
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}

export const api = {
  getHealth: () => request<{ status: string; neo4j: string; postgres: string }>("/health"),

  getProfiles: (processId?: string, status?: ProfileStatus | string) => {
    const params = new URLSearchParams();
    if (processId) params.append("process_id", processId);
    if (status) params.append("status", status);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return request<WorkProfile[]>(`/profiles${qs}`);
  },

  getProfileDetails: (profileId: string) => {
    return request<{ profile: WorkProfile; reviews: any[] }>(`/profiles/${profileId}`);
  },

  getQnnStatus: () => request<QnnStatusResponse>("/qnn/status"),

  getQnnRisk: (profileId: string) => {
    return request<QnnRiskResponse>(`/qnn/profiles/${encodeURIComponent(profileId)}/risk`);
  },

  patchProfile: (profileId: string, data: ProfilePatchRequest) => {
    return request<WorkProfile>(`/profiles/${profileId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  reviewProfile: (profileId: string, data: ReviewRequest) => {
    return request<WorkProfile>(`/profiles/${profileId}/review`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  deleteProfile: (profileId: string) => {
    return request<ProfileDeleteResult>(`/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
  },

  deleteProfiles: (profileIds: string[]) => {
    return request<ProfileDeleteResult>("/profiles/delete", {
      method: "POST",
      body: JSON.stringify({ profile_ids: profileIds }),
    });
  },

  getSigmaLots: (processId?: string) => {
    const qs = processId ? `?process_id=${processId}` : "";
    return request<LotRecord[]>(`/sigma/lots${qs}`);
  },

  askAssistant: (processId: string, question: string) => {
    return request<AssistantAnswer>("/assistant/ask", {
      method: "POST",
      body: JSON.stringify({ process_id: processId, question }),
    });
  },

  investigateRca: (lotId?: string, symptom?: string) => {
    return request<RcaReport>("/rca/investigate", {
      method: "POST",
      body: JSON.stringify({ lot_id: lotId || undefined, symptom: symptom || undefined }),
    });
  },

  uploadDocuments: (files: File[], classification: DataClassification) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("classification", classification);
    return requestForm<{ job_id: string }>("/ingest/documents", form);
  },

  uploadVideo: async (file: File, processId: string, classification: DataClassification) => {
    // Railway may time out one long multipart request. Upload small chunks instead; the backend
    // assembles them on the persistent volume and only then probes/hash-validates the video.
    const init = await request<{ upload_id: string; chunk_size: number; next_offset: number }>(
      "/videos/uploads/init",
      {
        method: "POST",
        body: JSON.stringify({
          filename: file.name,
          process_id: processId,
          classification,
          size: file.size,
        }),
      },
    );

    let offset = init.next_offset ?? 0;
    while (offset < file.size) {
      const end = Math.min(offset + init.chunk_size, file.size);
      const chunk = file.slice(offset, end);
      const res = await fetch(
        `${BASE_URL}/videos/uploads/${encodeURIComponent(init.upload_id)}/chunk?offset=${offset}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/octet-stream" },
          body: chunk,
        },
      );
      if (!res.ok) throw await toApiError(res);
      const progress = (await res.json()) as { received: number };
      if (progress.received <= offset) {
        throw new Error("Máy chủ không tiến thêm dữ liệu upload; vui lòng thử lại.");
      }
      offset = progress.received;
    }

    return request<VideoAsset>(`/videos/uploads/${encodeURIComponent(init.upload_id)}/finalize`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  processVideo: (videoId: string, method: CutMethod | null) => {
    return request<{ job_id: string }>(`/videos/${encodeURIComponent(videoId)}/process`, {
      method: "POST",
      body: JSON.stringify({ method }),
    });
  },

  getVideoSegments: (videoId: string) => {
    return request<Segment[]>(`/videos/${encodeURIComponent(videoId)}/segments`);
  },

  deleteVideo: (videoId: string) => {
    return request<VideoDeleteResult>(`/videos/${encodeURIComponent(videoId)}`, { method: "DELETE" });
  },

  getDocuments: () => request<DocumentInfo[]>("/documents"),

  deleteDocument: (docId: string) => {
    return request<DocumentDeleteResult>(`/documents/${encodeURIComponent(docId)}`, { method: "DELETE" });
  },

  getJob: <T = unknown>(jobId: string) => {
    return request<JobResponse<T>>(`/jobs/${encodeURIComponent(jobId)}`);
  },

  getMediaUrl: (relpath: string) => {
    if (relpath.startsWith("http://") || relpath.startsWith("https://")) return relpath;
    const clean = relpath.startsWith("/") ? relpath.slice(1) : relpath;
    return `${BASE_URL}/${clean}`;
  },
};

// URL of a file the API serves under GET /media (spec 08 §2): profiles and segments carry paths
// such as "data/work/video/<id>/keyframes/x.jpg"; citations already carry "/media/...".
export function mediaUrl(path?: string | null): string | null {
  if (!path) return null;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  if (path.startsWith("/media/")) return `${BASE_URL}${path}`;
  const normalized = path.replace(/\\/g, "/");
  for (const root of ["data/work/", "data/samples/"]) {
    const at = normalized.indexOf(root);
    if (at >= 0) return `${BASE_URL}/media/${normalized.slice(at + root.length)}`;
  }
  return null;
}
