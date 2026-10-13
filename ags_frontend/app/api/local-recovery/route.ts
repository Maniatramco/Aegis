import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const loopback = (host: string) => ["127.0.0.1", "localhost", "[::1]"].includes(host);

export async function GET(request: NextRequest) {
  try {
    const backend = new URL(process.env.API_INTERNAL_URL || "http://api:8000");
    // Next can canonicalize nextUrl to localhost even when the browser uses
    // 127.0.0.1. Use the actual request host to keep recovery cookies same-site.
    const browserHost = new URL(`http://${request.headers.get("host") || ""}`);
    if (!loopback(browserHost.hostname) || !loopback(backend.hostname) || backend.protocol !== "http:") {
      return Response.json({ detail: "Direct password reset is available only in the local desktop app." }, { status: 403 });
    }
    // Use the browser's hostname so localhost and 127.0.0.1 cookies stay same-site.
    // Recovery requests go directly to the API; the frontend proxy cannot relay them.
    backend.hostname = browserHost.hostname;
    backend.username = "";
    backend.password = "";
    backend.pathname = "/api/auth/recovery";
    backend.search = "";
    backend.hash = "";
    return Response.json({ endpoint: backend.toString() }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ detail: "Local password recovery is not configured." }, { status: 503 });
  }
}
