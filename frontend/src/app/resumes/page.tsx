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
  const [form, setForm] = useState({ name: "", latex_source: "", is_base: true });
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
      setForm({ name: "", latex_source: "", is_base: true });
      toast.success("Resume added to library!");
    },
    onError: (err: any) => toast.error(err.response?.data?.detail ?? "Upload failed"),
  });

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setForm((f) => ({ ...f, latex_source: text, name: f.name || file.name.replace(".tex", "") }));
  };

  const libraryResumes = resumes?.filter((r) => r.is_base) ?? [];
  const derivedResumes = resumes?.filter((r) => !r.is_base) ?? [];

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-3xl">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-2xl font-bold text-gray-900">Resume Library</h1>
            <button onClick={() => setShowUpload(!showUpload)} className="btn-primary">
              {showUpload ? "Cancel" : "+ Add Resume"}
            </button>
          </div>
          <p className="text-sm text-gray-500 mb-6">
            Upload multiple LaTeX resumes — one per job family (e.g. "Backend Engineering",
            "Data Science", "Product Management"). The system automatically picks the best match
            for each job using TF-IDF similarity. No AI API key needed.
          </p>

          {/* Upload form */}
          {showUpload && (
            <div className="card p-5 mb-6">
              <h2 className="font-semibold text-gray-900 mb-4">Add to Library</h2>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Label <span className="text-gray-400 font-normal">(describe the focus)</span>
                  </label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="input"
                    placeholder="e.g. Backend Engineer — Python/AWS focus"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    LaTeX File (.tex)
                  </label>
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
                      Preview
                    </label>
                    <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto max-h-28 text-gray-600">
                      {form.latex_source.slice(0, 300)}…
                    </pre>
                  </div>
                )}
                <button
                  onClick={() => uploadMutation.mutate()}
                  disabled={!form.name || !form.latex_source || uploadMutation.isPending}
                  className="btn-primary"
                >
                  {uploadMutation.isPending ? "Uploading…" : "Add to Library"}
                </button>
              </div>
            </div>
          )}

          {/* Empty state */}
          {!isLoading && libraryResumes.length === 0 && !showUpload && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-6 mb-6 text-sm text-blue-800">
              <p className="font-semibold mb-1">Your resume library is empty</p>
              <p>
                Add at least one LaTeX resume (.tex) to enable automatic job matching.
                For best results, add one resume per specialisation — the system will
                select the highest-scoring match for each job.
              </p>
            </div>
          )}

          {isLoading && <div className="text-gray-500 py-8 text-center">Loading…</div>}

          {/* Library resumes */}
          {libraryResumes.length > 0 && (
            <div className="mb-8">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                Library ({libraryResumes.length})
              </h2>
              <div className="space-y-3">
                {libraryResumes.map((resume) => (
                  <ResumeCard key={resume.id} resume={resume} />
                ))}
              </div>
            </div>
          )}

          {/* Derived / tailored resumes */}
          {derivedResumes.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                Used in Applications ({derivedResumes.length})
              </h2>
              <div className="space-y-3">
                {derivedResumes.map((resume) => (
                  <ResumeCard key={resume.id} resume={resume} />
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function ResumeCard({ resume }: { resume: Resume }) {
  return (
    <div className="card p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-900 truncate">{resume.name}</span>
            {resume.is_base && (
              <span className="badge bg-blue-100 text-blue-700">Library</span>
            )}
            {resume.job_id && (
              <span className="badge bg-purple-100 text-purple-700">Applied</span>
            )}
          </div>
          <p className="text-sm text-gray-400 mt-0.5">{timeAgo(resume.created_at)}</p>
        </div>
        <div className="flex gap-2 shrink-0 ml-3">
          {resume.compiled_pdf_path && (
            <a
              href={`${process.env.NEXT_PUBLIC_API_URL}/resumes/${resume.id}/pdf`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary text-xs py-1.5"
            >
              PDF
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
