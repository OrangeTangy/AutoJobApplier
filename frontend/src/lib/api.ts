import axios, { AxiosError, AxiosInstance } from "axios";
import { Application, Job, PaginatedJobs, Resume, TokenResponse, User, UserProfile } from "@/types";

// Default to same-origin ("") so the bundled desktop app talks to its
// embedded FastAPI server. Override at build time for split-origin deploys
// via NEXT_PUBLIC_API_URL.
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const API_PREFIX = "/api/v1";

function createClient(): AxiosInstance {
  const client = axios.create({
    baseURL: BASE_URL + API_PREFIX,
    headers: { "Content-Type": "application/json" },
    timeout: 30000,
  });

  // Attach stored access token to every request
  client.interceptors.request.use((config) => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("access_token");
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  });

  // Auto-refresh on 401
  client.interceptors.response.use(
    (res) => res,
    async (error: AxiosError) => {
      if (error.response?.status === 401 && typeof window !== "undefined") {
        const refresh = localStorage.getItem("refresh_token");
        if (refresh) {
          try {
            const res = await axios.post(`${BASE_URL}${API_PREFIX}/auth/refresh`, {
              refresh_token: refresh,
            });
            const tokens: TokenResponse = res.data;
            localStorage.setItem("access_token", tokens.access_token);
            localStorage.setItem("refresh_token", tokens.refresh_token);
            // Retry original request
            if (error.config) {
              error.config.headers.Authorization = `Bearer ${tokens.access_token}`;
              return client.request(error.config);
            }
          } catch {
            localStorage.clear();
            window.location.href = "/login";
          }
        }
      }
      return Promise.reject(error);
    }
  );

  return client;
}

export const api = createClient();
export const apiClient = api;

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  register: (email: string, password: string, full_name: string) =>
    api.post<User>("/auth/register", { email, password, full_name }),
  login: (email: string, password: string) =>
    api.post<TokenResponse>("/auth/login", { email, password }),
  me: () => api.get<User>("/auth/me"),
  logout: () => api.post("/auth/logout"),
};

// ── Profile ───────────────────────────────────────────────────────────────────
export const profileApi = {
  get: () => api.get<UserProfile>("/profile"),
  update: (data: Partial<UserProfile>) => api.put<UserProfile>("/profile", data),
};

// ── Jobs ──────────────────────────────────────────────────────────────────────
export const jobsApi = {
  ingest: (url: string) => api.post<Job>("/jobs/ingest", { url }),
  list: (params?: { status?: string; company?: string; min_fit_score?: number; page?: number; page_size?: number }) =>
    api.get<PaginatedJobs>("/jobs", { params }),
  get: (id: string) => api.get<Job>(`/jobs/${id}`),
  delete: (id: string) => api.delete(`/jobs/${id}`),
};

// ── Resumes ───────────────────────────────────────────────────────────────────
export const resumesApi = {
  upload: (name: string, latex_source: string, is_base = false) =>
    api.post<Resume>("/resumes", { name, latex_source, is_base }),
  list: () => api.get<Resume[]>("/resumes"),
  get: (id: string) => api.get<Resume>(`/resumes/${id}`),
  getLatex: (id: string) => api.get<{ latex_source: string }>(`/resumes/${id}/latex`),
  tailor: (job_id: string, base_resume_id: string) =>
    api.post<Resume>("/resumes/tailor", { job_id, base_resume_id }),
};

// ── Applications ──────────────────────────────────────────────────────────────
export const applicationsApi = {
  createDraft: (job_id: string) => api.post<Application>(`/applications/${job_id}/draft`),
  list: (status?: string) => api.get<Application[]>("/applications", { params: { status_filter: status } }),
  get: (id: string) => api.get<Application>(`/applications/${id}`),
  editAnswer: (app_id: string, answer_id: string, final_answer: string) =>
    api.patch(`/applications/${app_id}/answers/${answer_id}`, { final_answer }),
  approve: (id: string, notes?: string) =>
    api.post<Application>(`/applications/${id}/approve`, { notes }),
  reject: (id: string, reason?: string) =>
    api.post<Application>(`/applications/${id}/reject`, { reason }),
  submit: (id: string) => api.post<Application>(`/applications/${id}/submit`),
  updateOutcome: (id: string, outcome: string, notes?: string) =>
    api.patch<Application>(`/applications/${id}/outcome`, { outcome, notes }),
};
