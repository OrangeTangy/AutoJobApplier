"use client";

import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sidebar } from "@/components/layout/Sidebar";
import { resumesApi } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import toast from "react-hot-toast";
import { Resume } from "@/types";

export default function ResumesPage() {
  const qc = useQueryClient();
  const [showUpload, setShowUpload] = useState(false);
  const [form, setForm] = useState({ name: "", latex_source: "", is_base: false });
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: resumes, isLoading } = useQuery({
    queryKey: ["resumes"],
    queryFn: () => resumesApi.list().then((r) => r.data),
  });

  const uploadMutation = useMutation({
    mutationFn: () => resumesApi.upload(form.name, form.latex_source, form.is_base),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["resumes"] });
      setShowUpload(false);
      setForm({ name: "", latex_source: "", is_base: false });
      toast.success("Resume uploaded!");
    },
    onError: (err: any) => toast.error(err.response?.data?.detail ?? "Upload failed"),
  });

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setForm((f) => ({ ...f, latex_source: text, name: f.name || file.name.replace(".tex", "") }));
  };

  const baseResume = resumes?.find((r) => r.is_base);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-3xl">
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-bold text-gray-900">Resumes</h1>
            <button onClick={() => setShowUpload(!showUpload)} className="btn-primary">
              {showUpload ? "Cancel" : "Upload Resume"}
            </button>
          </div>

          {/* Upload form */}
          {showUpload && (
            <div className="card p-5 mb-6">
              <h2 className="font-semibold text-gray-900 mb-4">Upload LaTeX Resume</h2>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="input"
                    placeholder="e.g. Software Engineer Resume"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">LaTeX File</label>
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".tex"
                    onChange={handleFile}
                    className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                  />
                </div>
                {form.latex_source && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Preview (first 200 chars)
                    </label>
                    <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto max-h-32 text-gray-600">
                      {form.latex_source.slice(0, 200)}...
                    </pre>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="is_base"
                    checked={form.is_base}
                    onChange={(e) => setForm({ ...form, is_base: e.target.checked })}
                    className="rounded border-gray-300"
                  />
                  <label htmlFor="is_base" className="text-sm text-gray-700">
                    Set as base resume (used for tailoring)
                  </label>
                </div>
                <button
                  onClick={() => uploadMutation.mutate()}
                  disabled={!form.name || !form.latex_source || uploadMutation.isPending}
                  className="btn-primary"
                >
                  {uploadMutation.isPending ? "Uploading..." : "Upload"}
                </button>
              </div>
            </div>
          )}

          {/* Info box */}
          {!baseResume && !showUpload && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4 text-sm text-blue-800">
              Upload your base resume (.tex) to enable tailoring for each job.
            </div>
          )}

          {/* Resume list */}
          {isLoading && <div className="text-gray-500">Loading...</div>}
          <div className="space-y-3">
            {resumes?.map((resume) => (
              <ResumeCard key={resume.id} resume={resume} />
            ))}
            {!isLoading && resumes?.length === 0 && (
              <div className="card p-8 text-center text-gray-500">
                No resumes yet. Upload your LaTeX resume to get started.
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

function ResumeCard({ resume }: { resume: Resume }) {
  const diff = resume.tailoring_diff;

  return (
    <div className="card p-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-gray-900">{resume.name}</span>
            {resume.is_base && <span className="badge bg-blue-100 text-blue-700">Base</span>}
            {resume.job_id && <span className="badge bg-purple-100 text-purple-700">Tailored</span>}
          </div>
          <p className="text-sm text-gray-500 mt-0.5">
            {resume.word_count ? `${resume.word_count} words · ` : ""}
            {timeAgo(resume.created_at)}
          </p>
        </div>
        <div className="flex gap-2">
          {resume.compiled_pdf_path && (
            <a
              href={`${process.env.NEXT_PUBLIC_API_URL}/api/v1/resumes/${resume.id}/pdf`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary text-xs py-1.5"
            >
              Download PDF
            </a>
          )}
        </div>
      </div>

      {diff && diff.edits.length > 0 && (
        <div className="mt-3 border-t border-gray-100 pt-3">
          <p className="text-xs text-gray-500 mb-2">
            {diff.edits.length} bullet{diff.edits.length !== 1 ? "s" : ""} tailored
          </p>
          <p className="text-xs text-gray-600 italic">{diff.rationale_summary}</p>
          <details className="mt-2">
            <summary className="text-xs text-blue-600 cursor-pointer hover:underline">
              View changes
            </summary>
            <div className="mt-2 space-y-2">
              {diff.edits.slice(0, 3).map((edit, i) => (
                <div key={i} className="text-xs">
                  <p className="text-red-600 line-through">{edit.original}</p>
                  <p className="text-green-700">{edit.tailored}</p>
                  <p className="text-gray-400 italic">{edit.rationale}</p>
                </div>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
