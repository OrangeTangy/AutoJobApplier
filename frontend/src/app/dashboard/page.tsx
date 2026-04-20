"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Sidebar } from "@/components/layout/Sidebar";
import { jobsApi, applicationsApi } from "@/lib/api";
import { fitScoreBg, statusLabel, timeAgo } from "@/lib/utils";

export default function DashboardPage() {
  const { data: jobsData } = useQuery({
    queryKey: ["jobs", "dashboard"],
    queryFn: () => jobsApi.list({ page_size: 5 }).then((r) => r.data),
  });

  const { data: applications } = useQuery({
    queryKey: ["applications", "dashboard"],
    queryFn: () => applicationsApi.list().then((r) => r.data),
  });

  const statusCounts = applications?.reduce(
    (acc, app) => {
      acc[app.status] = (acc[app.status] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  ) ?? {};

  const pendingReview = applications?.filter((a) => a.status === "ready_for_review").length ?? 0;

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-4xl">
          <h1 className="text-2xl font-bold text-gray-900 mb-6">Dashboard</h1>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            {[
              { label: "Jobs Found", value: jobsData?.total ?? 0, color: "blue" },
              { label: "Pending Review", value: pendingReview, color: "yellow", urgent: pendingReview > 0 },
              { label: "Approved", value: statusCounts.approved ?? 0, color: "green" },
              { label: "Submitted", value: statusCounts.submitted ?? 0, color: "indigo" },
            ].map((stat) => (
              <div key={stat.label} className={`card p-4 ${stat.urgent ? "ring-2 ring-yellow-400" : ""}`}>
                <p className="text-sm text-gray-500">{stat.label}</p>
                <p className="text-3xl font-bold text-gray-900 mt-1">{stat.value}</p>
              </div>
            ))}
          </div>

          {/* Pending review alert */}
          {pendingReview > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6 flex items-center justify-between">
              <div>
                <p className="font-medium text-yellow-800">
                  {pendingReview} application{pendingReview > 1 ? "s" : ""} waiting for your review
                </p>
                <p className="text-sm text-yellow-700 mt-0.5">Review and approve before submission</p>
              </div>
              <Link href="/applications?status=ready_for_review" className="btn-primary bg-yellow-600 hover:bg-yellow-700 text-sm">
                Review Now
              </Link>
            </div>
          )}

          {/* Recent jobs */}
          <div className="card">
            <div className="flex items-center justify-between p-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">Recent Jobs</h2>
              <Link href="/jobs" className="text-sm text-blue-600 hover:underline">View all</Link>
            </div>
            <div className="divide-y divide-gray-50">
              {jobsData?.items.length === 0 && (
                <div className="p-8 text-center text-gray-500">
                  <p>No jobs yet.</p>
                  <Link href="/jobs" className="btn-primary mt-4 text-sm">Add your first job</Link>
                </div>
              )}
              {jobsData?.items.map((job) => (
                <Link
                  key={job.id}
                  href={`/jobs/${job.id}`}
                  className="flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
                >
                  <div>
                    <p className="font-medium text-gray-900">{job.title ?? "Parsing..."}</p>
                    <p className="text-sm text-gray-500">{job.company ?? ""} {job.location ? `· ${job.location}` : ""}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{timeAgo(job.discovered_at)}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    {job.fit_score != null && (
                      <span className={`badge ${fitScoreBg(job.fit_score)}`}>
                        {job.fit_score}% fit
                      </span>
                    )}
                    <span className="text-xs text-gray-400">{statusLabel(job.status)}</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
