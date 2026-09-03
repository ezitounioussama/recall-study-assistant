/**
 * The API client.
 *
 * `credentials: "include"` on every call is the point: the session lives in an
 * HttpOnly cookie, which means JavaScript cannot read it and therefore cannot
 * attach it to a header. The browser sends it, or nothing does.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export type PublicUser = { id: string; email: string; display_name: string };

export type Document = {
  id: string;
  title: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  chunk_count: number;
  created_at: string;
};
export type Chunk = { id: string; position: number; text: string; char_count: number };
export type DocumentDetail = Document & { chunks: Chunk[] };
export type SearchHit = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  position: number;
  text: string;
  score: number;
};

export type Source = SearchHit & { index: number };
export type ChatTurn = { role: "user" | "assistant"; content: string };
export type ChatEvent =
  | { type: "sources"; sources: Source[] }
  | { type: "token"; text: string }
  | { type: "done"; answer: string; grounded: boolean; citations: number[] }
  | { type: "error"; detail: string };

export type CardState = "learning" | "review" | "relearning";
export type Card = {
  id: string;
  document_id: string | null;
  chunk_id: string | null;
  front: string;
  back: string;
  state: CardState;
  step: number | null;
  stability: number | null;
  difficulty: number | null;
  due: string;
  last_review: string | null;
  reps: number;
  lapses: number;
  created_at: string;
  retrievability: number;
};
export type Rating = 1 | 2 | 3 | 4;
export type Preview = Record<"again" | "hard" | "good" | "easy", number>;
export type DueCard = Card & { preview: Preview; source_text: string | null; source_title: string | null };
export type ReviewLog = {
  id: string;
  card_id: string;
  rating: number;
  state_before: CardState;
  retrievability: number;
  elapsed_seconds: number;
  scheduled_seconds: number;
  stability_after: number;
  difficulty_after: number;
  reviewed_at: string;
};
export type ReviewResult = { card: Card; log: ReviewLog };
export type CardStats = {
  total: number;
  learning: number;
  review: number;
  relearning: number;
  due_now: number;
  reviewed_today: number;
  retention_30d: number | null;
  next_due: string | null;
  mean_retrievability: number | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  // A FormData body sets its own multipart boundary; forcing JSON breaks it.
  if (typeof init?.body === "string") headers.set("content-type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, credentials: "include", headers });
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
        : Array.isArray(body?.detail)
          ? "Please check the details you entered."
          : `Request failed (${response.status}).`;
    throw new ApiError(detail, response.status);
  }
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  login: (email: string, password: string) => request<PublicUser>("/auth/login", json({ email, password })),
  register: (email: string, password: string, displayName: string) =>
    request<PublicUser>("/auth/register", json({ email, password, display_name: displayName })),
  logout: () => request<{ detail: string }>("/auth/logout", { method: "POST" }),
  me: () => request<PublicUser>("/auth/me"),

  documents: {
    list: () => request<Document[]>("/documents"),
    get: (id: string) => request<DocumentDetail>(`/documents/${id}`),
    delete: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
    search: (q: string, k = 6) => request<SearchHit[]>(`/documents/search?q=${encodeURIComponent(q)}&k=${k}`),
    upload: (file: File, title?: string) => {
      const form = new FormData();
      form.append("file", file);
      if (title?.trim()) form.append("title", title.trim());
      return request<Document>("/documents", { method: "POST", body: form });
    },
  },

  chat: {
    /**
     * POST /chat and yield its server-sent events as they arrive. EventSource
     * cannot POST, so this reads the body stream and splits on blank lines.
     */
    async *stream(
      body: { question: string; history?: ChatTurn[]; document_ids?: string[] | null },
      signal?: AbortSignal,
    ): AsyncGenerator<ChatEvent> {
      const response = await send("/chat", { ...json(body), signal });
      const reader = response.body?.getReader();
      if (!reader) throw new ApiError("The API returned no stream.", 0);
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.indexOf("\n\n");
        while (boundary !== -1) {
          const raw = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const event = parseEvent(raw);
          if (event) yield event;
          boundary = buffer.indexOf("\n\n");
        }
      }
    },
  },

  cards: {
    list: (params?: { state?: CardState; document_id?: string }) => {
      const query = new URLSearchParams(params as Record<string, string>).toString();
      return request<Card[]>(`/cards${query ? `?${query}` : ""}`);
    },
    due: (limit = 50) => request<DueCard[]>(`/cards/due?limit=${limit}`),
    stats: () => request<CardStats>("/cards/stats"),
    create: (front: string, back: string, document_id?: string) =>
      request<Card>("/cards", json({ front, back, document_id })),
    generate: (document_id: string, per_chunk = 3) => request<Card[]>("/cards/generate", json({ document_id, per_chunk })),
    review: (id: string, rating: Rating) => request<ReviewResult>(`/cards/${id}/review`, json({ rating })),
    delete: (id: string) => request<void>(`/cards/${id}`, { method: "DELETE" }),
  },
};

function parseEvent(raw: string): ChatEvent | null {
  let type = "";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event: ")) type = line.slice(7);
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!type || !data) return null;
  const payload = JSON.parse(data) as unknown;
  switch (type) {
    case "sources":
      return { type, sources: payload as Source[] };
    case "token":
      return { type, text: (payload as { text: string }).text };
    case "done":
      return { type, ...(payload as { answer: string; grounded: boolean; citations: number[] }) };
    case "error":
      return { type, detail: (payload as { detail: string }).detail };
    default:
      return null;
  }
}
