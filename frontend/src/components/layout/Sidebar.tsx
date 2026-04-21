"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Briefcase,
  FileText,
  Home,
  User,
  Inbox,
  Mail,
  Building2,
  BarChart3,
} from "lucide-react";
import { cn, clearTokens } from "@/lib/utils";
import { authApi } from "@/lib/api";
import toast from "react-hot-toast";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: Home },
  { href: "/jobs", label: "Jobs", icon: Briefcase },
  { href: "/applications", label: "Applications", icon: Inbox },
  { href: "/resumes", label: "Resumes", icon: FileText },
  { href: "/profile", label: "Profile", icon: User },
];

const NAV_SECONDARY = [
  { href: "/ingestion", label: "Job Ingestion", icon: Mail },
  { href: "/company-rules", label: "Company Rules", icon: Building2 },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } finally {
      clearTokens();
      router.push("/login");
      toast.success("Signed out");
    }
  };

  return (
    <aside className="w-56 bg-white border-r border-gray-200 flex flex-col h-screen sticky top-0">
      <div className="p-4 border-b border-gray-200">
        <span className="text-lg font-bold text-blue-600">AutoJobApplier</span>
      </div>

      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
              pathname.startsWith(href)
                ? "bg-blue-50 text-blue-700"
                : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}

        <div className="pt-4 pb-1">
          <p className="px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
            Settings
          </p>
        </div>
        {NAV_SECONDARY.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
              pathname.startsWith(href)
                ? "bg-blue-50 text-blue-700"
                : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </nav>

      <div className="p-4 border-t border-gray-200">
        <button
          onClick={handleLogout}
          className="w-full text-left px-3 py-2 text-sm text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-md transition-colors"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
