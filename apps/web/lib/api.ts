export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((d) => `${(d?.loc ?? []).slice(1).join(".")}: ${d?.msg ?? ""}`).join("; ");
  return "Erro inesperado";
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`/api${path}`, {
    credentials: "include",
    ...rest,
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    if (typeof window !== "undefined" && location.pathname !== "/login") window.location.assign("/login");
    throw new ApiError("Sessão expirada", 401);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(detailText(body?.detail), res.status);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
