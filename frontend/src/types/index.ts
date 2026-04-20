export interface User {
  id: string;
  email: string;
  is_active: boolean;
  is_admin: boolean;
}

export interface UserProfile {
  id: string;
  user_id: string;
  full_name: string;
  phone?: string;
  location?: string;
  linkedin_url?: string;
  github_url?: string;
  portfolio_url?: string;
  work_authorization: string;
  requires_sponsorship: boolean;
  desired_salary_min?: number;
  desired_salary_max?: number;
  salary_currency: string;
  earliest_start_date?: string;
  willing_to_relocate: boolean;
  target_locations: string[];
  education: EducationEntry[];
  work_history: WorkHistoryEntry[];
  skills: string[];
  certifications: string[];
  custom_qa_defaults: Record<string, string>;
}

export interface EducationEntry {
  institution: string;
  degree: string;
  field: string;
  gpa?: string;
  graduated_at?: string;
  in_progress: boolean;
}

export interface WorkHistoryEntry {
  company: string;
  title: string;
  start_date: string;
  end_date?: string;
  bullets: string[];
}

export interface Job {
  id: string;
  title?: string;
  company?: string;
  location?: string;
  remote_policy?: string;
  description?: string;
  required_skills: string[];
  preferred_skills: string[];
  years_experience_min?: number;
  years_experience_max?: number;
  sponsorship_hint?: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  deadline?: string;
  application_url?: string;
  application_questions: ApplicationQuestion[];
  fit_score?: number;
  fit_rationale?: FitRationale;
  status: JobStatus;
  discovered_at: string;
  raw_url?: string;
}

export type JobStatus =
  | "new"
  | "parsing"
  | "parsed"
  | "scored"
  | "draft"
  | "review"
  | "approved"
  | "submitted"
  | "rejected_by_user"
  | "rejected_by_employer"
  | "error";

export interface ApplicationQuestion {
  question_text: string;
  question_type: string;
  required: boolean;
  options: string[];
}

export interface FitRationale {
  score: number;
  matched_skills: string[];
  missing_required_skills: string[];
  missing_preferred_skills: string[];
  red_flags: string[];
  positive_signals: string[];
  summary: string;
}

export interface Resume {
  id: string;
  name: string;
  is_base: boolean;
  template_name?: string;
  word_count?: number;
  page_count?: number;
  compiled_pdf_path?: string;
  base_resume_id?: string;
  job_id?: string;
  tailoring_diff?: TailoringDiff;
  created_at: string;
  updated_at: string;
}

export interface TailoringDiff {
  edits: BulletEdit[];
  sections_reordered: string[];
  rationale_summary: string;
}

export interface BulletEdit {
  section: string;
  original: string;
  tailored: string;
  rationale: string;
}

export interface Application {
  id: string;
  job_id: string;
  resume_id?: string;
  status: ApplicationStatus;
  approved_at?: string;
  submitted_at?: string;
  outcome?: string;
  user_notes?: string;
  created_at: string;
  updated_at: string;
  answers: QuestionnaireAnswer[];
}

export type ApplicationStatus =
  | "draft"
  | "ready_for_review"
  | "approved"
  | "rejected"
  | "submitted"
  | "error";

export interface QuestionnaireAnswer {
  id: string;
  question_text: string;
  question_type: string;
  draft_answer: string;
  final_answer?: string;
  confidence: "high" | "medium" | "low";
  requires_review: boolean;
  sources: string[];
  rationale?: string;
  user_edited: boolean;
  approved: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface PaginatedJobs {
  items: Job[];
  total: number;
  page: number;
  page_size: number;
}
