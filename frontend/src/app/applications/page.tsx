"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Sidebar } from "@/components/layout/Sidebar";
import { applicationsApi } from "@/lib/api";
import { statusLabel, timeAgo } from "@/lib/utils";
import { Suspense } from "react";

function ApplicationsList() {
  const searchParams = useSearchParams();
  const statusFilter = searchParams.get("status") ?? undefined;

  const { data: apps, isLoading } = useQuery({
    queryKey: ["applications", statusFilter],
    queryFn: () => applicationsApi.list(statusFilter).then((r) => r.data),
  });

  const statusColors: Record<string, string> = {
    draft: "bg-gray-100 text-gray-600",
    ready_for_review: "bg-yellow-100 text-yellow-800",
    approved: "bg-green-100 text-green-800",
    rejected: "bg-red-100 text-red-700",
    submitted: "bg-blue-100 text-blue-700",
    error: "bg-red-200 text-red-800",
  };

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-3xl">
          <h1 className="text-2xl font-bold text-gray-900 mb-6">Applications</h1>

          {isLoading && <div className="text-gray-500">Loading...</div>}

          {!isLoading && apps?.length === 0 && (
            <div className="card p-8 text-center text-gray-500">
              <p>No applications yet.</p>
              <Link href="/jobs" className="btn-primary mt-4 text-sm inline-block">
                Browse Jobs
              </Link>
            </div>
          )}

          <div className="card divide-y divide-gray-50">
            {apps?.map((app) => (
              <Link
                key={app.id}
                href={`/applications/${app.id}`}
                className="flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`badge ${statusColors[app.status] ?? "bg-gray-100 text-gray-600"}`}>
                      {statusLabel(app.status)}
                    </span>
                    {app.status === "ready_for_review" && (
                      <span className="text-xs text-yellow-600 font-medium">Review required</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500 mt-1">{timeAgo(app.created_at)}</p>
                  <p className="text-xs text-gray-400">{app.answers.length} questions</p>
                </div>
                <span className="text-blue-600 text-sm">Review →</span>
              </Link>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

export default function ApplicationsPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen"><Sidebar /><main className="flex-1 p-8">Loading...</main></div>}>
      <ApplicationsList />
    </Suspense>
  );
}
