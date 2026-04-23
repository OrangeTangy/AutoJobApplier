"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { jobsApi, applicationsApi } from "@/lib/api";
import { fitScoreBg, formatSalary, statusLabel, timeAgo } from "@/lib/utils";
import toast from "react-hot-toast";
import Link from "next/link";

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const router = useRouter();

  const { data: job, isLoading } = useQuery({
    queryKey: ["job", id],
    queryFn: () => jobsApi.get(id).then((r) => r.data),
  });

  const draftMutation = useMutation({
    mutationFn: () => applicationsApi.createDraft(id),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      toast.success("Draft application created — generating answers...");
      router.push(`/applications/${res.data.id}`);
    },
    onError: (err: any) => toast.error(err.response?.data?.detail ?? "Failed to create draft"),
  });

  if (isLoading) {
    return (
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 p-8">
          <div className="max-w-3xl animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-1/2 mb-4" />
            <div className="h-4 bg-gray-200 rounded w-1/3 mb-8" />
            <div className="h-64 bg-gray-200 rounded" />
          </div>
        </main>
      </div>
    );
  }

  if (!job) return null;

  const fit = job.fit_rationale;

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-3xl">
          {/* Header */}
          <div className="mb-6">
            <Link href="/jobs" className="text-sm text-blue-600 hover:underline mb-4 inline-block">
              ← Back to jobs
            </Link>
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  {job.title ?? "Parsing..."}
                </h1>
                <p className="text-gray-600 mt-1">
                  {[job.company, job.location].filter(Boolean).join(" · ")}
                </p>
                {job.remote_policy && job.remote_policy !== "unknown" && (
                  <span className="badge bg-blue-50 text-blue-700 mt-2">{job.remote_policy}</span>
                )}
              </div>
              <div className="text-right">
                {job.fit_score != null && (
                  <div className={`text-3xl font-bold ${fitScoreBg(job.fit_score)} px-4 py-2 rounded-lg`}>
                    {job.fit_score}%
                  </div>
                )}
                <p className="text-xs text-gray-400 mt-1">{statusLabel(job.status)}</p>
              </div>
            </div>
          </div>

          {/* Fit breakdown */}
          {fit && (
            <div className="card p-4 mb-6">
              <h2 className="font-semibold text-gray-900 mb-3">Fit Analysis</h2>
              <p className="text-sm text-gray-700 mb-3">{fit.summary}</p>

              <div className="grid grid-cols-2 gap-4">
                {fit.matched_skills.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-green-700 mb-1.5">Matched Skills</p>
                    <div className="flex flex-wrap gap-1">
                      {fit.matched_skills.map((s) => (
                        <span key={s} className="badge bg-green-50 text-green-700">{s}</span>
                      ))}
                    </div>
                  </div>
                )}
                {fit.missing_required_skills.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-red-600 mb-1.5">Missing Required</p>
                    <div className="flex flex-wrap gap-1">
                      {fit.missing_required_skills.map((s) => (
                        <span key={s} className="badge bg-red-50 text-red-600">{s}</span>
                      ))}
                    </div>
                  </div>
                )}
                {fit.red_flags.length > 0 && (
                  <div className="col-span-2">
                    <p className="text-xs font-medium text-orange-600 mb-1.5">Red Flags</p>
                    <ul className="text-sm text-orange-700 space-y-0.5">
                      {fit.red_flags.map((f, i) => <li key={i}>• {f}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Job details */}
          <div className="card p-4 mb-6 space-y-4">
            <h2 className="font-semibold text-gray-900">Job Details</h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-gray-500">Salary</p>
                <p className="font-medium">{formatSalary(job.salary_min, job.salary_max, job.salary_currency)}</p>
              </div>
              {job.years_experience_min != null && (
                <div>
                  <p className="text-gray-500">Experience</p>
                  <p className="font-medium">
                    {job.years_experience_min}
                    {job.years_experience_max ? `–${job.years_experience_max}` : "+"} years
                  </p>
                </div>
              )}
              {job.sponsorship_hint && (
                <div>
                  <p className="text-gray-500">Sponsorship</p>
                  <p className={`font-medium ${job.sponsorship_hint === "yes" ? "text-green-700" : job.sponsorship_hint === "no" ? "text-red-600" : "text-gray-700"}`}>
                    {job.sponsorship_hint === "yes" ? "Available" : job.sponsorship_hint === "no" ? "Not available" : "Unknown"}
                  </p>
                </div>
              )}
              {job.deadline && (
                <div>
                  <p className="text-gray-500">Deadline</p>
                  <p className="font-medium">{job.deadline}</p>
                </div>
              )}
            </div>

            {job.description && (
              <div>
                <p className="text-sm text-gray-500 mb-1.5">Description</p>
                <p className="text-sm text-gray-700 whitespace-pre-line max-h-48 overflow-y-auto leading-relaxed">
                  {job.description}
                </p>
              </div>
            )}
          </div>

          {/* Skills */}
          {(job.required_skills.length > 0 || job.preferred_skills.length > 0) && (
            <div className="card p-4 mb-6">
              <h2 className="font-semibold text-gray-900 mb-3">Skills</h2>
              {job.required_skills.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-gray-500 mb-1.5">Required</p>
                  <div className="flex flex-wrap gap-1">
                    {job.required_skills.map((s) => (
                      <span key={s} className="badge bg-gray-100 text-gray-700">{s}</span>
                    ))}
                  </div>
                </div>
              )}
              {job.preferred_skills.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1.5">Preferred</p>
                  <div className="flex flex-wrap gap-1">
                    {job.preferred_skills.map((s) => (
                      <span key={s} className="badge bg-blue-50 text-blue-600">{s}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            {job.application_url && (
              <a
                href={job.application_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary"
              >
                View Original Posting ↗
              </a>
            )}
            {["scored", "parsed"].includes(job.status) && (
              <button
                onClick={() => draftMutation.mutate()}
                disabled={draftMutation.isPending}
                className="btn-primary"
              >
                {draftMutation.isPending ? "Creating draft..." : "Start Application"}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
