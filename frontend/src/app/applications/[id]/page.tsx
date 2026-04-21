"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { applicationsApi } from "@/lib/api";
import { confidenceColor, statusLabel } from "@/lib/utils";
import { QuestionnaireAnswer } from "@/types";
import toast from "react-hot-toast";
import Link from "next/link";

export default function ApplicationReviewPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const router = useRouter();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [approveConfirm, setApproveConfirm] = useState(false);

  const { data: app, isLoading } = useQuery({
    queryKey: ["application", id],
    queryFn: () => applicationsApi.get(id).then((r) => r.data),
    refetchInterval: (query) =>
      query.state.data?.status === "draft" ? 3000 : false,
  });

  const editMutation = useMutation({
    mutationFn: ({ answerId, text }: { answerId: string; text: string }) =>
      applicationsApi.editAnswer(id, answerId, text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", id] });
      setEditingId(null);
      toast.success("Answer updated");
    },
    onError: () => toast.error("Failed to save answer"),
  });

  const approveMutation = useMutation({
    mutationFn: () => applicationsApi.approve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", id] });
      setApproveConfirm(false);
      toast.success("Application approved!");
    },
    onError: (err: any) => toast.error(err.response?.data?.detail ?? "Approval failed"),
  });

  const rejectMutation = useMutation({
    mutationFn: () => applicationsApi.reject(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      router.push("/applications");
      toast("Application rejected");
    },
  });

  const submitMutation = useMutation({
    mutationFn: () => applicationsApi.submit(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", id] });
      toast.success("Submission started!");
    },
    onError: (err: any) => toast.error(err.response?.data?.detail ?? "Submission failed"),
  });

  if (isLoading) {
    return (
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 p-8">
          <div className="max-w-3xl animate-pulse space-y-4">
            {[1, 2, 3].map((i) => <div key={i} className="h-24 bg-gray-200 rounded" />)}
          </div>
        </main>
      </div>
    );
  }

  if (!app) return null;

  const unansweredRequired = app.answers.filter(
    (a) => a.requires_review && !a.final_answer && !a.draft_answer
  ).length;

  const hasUnreviewedSensitive = app.answers.some(
    (a) => a.requires_review && !a.approved
  );

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-3xl">
          <Link href="/applications" className="text-sm text-blue-600 hover:underline mb-4 inline-block">
            ← Back to applications
          </Link>

          {/* Status header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Application Review</h1>
              <p className="text-sm text-gray-500 mt-1">
                Status: <span className="font-medium">{statusLabel(app.status)}</span>
                {app.status === "draft" && " — Generating answers..."}
              </p>
            </div>
            <div className="flex gap-2">
              {app.status === "ready_for_review" && !approveConfirm && (
                <>
                  <button
                    onClick={() => rejectMutation.mutate()}
                    disabled={rejectMutation.isPending}
                    className="btn-secondary text-red-600 border-red-200 hover:bg-red-50"
                  >
                    Reject
                  </button>
                  <button
                    onClick={() => setApproveConfirm(true)}
                    className="btn-primary bg-green-600 hover:bg-green-700"
                  >
                    Approve & Review →
                  </button>
                </>
              )}
              {approveConfirm && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-center gap-4">
                  <p className="text-sm font-medium text-green-800">
                    Confirm approval? This locks in the answers above.
                  </p>
                  <button
                    onClick={() => approveMutation.mutate()}
                    disabled={approveMutation.isPending}
                    className="btn-primary bg-green-700 hover:bg-green-800 text-sm"
                  >
                    {approveMutation.isPending ? "Approving..." : "Yes, Approve"}
                  </button>
                  <button onClick={() => setApproveConfirm(false)} className="text-sm text-gray-500">
                    Cancel
                  </button>
                </div>
              )}
              {app.status === "approved" && (
                <button
                  onClick={() => submitMutation.mutate()}
                  disabled={submitMutation.isPending}
                  className="btn-primary"
                >
                  {submitMutation.isPending ? "Submitting..." : "Submit Application →"}
                </button>
              )}
            </div>
          </div>

          {/* Warnings */}
          {hasUnreviewedSensitive && app.status === "ready_for_review" && (
            <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 mb-4 text-sm text-orange-800">
              Some answers marked for mandatory review. Please check them before approving.
            </div>
          )}

          {/* Cover letter */}
          {app.cover_letter && (
            <div className="mb-6">
              <details className="group">
                <summary className="cursor-pointer font-semibold text-gray-900 flex items-center gap-2 select-none">
                  <span className="text-sm text-gray-400 group-open:rotate-90 transition-transform inline-block">▶</span>
                  Cover Letter
                </summary>
                <div className="mt-3 p-4 bg-gray-50 rounded-lg border border-gray-200 text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
                  {app.cover_letter}
                </div>
              </details>
            </div>
          )}

          {/* Questionnaire */}
          <div className="space-y-4">
            <h2 className="font-semibold text-gray-900">
              Application Questions ({app.answers.length})
            </h2>

            {app.status === "draft" && app.answers.length === 0 && (
              <div className="card p-6 text-center text-gray-500">
                <div className="animate-spin w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full mx-auto mb-3" />
                Generating answers from your profile...
              </div>
            )}

            {app.answers.map((answer) => (
              <AnswerCard
                key={answer.id}
                answer={answer}
                isEditing={editingId === answer.id}
                editText={editText}
                onEdit={() => {
                  setEditingId(answer.id);
                  setEditText(answer.final_answer ?? answer.draft_answer);
                }}
                onSave={() => editMutation.mutate({ answerId: answer.id, text: editText })}
                onCancel={() => setEditingId(null)}
                onEditTextChange={setEditText}
                locked={app.status === "approved" || app.status === "submitted"}
              />
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

function AnswerCard({
  answer,
  isEditing,
  editText,
  onEdit,
  onSave,
  onCancel,
  onEditTextChange,
  locked,
}: {
  answer: QuestionnaireAnswer;
  isEditing: boolean;
  editText: string;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  onEditTextChange: (t: string) => void;
  locked: boolean;
}) {
  const displayAnswer = answer.final_answer ?? answer.draft_answer;

  return (
    <div className={`card p-4 ${answer.requires_review ? "ring-1 ring-orange-200" : ""}`}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-gray-500 uppercase">{answer.question_type.replace(/_/g, " ")}</span>
            <span className={`badge ${confidenceColor(answer.confidence)}`}>
              {answer.confidence} confidence
            </span>
            {answer.requires_review && (
              <span className="badge bg-orange-100 text-orange-700">Review required</span>
            )}
            {answer.user_edited && (
              <span className="badge bg-purple-100 text-purple-700">Edited</span>
            )}
          </div>
          <p className="font-medium text-gray-900 mt-1 text-sm">{answer.question_text}</p>
        </div>
        {!locked && !isEditing && (
          <button onClick={onEdit} className="text-xs text-blue-600 hover:underline ml-2 shrink-0">
            Edit
          </button>
        )}
      </div>

      {isEditing ? (
        <div className="mt-2 space-y-2">
          <textarea
            value={editText}
            onChange={(e) => onEditTextChange(e.target.value)}
            rows={4}
            className="input w-full resize-y"
            placeholder="Your answer..."
          />
          <div className="flex gap-2">
            <button onClick={onSave} className="btn-primary text-xs py-1.5">Save</button>
            <button onClick={onCancel} className="btn-secondary text-xs py-1.5">Cancel</button>
          </div>
        </div>
      ) : (
        <div className="mt-2 p-3 bg-gray-50 rounded text-sm text-gray-800 whitespace-pre-wrap">
          {displayAnswer || <span className="text-gray-400 italic">No answer generated</span>}
        </div>
      )}

      {answer.sources.length > 0 && (
        <p className="text-xs text-gray-400 mt-2">
          Sources: {answer.sources.join(", ")}
        </p>
      )}
      {answer.rationale && (
        <p className="text-xs text-gray-500 mt-1 italic">{answer.rationale}</p>
      )}
    </div>
  );
}
