"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

interface IngestionSource {
  id: string;
  source_type: "imap" | "gmail";
  display_name: string;
  is_active: boolean;
  last_polled_at: string | null;
  created_at: string;
}

type Tab = "sources" | "handshake" | "urls" | "json";

interface ImportResult {
  imported: number;
  skipped_duplicates: number;
  errors: number;
}

export default function IngestionPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("sources");

  // ── Sources ───────────────────────────────────────────────────────────────
  const { data: sources = [], isLoading: sourcesLoading } = useQuery<IngestionSource[]>({
    queryKey: ["sources"],
    queryFn: async () => {
      const res = await apiClient.get("/ingestion/sources");
      return res.data;
    },
  });

  const toggleMutation = useMutation({
    mutationFn: async ({ id, active }: { id: string; active: boolean }) => {
      await apiClient.patch(`/ingestion/sources/${id}`, { is_active: active });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await apiClient.delete(`/ingestion/sources/${id}`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });

  // ── Handshake import ──────────────────────────────────────────────────────
  const [handshakeFile, setHandshakeFile] = useState<File | null>(null);
  const [handshakeResult, setHandshakeResult] = useState<ImportResult | null>(null);

  const handshakeMutation = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiClient.post("/import/handshake", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return res.data as ImportResult;
    },
    onSuccess: (data) => setHandshakeResult(data),
  });

  // ── URL list import ───────────────────────────────────────────────────────
  const [urlsText, setUrlsText] = useState("");
  const [urlsResult, setUrlsResult] = useState<ImportResult | null>(null);

  const urlsMutation = useMutation({
    mutationFn: async (text: string) => {
      const fd = new FormData();
      fd.append("urls_text", text);
      const res = await apiClient.post("/import/urls", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return res.data as ImportResult;
    },
    onSuccess: (data) => setUrlsResult(data),
  });

  // ── JSON import ───────────────────────────────────────────────────────────
  const [jsonFile, setJsonFile] = useState<File | null>(null);
  const [jsonResult, setJsonResult] = useState<ImportResult | null>(null);

  const jsonMutation = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiClient.post("/import/json", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return res.data as ImportResult;
    },
    onSuccess: (data) => setJsonResult(data),
  });

  const TABS: { id: Tab; label: string }[] = [
    { id: "sources", label: "Email Sources" },
    { id: "handshake", label: "Handshake CSV" },
    { id: "urls", label: "URL List" },
    { id: "json", label: "JSON Import" },
  ];

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Job Ingestion</h1>
      <p className="text-gray-500 mb-6">
        Connect email sources for automatic job discovery, or import jobs in bulk from Handshake,
        URLs, or JSON.
      </p>

      {/* Tab bar */}
      <div className="flex border-b border-gray-200 mb-6 gap-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.id
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Email Sources tab ───────────────────────────────────────────────── */}
      {tab === "sources" && (
        <div>
          {sourcesLoading ? (
            <p className="text-gray-400 text-center py-12">Loading sources…</p>
          ) : sources.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <p className="mb-2">No email sources configured.</p>
              <p className="text-sm">
                Configure IMAP or Gmail credentials in your{" "}
                <code className="text-xs bg-gray-100 px-1 rounded">.env</code> to enable automatic
                job discovery from your inbox.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {sources.map((source) => (
                <div
                  key={source.id}
                  className="flex items-center justify-between bg-white border border-gray-200 rounded-xl px-5 py-4 shadow-sm"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">{source.display_name}</span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          source.source_type === "gmail"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {source.source_type.toUpperCase()}
                      </span>
                      {source.is_active ? (
                        <span className="text-xs text-green-600 font-medium">● Active</span>
                      ) : (
                        <span className="text-xs text-gray-400 font-medium">○ Paused</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 mt-1">
                      Last polled:{" "}
                      {source.last_polled_at
                        ? new Date(source.last_polled_at).toLocaleString()
                        : "Never"}
                    </p>
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={() =>
                        toggleMutation.mutate({ id: source.id, active: !source.is_active })
                      }
                      className="text-sm text-blue-600 hover:text-blue-800 font-medium"
                    >
                      {source.is_active ? "Pause" : "Resume"}
                    </button>
                    <button
                      onClick={() => {
                        if (confirm("Remove this source?")) deleteMutation.mutate(source.id);
                      }}
                      className="text-sm text-red-500 hover:text-red-700"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Handshake CSV tab ───────────────────────────────────────────────── */}
      {tab === "handshake" && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-800 mb-1">Import Handshake CSV</h2>
          <p className="text-sm text-gray-500 mb-4">
            Export jobs from Handshake (Jobs → Export), then upload the CSV file here.
          </p>
          <div className="space-y-4">
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setHandshakeFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
            <button
              onClick={() => handshakeFile && handshakeMutation.mutate(handshakeFile)}
              disabled={!handshakeFile || handshakeMutation.isPending}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {handshakeMutation.isPending ? "Importing…" : "Import"}
            </button>
            {handshakeResult && <ImportResultBanner result={handshakeResult} />}
          </div>
        </div>
      )}

      {/* ── URL List tab ────────────────────────────────────────────────────── */}
      {tab === "urls" && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-800 mb-1">Import URL List</h2>
          <p className="text-sm text-gray-500 mb-4">
            Paste one job posting URL per line. The system will fetch and parse each one.
          </p>
          <div className="space-y-4">
            <textarea
              rows={8}
              value={urlsText}
              onChange={(e) => setUrlsText(e.target.value)}
              placeholder={"https://jobs.lever.co/acme/abc123\nhttps://boards.greenhouse.io/..."}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={() => urlsMutation.mutate(urlsText)}
              disabled={!urlsText.trim() || urlsMutation.isPending}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {urlsMutation.isPending ? "Importing…" : "Import URLs"}
            </button>
            {urlsResult && <ImportResultBanner result={urlsResult} />}
          </div>
        </div>
      )}

      {/* ── JSON Import tab ─────────────────────────────────────────────────── */}
      {tab === "json" && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-800 mb-1">Import JSON Array</h2>
          <p className="text-sm text-gray-500 mb-2">
            Upload a JSON file containing an array of job objects. Each object may include:
          </p>
          <pre className="bg-gray-50 rounded-lg p-3 text-xs text-gray-600 mb-4 overflow-x-auto">
            {`[
  {
    "title": "Software Engineer",
    "company": "Acme Corp",
    "location": "San Francisco, CA",
    "raw_url": "https://...",
    "description": "..."
  }
]`}
          </pre>
          <div className="space-y-4">
            <input
              type="file"
              accept=".json"
              onChange={(e) => setJsonFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
            <button
              onClick={() => jsonFile && jsonMutation.mutate(jsonFile)}
              disabled={!jsonFile || jsonMutation.isPending}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {jsonMutation.isPending ? "Importing…" : "Import"}
            </button>
            {jsonResult && <ImportResultBanner result={jsonResult} />}
          </div>
        </div>
      )}
    </div>
  );
}

function ImportResultBanner({ result }: { result: ImportResult }) {
  return (
    <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm">
      <span className="font-semibold text-green-800">Import complete —</span>{" "}
      <span className="text-green-700">
        {result.imported} imported, {result.skipped_duplicates} duplicates skipped
        {result.errors > 0 && (
          <span className="text-red-600">, {result.errors} errors</span>
        )}
      </span>
    </div>
  );
}
