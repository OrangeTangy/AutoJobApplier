import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-6">
      <div className="max-w-2xl w-full text-center space-y-8">
        <div>
          <h1 className="text-5xl font-bold text-gray-900 mb-4">AutoJobApplier</h1>
          <p className="text-xl text-gray-600 leading-relaxed">
            AI-powered job application assistant. Discover opportunities, tailor your resume,
            prepare answers — then <strong>you</strong> approve before anything is submitted.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-left">
          {[
            { icon: "🔍", title: "Discover", desc: "Import jobs from email, URLs, or job boards" },
            { icon: "✏️", title: "Tailor", desc: "AI-tailored resume and answers grounded in your profile" },
            { icon: "✅", title: "You Approve", desc: "Review every detail. Submit only what you approve." },
          ].map((f) => (
            <div key={f.title} className="card p-4">
              <div className="text-3xl mb-2">{f.icon}</div>
              <h3 className="font-semibold text-gray-900">{f.title}</h3>
              <p className="text-sm text-gray-600 mt-1">{f.desc}</p>
            </div>
          ))}
        </div>

        <div className="flex gap-4 justify-center">
          <Link href="/login" className="btn-secondary px-8 py-3 text-base">
            Sign In
          </Link>
          <Link href="/register" className="btn-primary px-8 py-3 text-base">
            Get Started
          </Link>
        </div>

        <p className="text-xs text-gray-500">
          No auto-submission. No fabricated qualifications. Every answer grounded in your profile.
        </p>
      </div>
    </main>
  );
}
