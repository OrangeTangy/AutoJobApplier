import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { formatDistanceToNow } from "date-fns";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function timeAgo(date: string | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true });
}

export function formatSalary(min?: number, max?: number, currency = "USD"): string {
  if (!min && !max) return "Not specified";
  const fmt = (n: number) =>
    new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(n);
  if (min && max) return `${fmt(min)} – ${fmt(max)}`;
  if (min) return `${fmt(min)}+`;
  return `Up to ${fmt(max!)}`;
}

export function fitScoreColor(score?: number): string {
  if (!score) return "text-gray-400";
  if (score >= 80) return "text-green-600";
  if (score >= 60) return "text-yellow-600";
  if (score >= 40) return "text-orange-500";
  return "text-red-500";
}

export function fitScoreBg(score?: number): string {
  if (!score) return "bg-gray-100 text-gray-600";
  if (score >= 80) return "bg-green-100 text-green-800";
  if (score >= 60) return "bg-yellow-100 text-yellow-800";
  if (score >= 40) return "bg-orange-100 text-orange-800";
  return "bg-red-100 text-red-800";
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    new: "New",
    parsing: "Parsing...",
    parsed: "Parsed",
    scored: "Scored",
    draft: "Draft",
    ready_for_review: "Ready for Review",
    approved: "Approved",
    submitted: "Submitted",
    rejected_by_user: "Rejected",
    rejected_by_employer: "Not Selected",
    error: "Error",
  };
  return labels[status] ?? status;
}

export function confidenceColor(confidence: string): string {
  const map: Record<string, string> = {
    high: "text-green-700 bg-green-50",
    medium: "text-yellow-700 bg-yellow-50",
    low: "text-red-700 bg-red-50",
  };
  return map[confidence] ?? "text-gray-600 bg-gray-50";
}

export function storeTokens(access: string, refresh: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("access_token", access);
    localStorage.setItem("refresh_token", refresh);
  }
}

export function clearTokens(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  }
}

export function getStoredToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("access_token");
  }
  return null;
}
