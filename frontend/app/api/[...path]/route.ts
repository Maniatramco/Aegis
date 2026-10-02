import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const base = (process.env.API_INTERNAL_URL || "http://api:8000").replace(
    /\/$/,
    "",
  );
  const url = `${base}/api/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");
  try {
    const response = await fetch(url, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method)
        ? undefined
        : await request.arrayBuffer(),
      redirect: "manual",
      cache: "no-store",
      signal: request.signal,
    });
    const output = new Headers(response.headers);
    output.delete("transfer-encoding");
    output.delete("connection");
    output.delete("content-encoding");
    output.delete("content-length");
    return new Response(response.body, {
      status: response.status,
      headers: output,
    });
  } catch {
    return Response.json(
      {
        detail:
          "The API service is unavailable. Check that the api container is running and API_INTERNAL_URL is correct.",
      },
      { status: 502 },
    );
  }
}
export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
  proxy as HEAD,
  proxy as OPTIONS,
};
