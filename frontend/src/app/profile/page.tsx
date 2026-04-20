"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sidebar } from "@/components/layout/Sidebar";
import { profileApi } from "@/lib/api";
import { UserProfile } from "@/types";
import toast from "react-hot-toast";

const WORK_AUTH_OPTIONS = [
  { value: "citizen", label: "US Citizen" },
  { value: "permanent_resident", label: "Permanent Resident (Green Card)" },
  { value: "opt", label: "OPT / STEM OPT" },
  { value: "cpt", label: "CPT" },
  { value: "h1b", label: "H-1B" },
  { value: "other", label: "Other Visa" },
  { value: "unknown", label: "Prefer not to say" },
];

export default function ProfilePage() {
  const qc = useQueryClient();
  const { data: profile, isLoading } = useQuery({
    queryKey: ["profile"],
    queryFn: () => profileApi.get().then((r) => r.data),
  });

  const [form, setForm] = useState<Partial<UserProfile>>({});
  const [skillInput, setSkillInput] = useState("");

  useEffect(() => {
    if (profile) setForm(profile);
  }, [profile]);

  const updateMutation = useMutation({
    mutationFn: (data: Partial<UserProfile>) => profileApi.update(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile"] });
      toast.success("Profile saved!");
    },
    onError: () => toast.error("Failed to save profile"),
  });

  const addSkill = () => {
    const skill = skillInput.trim();
    if (!skill || form.skills?.includes(skill)) return;
    setForm((f) => ({ ...f, skills: [...(f.skills ?? []), skill] }));
    setSkillInput("");
  };

  const removeSkill = (s: string) => {
    setForm((f) => ({ ...f, skills: f.skills?.filter((x) => x !== s) }));
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 p-8">
          <div className="max-w-2xl animate-pulse space-y-4">
            {[1, 2, 3].map((i) => <div key={i} className="h-16 bg-gray-200 rounded" />)}
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold text-gray-900 mb-6">Profile</h1>
          <p className="text-sm text-gray-500 mb-6">
            This profile is the source of truth for all generated answers and resume tailoring. Keep it accurate — nothing will be fabricated.
          </p>

          <div className="space-y-6">
            {/* Basic info */}
            <div className="card p-5">
              <h2 className="font-semibold text-gray-900 mb-4">Basic Info</h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
                  <input
                    type="text"
                    value={form.full_name ?? ""}
                    onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                    className="input"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                  <input
                    type="tel"
                    value={form.phone ?? ""}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    className="input"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
                  <input
                    type="text"
                    value={form.location ?? ""}
                    onChange={(e) => setForm({ ...form, location: e.target.value })}
                    className="input"
                    placeholder="City, State"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">LinkedIn</label>
                  <input
                    type="url"
                    value={form.linkedin_url ?? ""}
                    onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })}
                    className="input"
                    placeholder="https://linkedin.com/in/..."
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">GitHub</label>
                  <input
                    type="url"
                    value={form.github_url ?? ""}
                    onChange={(e) => setForm({ ...form, github_url: e.target.value })}
                    className="input"
                    placeholder="https://github.com/..."
                  />
                </div>
              </div>
            </div>

            {/* Work authorization */}
            <div className="card p-5">
              <h2 className="font-semibold text-gray-900 mb-4">Work Authorization</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Authorization Status</label>
                  <select
                    value={form.work_authorization ?? "unknown"}
                    onChange={(e) => setForm({ ...form, work_authorization: e.target.value })}
                    className="input"
                  >
                    {WORK_AUTH_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id="sponsorship"
                    checked={form.requires_sponsorship ?? false}
                    onChange={(e) => setForm({ ...form, requires_sponsorship: e.target.checked })}
                    className="rounded border-gray-300"
                  />
                  <label htmlFor="sponsorship" className="text-sm text-gray-700">
                    I require visa sponsorship
                  </label>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id="relocate"
                    checked={form.willing_to_relocate ?? false}
                    onChange={(e) => setForm({ ...form, willing_to_relocate: e.target.checked })}
                    className="rounded border-gray-300"
                  />
                  <label htmlFor="relocate" className="text-sm text-gray-700">
                    Willing to relocate
                  </label>
                </div>
              </div>
            </div>

            {/* Salary */}
            <div className="card p-5">
              <h2 className="font-semibold text-gray-900 mb-4">Salary Expectations</h2>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Minimum ($)</label>
                  <input
                    type="number"
                    value={form.desired_salary_min ?? ""}
                    onChange={(e) => setForm({ ...form, desired_salary_min: parseInt(e.target.value) || undefined })}
                    className="input"
                    placeholder="80000"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Maximum ($)</label>
                  <input
                    type="number"
                    value={form.desired_salary_max ?? ""}
                    onChange={(e) => setForm({ ...form, desired_salary_max: parseInt(e.target.value) || undefined })}
                    className="input"
                    placeholder="120000"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Earliest Start Date</label>
                  <input
                    type="date"
                    value={form.earliest_start_date ?? ""}
                    onChange={(e) => setForm({ ...form, earliest_start_date: e.target.value })}
                    className="input"
                  />
                </div>
              </div>
            </div>

            {/* Skills */}
            <div className="card p-5">
              <h2 className="font-semibold text-gray-900 mb-4">Skills</h2>
              <div className="flex gap-2 mb-3">
                <input
                  type="text"
                  value={skillInput}
                  onChange={(e) => setSkillInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSkill())}
                  className="input flex-1"
                  placeholder="Add a skill (press Enter)"
                />
                <button onClick={addSkill} className="btn-secondary">Add</button>
              </div>
              <div className="flex flex-wrap gap-2">
                {(form.skills ?? []).map((skill) => (
                  <span key={skill} className="badge bg-gray-100 text-gray-700 gap-1.5 pr-1">
                    {skill}
                    <button
                      onClick={() => removeSkill(skill)}
                      className="text-gray-400 hover:text-red-500 leading-none"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>

            <button
              onClick={() => updateMutation.mutate(form)}
              disabled={updateMutation.isPending}
              className="btn-primary w-full py-3"
            >
              {updateMutation.isPending ? "Saving..." : "Save Profile"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
