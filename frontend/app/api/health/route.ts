import { NextResponse } from "next/server";

// The frontend healthcheck target docker-compose's `frontend` service probes
// (BASE-DESIGN.md §8.2): `wget --spider http://localhost:3000/api/health`. `--spider`
// issues a HEAD request, so this must answer HEAD, not only GET. This is a pure liveness
// probe for the Next.js server itself — it deliberately never calls the backend, so a
// down/unreachable API doesn't take the frontend container out of rotation too.
export const dynamic = "force-dynamic";

function ok(): NextResponse {
  return NextResponse.json({ status: "ok" });
}

export function GET(): NextResponse {
  return ok();
}

export function HEAD(): NextResponse {
  return ok();
}
