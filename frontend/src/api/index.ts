/** Typed wrappers for every backend endpoint. Types are intentionally loose (prototype). */
import { api, streamPost } from "./client";

export type Dict = Record<string, any>;

export interface Concept {
  concept_id: string;
  name: string;
  description: string;
  score: number;
  previous: number;
  delta: number;
  trend: "improving" | "stable" | "needs_attention" | "new";
  band: "strong" | "developing" | "weak";
  attempts: number;
  confidence: number;
  last_result: string | null;
  importance: number;
  source_pages: number[];
  source_material_id: string | null;
}

export interface Material {
  id: string;
  title: string;
  original_name: string;
  status: "queued" | "processing" | "ready" | "failed";
  stage: string | null;
  error_message: string | null;
  page_count: number;
  chunk_count: number;
  summary: string | null;
  size_bytes: number;
  created_at: string;
  job: Dict | null;
}

export interface Citation {
  label: string;
  material_title: string;
  page: number;
  page_end: number;
  snippet: string;
  score: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  tool_calls: Dict[];
  grounded: boolean | null;
  created_at: string;
  pending?: boolean;
}

export interface Question {
  id: string;
  ordinal: number;
  kind: "mcq" | "open";
  difficulty: "easy" | "medium" | "hard";
  prompt: string;
  options: string[];
  concept_name: string | null;
  concept_id: string | null;
  source_pages: number[];
  source_material: string | null;
}

// home / analytics
export const getHome = () => api.get<Dict>("/home");
export const getGlobalAnalytics = () => api.get<Dict>("/analytics");

// global learning context (user level, applies across every project)
export const getGlobalContext = () => api.get<Dict>("/context");
export const addGlobalNote = (body: { kind: string; content: string }) => api.post<Dict>("/context/notes", body);
export const deleteGlobalNote = (noteId: string) => api.del(`/context/notes/${noteId}`);

// spaces
export const listSpaces = () => api.get<Dict[]>("/spaces");
export const createSpace = (body: Dict) => api.post<Dict>("/spaces", body);
export const getSpace = (id: string) => api.get<Dict>(`/spaces/${id}`);
export const deleteSpace = (id: string) => api.del(`/spaces/${id}`);

// projects
export const createProject = (body: Dict) => api.post<Dict>("/projects", body);
export const getProject = (id: string) => api.get<Dict>(`/projects/${id}`);
export const updateProject = (id: string, body: Dict) => api.patch<Dict>(`/projects/${id}`, body);
export const deleteProject = (id: string) => api.del(`/projects/${id}`);
export const getProjectAnalytics = (id: string) => api.get<Dict>(`/projects/${id}/analytics`);
export const getGrowth = (id: string) => api.get<Dict>(`/projects/${id}/growth`);
export const getContext = (id: string) => api.get<Dict>(`/projects/${id}/context`);
export const addNote = (id: string, body: { kind: string; content: string }) => api.post<Dict>(`/projects/${id}/context/notes`, body);
export const deleteNote = (id: string, noteId: string) => api.del(`/projects/${id}/context/notes/${noteId}`);
export const listRecommendations = (id: string) => api.get<Dict[]>(`/projects/${id}/recommendations`);
export const generateRecommendation = (id: string) => api.post<Dict>(`/projects/${id}/recommendations/generate`);
export const updateRecommendation = (id: string, recId: string, status: "done" | "dismissed") => api.patch<Dict>(`/projects/${id}/recommendations/${recId}`, { status });

// materials
export const listMaterials = (id: string) => api.get<Material[]>(`/projects/${id}/materials`);
export const uploadMaterial = (id: string, file: File, title?: string) => {
  const form = new FormData();
  form.append("file", file);
  if (title) form.append("title", title);
  return api.upload<Material>(`/projects/${id}/materials`, form);
};
export const retryMaterial = (id: string, mid: string) => api.post<Material>(`/projects/${id}/materials/${mid}/retry`);
export const deleteMaterial = (id: string, mid: string) => api.del(`/projects/${id}/materials/${mid}`);

// tutor
export const listConversations = (id: string) => api.get<Dict[]>(`/projects/${id}/tutor/conversations`);
export const getConversation = (id: string, cid: string) => api.get<{ conversation: Dict; messages: Message[] }>(`/projects/${id}/tutor/conversations/${cid}`);
export const askTutor = (id: string, body: { message: string; conversation_id?: string | null }, onEvent: (e: string, d: any) => void, signal?: AbortSignal) =>
  streamPost(`/projects/${id}/tutor/ask`, body, onEvent, signal);

// quiz
export const listQuizSessions = (id: string) => api.get<Dict[]>(`/projects/${id}/quiz/sessions`);
export const startQuiz = (id: string, body: Dict) => api.post<{ session: Dict; question: Question | null }>(`/projects/${id}/quiz/sessions`, body);
export const getQuizSession = (id: string, sid: string) => api.get<Dict>(`/projects/${id}/quiz/sessions/${sid}`);
export const answerQuiz = (id: string, sid: string, body: { question_id: string; answer: string }) => api.post<Dict>(`/projects/${id}/quiz/sessions/${sid}/answer`, body);
export const abandonQuiz = (id: string, sid: string) => api.post<Dict>(`/projects/${id}/quiz/sessions/${sid}/abandon`);

// admin
export const admin = {
  overview: () => api.get<Dict>("/admin/overview"),
  users: (search?: string) => api.get<Dict[]>(`/admin/users${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  user: (id: string) => api.get<Dict>(`/admin/users/${id}`),
  spaces: () => api.get<Dict[]>("/admin/spaces"),
  projects: () => api.get<Dict[]>("/admin/projects"),
  activity: (params: Record<string, string>) => api.get<Dict[]>(`/admin/activity?${new URLSearchParams(params).toString()}`),
  learning: () => api.get<Dict>("/admin/learning"),
  ai: (days = 14) => api.get<Dict>(`/admin/ai?days=${days}`),
  aiRequest: (id: string) => api.get<Dict>(`/admin/ai/requests/${id}`),
  prompts: () => api.get<Dict[]>("/admin/prompts"),
  health: () => api.get<Dict>("/admin/health"),
  evals: () => api.get<Dict[]>("/admin/evals"),
  evalDetail: (id: string) => api.get<Dict>(`/admin/evals/${id}`),
  runEval: (project_id: string) => api.post<Dict>("/admin/evals", { project_id }),
};
