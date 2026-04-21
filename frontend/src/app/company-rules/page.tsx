"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

interface CompanyRule {
  id: string;
  company: string;
  rule_type: "blacklist" | "allowlist" | "cooldown";
  reason: string | null;
  cooldown_days: number | null;
  created_at: string;
}

const RULE_TYPE_LABELS: Record<string, { label: string; color: string; desc: string }> = {
  blacklist: {
    label: "Blacklist",
    color: "bg-red-100 text-red-800",
    desc: "Never apply to this company",
  },
  allowlist: {
    label: "Allow",
    color: "bg-green-100 text-green-800",
    desc: "Always allow applications to this company",
  },
  cooldown: {
    label: "Cooldown",
    color: "bg-yellow-100 text-yellow-800",
    desc: "Pause applications for N days after a submission",
  },
};

export default function CompanyRulesPage() {
  const queryClient = useQueryClient();
  const [company, setCompany] = useState("");
  const [ruleType, setRuleType] = useState<"blacklist" | "allowlist" | "cooldown">("blacklist");
  const [reason, setReason] = useState("");
  const [cooldownDays, setCooldownDays] = useState(30);
  const [formError, setFormError] = useState("");

  const { data: rules = [], isLoading } = useQuery<CompanyRule[]>({
    queryKey: ["company-rules"],
    queryFn: async () => {
      const res = await apiClient.get("/company-rules");
      return res.data;
    },
  });

  const createMutation = useMutation({
    mutationFn: async (body: object) => {
      const res = await apiClient.post("/company-rules", body);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["company-rules"] });
      setCompany("");
      setReason("");
      setFormError("");
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.detail || "Failed to create rule");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (ruleId: string) => {
      await apiClient.delete(`/company-rules/${ruleId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["company-rules"] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!company.trim()) {
      setFormError("Company name is required");
      return;
    }
    createMutation.mutate({
      company: company.trim(),
      rule_type: ruleType,
      reason: reason.trim() || null,
      cooldown_days: ruleType === "cooldown" ? cooldownDays : null,
    });
  };

  const byType = (type: string) => rules.filter((r) => r.rule_type === type);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Company Rules</h1>
      <p className="text-gray-500 mb-8">
        Control which companies you apply to — blacklist, allowlist, or add a cooling-off period.
      </p>

      {/* Add rule form */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 mb-8 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Add Rule</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Company Name *
              </label>
              <input
                type="text"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="e.g. Acme Corp"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Rule Type *</label>
              <select
                value={ruleType}
                onChange={(e) => setRuleType(e.target.value as typeof ruleType)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="blacklist">Blacklist — never apply</option>
                <option value="allowlist">Allow — always apply</option>
                <option value="cooldown">Cooldown — pause after submission</option>
              </select>
            </div>
          </div>

          {ruleType === "cooldown" && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Cooldown Days *
              </label>
              <input
                type="number"
                min={1}
                max={365}
                value={cooldownDays}
                onChange={(e) => setCooldownDays(Number(e.target.value))}
                className="w-32 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <span className="ml-2 text-sm text-gray-500">days between applications</span>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Reason <span className="text-gray-400">(optional)</span>
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Bad interview experience"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {formError && <p className="text-sm text-red-600">{formError}</p>}

          <button
            type="submit"
            disabled={createMutation.isPending}
            className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-60 transition-colors"
          >
            {createMutation.isPending ? "Adding…" : "Add Rule"}
          </button>
        </form>
      </div>

      {/* Rule lists by type */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-400">Loading rules…</div>
      ) : rules.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          No rules yet. Add one above to control which companies you apply to.
        </div>
      ) : (
        <div className="space-y-6">
          {(["blacklist", "cooldown", "allowlist"] as const).map((type) => {
            const group = byType(type);
            if (group.length === 0) return null;
            const meta = RULE_TYPE_LABELS[type];
            return (
              <div key={type}>
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  {meta.label} ({group.length})
                </h3>
                <div className="space-y-2">
                  {group.map((rule) => (
                    <div
                      key={rule.id}
                      className="flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${meta.color}`}
                        >
                          {meta.label}
                        </span>
                        <span className="font-medium text-gray-900 truncate">{rule.company}</span>
                        {rule.cooldown_days && (
                          <span className="text-xs text-gray-500">{rule.cooldown_days}d</span>
                        )}
                        {rule.reason && (
                          <span className="text-xs text-gray-400 truncate hidden sm:block">
                            — {rule.reason}
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => deleteMutation.mutate(rule.id)}
                        disabled={deleteMutation.isPending}
                        className="ml-4 text-sm text-red-500 hover:text-red-700 disabled:opacity-50 shrink-0"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
