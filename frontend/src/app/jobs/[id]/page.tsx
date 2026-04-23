// Server wrapper for the dynamic [id] route. Renders the real client component.
// For `output: 'export'` we must declare a static params set; the desktop app
// serves an SPA fallback so any concrete id resolves to this placeholder HTML,
// and the client reads the actual id from window.location via useParams().
import Client from "./Client";

export function generateStaticParams() {
  return [{ id: "_" }];
}

export const dynamic = "force-static";
export const dynamicParams = false;

export default function Page() {
  return <Client />;
}
