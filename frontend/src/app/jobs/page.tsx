"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sidebar } from "@/components/layout/Sidebar";
import { jobsApi } from "@/lib/api";
import { fitScoreBg, statusLabel, timeAgo } from "@/lib/utils";
import Link from "next/link";
import toast from "react-hot-toast";

export default function JobsPage() {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["jobs", statusFilter, page],
    queryFn: () =>
      jobsApi.list({ status: statusFilter || undefined, page, page_size: 20 }).then((r) => r.data),
  });

  const ingestMutation = useMutation({
    mutationFn: (u: string) => jobsApi.ingest(u),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setUrl("");
      toast.success("Job added! Parsing in the background...");
    },
    onError: (err: any) => toast.error(err.response?.data?.detail ?? "Failed to add job"),
  });

  const handleIngest = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    ingestMutation.mutate(url.trim());
  };

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-4xl">
          <h1 className="text-2xl font-bold text-gray-900 mb-6">Jobs</h1>

          {/* Ingest form */}
          <div className="card p-4 mb-6">
            <h2 className="font-medium text-gray-900 mb-3">Add Job Posting</h2>
            <form onSubmit={handleIngest} className="flex gap-3">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="Paste job posting URL..."
                className="input flex-1"
                required
              />
              <button
                type="submit"
                disabled={ingestMutation.isPending}
                className="btn-primary"
              >
                {ingestMutation.isPending ? "Adding..." : "Add Job"}
              </button>
            </form>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-3 mb-4">
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
              className="input w-auto"
            >
              <option value="">All statuses</option>
              <option value="scored">Scored</option>
              <option value="ready_for_review">Ready for Review</option>
              <option value="approved">Approved</option>
              <option value="submitted">Submitted</option>
              <option value="parsing">Parsing</option>
            </select>
            {data && (
              <p className="text-sm text-gray-500">{data.total} job{data.total !== 1 ? "s" : ""}</p>
            )}
          </div>

          {/* Job list */}
          <div className="card divide-y divide-gray-50">
            {isLoading && (
              <div className="p-8 text-center text-gray-500">Loading...</div>
            )}
            {!isLoading && data?.items.length === 0 && (
              <div className="p-8 text-center text-gray-500">No jobs found. Add a job posting URL above.</div>
            )}
            {data?.items.map((job) => (
              <Link
                key={job.id}
                href={`/jobs/${job.id}`}
                className="flex items-start justify-between p-4 hover:bg-gray-50 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-900 truncate">
                    {job.title ?? <span className="text-gray-400 italic">Parsing...</span>}
                  </p>
                  <p className="text-sm text-gray-600">
                    {[job.company, job.location].filter(Boolean).join(" · ")}
                    {job.remote_policy && job.remote_policy !== "unknown" && (
                      <span className="ml-2 badge bg-blue-50 text-blue-700">{job.remote_policy}</span>
                    )}
                  </p>
                  {job.required_skills.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {job.required_skills.slice(0, 5).map((s) => (
                        <span key={s} className="badge bg-gray-100 text-gray-600">{s}</span>
                      ))}
                      {job.required_skills.length > 5 && (
                        <span className="badge bg-gray-100 text-gray-500">+{job.required_skills.length - 5}</span>
                      )}
                    </div>
                  )}
                  <p className="text-xs text-gray-400 mt-1">{timeAgo(job.discovered_at)}</p>
                </div>
                <div className="ml-4 flex flex-col items-end gap-2 shrink-0">
                  {job.fit_score != null && (
                    <span className={`badge ${fitScoreBg(job.fit_score)} text-sm font-semibold`}>
                      {job.fit_score}%
                    </span>
                  )}
                  <span className="text-xs text-gray-500">{statusLabel(job.status)}</span>
                </div>
              </Link>
            ))}
          </div>

          {/* Pagination */}
          {data && data.total > data.page_size && (
            <div className="flex justify-center gap-3 mt-4">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="btn-secondary"
              >
                Previous
              </button>
              <span className="text-sm text-gray-500 self-center">
                Page {page} of {Math.ceil(data.total / data.page_size)}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= Math.ceil(data.total / data.page_size)}
                className="btn-secondary"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
