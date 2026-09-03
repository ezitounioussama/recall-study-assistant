/**
 * The API client.
 *
 * `credentials: "include"` on every call is the point: the session lives in an
 * HttpOnly cookie, which means JavaScript cannot read it and therefore cannot
 * attach it to a header. The browser sends it, or nothing does.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export type PublicUser = { id: string; email: string; display_name: string };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      credentials: "include",
      headers: { "content-type": "application/json", ...init?.headers },
    });
  } catch {
    // A network-level failure and a 500 need different words. "Something went
    // wrong" for both leaves the reader unable to tell "the API is not running"
    // from "my password is wrong", which is the difference that matters when
    // you are the one running it.
    throw new ApiError(`Cannot reach the API at ${BASE}. Is it running?`, 0);
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : // FastAPI validation errors arrive as an array of objects. Surfacing
          // the raw JSON would be worse than a generic sentence.
          Array.isArray(body?.detail)
          ? "Please check the details you entered."
          : `Request failed (${response.status}).`;
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<PublicUser>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string, displayName: string) =>
    request<PublicUser>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name: displayName }),
    }),

  logout: () => request<{ detail: string }>("/auth/logout", { method: "POST" }),

  me: () => request<PublicUser>("/auth/me"),
};
