"use client";

/**
 * Ask your notes. Answers stream in; the passages they were built from appear
 * on the right before the first word arrives, and every [n] in the answer is a
 * chip that lights up its source.
 */
import { Suspense, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { AnimatedList } from "@/components/magicui/animated-list";
import { BlurFade } from "@/components/magicui/blur-fade";
import { TypingAnimation } from "@/components/magicui/typing-animation";
import { api, ApiError, type ChatTurn, type Document, type Source } from "@/lib/api";
import { cn } from "@/lib/utils";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  grounded?: boolean;
  citations?: number[];
  streaming?: boolean;
  error?: string;
};

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <Chat />
    </Suspense>
  );
}

function Chat() {
  const params = useSearchParams();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [scope, setScope] = useState<string>(params.get("doc") ?? "");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [highlight, setHighlight] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api.documents.list().then(setDocuments).catch(() => setDocuments([]));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const latest = useMemo(() => [...messages].reverse().find((m) => m.role === "assistant"), [messages]);
  const scopedDoc = documents.find((d) => d.id === scope);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || busy) return;
      setInput("");
      setHighlight(null);
      const userId = crypto.randomUUID();
      const assistantId = crypto.randomUUID();
      const history: ChatTurn[] = messages
        .filter((m) => !m.error && m.content)
        .map((m) => ({ role: m.role, content: m.content }));
      setMessages((ms) => [
        ...ms,
        { id: userId, role: "user", content: q },
        { id: assistantId, role: "assistant", content: "", streaming: true },
      ]);
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;
      const patch = (update: Partial<Message> | ((m: Message) => Partial<Message>)) =>
        setMessages((ms) => ms.map((m) => (m.id === assistantId ? { ...m, ...(typeof update === "function" ? update(m) : update) } : m)));

      try {
        for await (const event of api.chat.stream({ question: q, history, document_ids: scope ? [scope] : null }, controller.signal)) {
          if (event.type === "sources") patch({ sources: event.sources });
          else if (event.type === "token") patch((m) => ({ content: m.content + event.text }));
          else if (event.type === "done") patch({ content: event.answer, grounded: event.grounded, citations: event.citations, streaming: false });
          else if (event.type === "error") patch({ error: event.detail, streaming: false });
        }
      } catch (e) {
        if (!controller.signal.aborted) patch({ error: e instanceof ApiError ? e.message : "The stream broke off.", streaming: false });
      } finally {
        patch({ streaming: false });
        setBusy(false);
        abortRef.current = null;
        textareaRef.current?.focus();
      }
    },
    [busy, messages, scope],
  );

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  };

  const suggestions = useMemo(() => {
    const doc = scopedDoc ?? documents[0];
    if (!doc) return ["What should I upload first?"];
    return [`Summarise “${doc.title}” in five points`, `What are the key terms in “${doc.title}”?`, `Explain the hardest idea in “${doc.title}” simply`];
  }, [documents, scopedDoc]);

  return (
    <div className="grid gap-xl lg:grid-cols-[minmax(0,1fr)_340px]">
      {/* ---- conversation ---- */}
      <section className="flex min-h-[70vh] flex-col">
        <BlurFade inView={false}>
          <header className="flex flex-wrap items-end justify-between gap-md">
            <div>
              <p className="text-body-strong text-ink-muted-48">Ask</p>
              <h1 className="mt-xs text-display-lg text-ink">{scopedDoc ? scopedDoc.title : "Your notes, questioned."}</h1>
            </div>
            <label className="flex items-center gap-xs text-caption text-lead-grey">
              Scope
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                className="min-h-9 rounded-pill border border-hairline bg-canvas px-md text-caption text-ink"
              >
                <option value="">All documents</option>
                {documents.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title}
                  </option>
                ))}
              </select>
            </label>
          </header>
        </BlurFade>

        <div className="flex flex-1 flex-col gap-lg py-xl">
          {messages.length === 0 ? (
            <BlurFade inView={false} delay={0.1} className="my-auto">
              <div className="rounded-lg bg-canvas-parchment p-xl">
                <p className="font-display text-tagline text-ink">
                  <TypingAnimation duration={35} startOnView={false}>
                    Ask anything your material can answer.
                  </TypingAnimation>
                </p>
                <p className="mt-xs max-w-[46ch] text-body text-lead-grey">
                  Recall finds the passages, answers from them, and cites each one. If your notes do not cover it, it says so
                  instead of guessing.
                </p>
                <div className="mt-lg flex flex-wrap gap-xs">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => void send(s)}
                      className="min-h-9 cursor-pointer rounded-pill border border-hairline bg-canvas px-md text-caption text-ink"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </BlurFade>
          ) : null}

          <AnimatePresence initial={false}>
            {messages.map((m) => (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, y: 10, filter: "blur(4px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                transition={{ duration: 0.3 }}
                className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
              >
                {m.role === "user" ? (
                  <p className="max-w-[70%] rounded-lg rounded-br-xs bg-primary px-lg py-sm text-body text-on-primary">{m.content}</p>
                ) : (
                  <Answer message={m} onCite={setHighlight} />
                )}
              </motion.div>
            ))}
          </AnimatePresence>
          <div ref={endRef} />
        </div>

        {/* ---- composer ---- */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
          className="sticky bottom-[120px] flex items-end gap-xs rounded-lg border border-hairline bg-canvas/90 p-xs shadow-float backdrop-blur-xl"
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            rows={1}
            placeholder={scopedDoc ? `Ask about ${scopedDoc.title}…` : "Ask your notes…"}
            className="max-h-40 min-h-11 flex-1 resize-none border-0 bg-transparent px-md py-sm font-[inherit] text-body text-ink outline-none placeholder:text-ink-muted-48"
            onInput={(e) => {
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
            }}
          />
          {busy ? (
            <button type="button" onClick={() => abortRef.current?.abort()} className="min-h-11 cursor-pointer rounded-pill border-0 bg-canvas-parchment px-lg text-body text-ink">
              Stop
            </button>
          ) : (
            <button type="submit" disabled={!input.trim()} className="min-h-11 cursor-pointer rounded-pill border-0 bg-primary px-lg text-body text-on-primary disabled:cursor-not-allowed disabled:opacity-40">
              Ask
            </button>
          )}
        </form>
      </section>

      {/* ---- sources ---- */}
      <aside className="lg:sticky lg:top-[76px] lg:self-start">
        <p className="text-body-strong text-ink-muted-48">Sources</p>
        <p className="mt-xxs text-caption text-lead-grey">
          {latest?.sources?.length
            ? `${latest.sources.length} passage${latest.sources.length === 1 ? "" : "s"} behind the last answer.`
            : "The passages behind an answer appear here, numbered as the answer cites them."}
        </p>
        {latest?.sources?.length ? (
          <AnimatedList key={latest.id} delay={220} className="mt-md items-stretch">
            {latest.sources.map((s) => (
              <SourceCard key={s.chunk_id} source={s} active={highlight === s.index} cited={latest.citations?.includes(s.index) ?? false} />
            ))}
          </AnimatedList>
        ) : null}
      </aside>
    </div>
  );
}

const CITATION = /\[(\d+)\]/g;

function Answer({ message, onCite }: { message: Message; onCite: (n: number) => void }) {
  const parts = message.content.split(CITATION);
  return (
    <div className="max-w-[85%]">
      <div
        className={cn(
          "rounded-lg rounded-bl-xs px-lg py-sm text-body",
          message.grounded === false ? "bg-canvas-parchment text-lead-grey" : "bg-canvas-parchment text-ink",
        )}
      >
        {message.error ? (
          <span role="alert" className="text-ink">
            {message.error}
          </span>
        ) : message.content ? (
          parts.map((part, i) =>
            i % 2 === 1 ? (
              <button
                key={i}
                type="button"
                onClick={() => {
                  onCite(Number(part));
                  document.getElementById(`source-${part}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
                }}
                className="mx-px inline-flex min-h-5 cursor-pointer items-center rounded-pill border-0 bg-primary/10 px-xs align-baseline text-caption-strong text-primary"
              >
                {part}
              </button>
            ) : (
              <span key={i}>{part}</span>
            ),
          )
        ) : (
          <span className="inline-flex gap-xxs py-xxs" aria-label="Thinking">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="size-1.5 rounded-pill bg-ink-muted-48"
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.18 }}
              />
            ))}
          </span>
        )}
        {message.streaming && message.content ? <span className="ml-px inline-block h-[1em] w-px animate-blink-cursor bg-ink align-text-bottom" /> : null}
      </div>
      {message.grounded === false && !message.streaming ? (
        <p className="mt-xs text-caption text-lead-grey">
          Nothing in your material clears the similarity floor for this question.{" "}
          <Link href="/library" className="text-primary">
            Add material
          </Link>{" "}
          or ask something it covers.
        </p>
      ) : null}
    </div>
  );
}

function SourceCard({ source, active, cited }: { source: Source; active: boolean; cited: boolean }) {
  return (
    <article
      id={`source-${source.index}`}
      className={cn(
        "rounded-lg border bg-canvas p-md transition-colors duration-300",
        active ? "border-primary bg-surface-pearl" : "border-hairline",
        !cited && "opacity-70",
      )}
    >
      <header className="flex items-center gap-xs">
        <span className={cn("inline-flex size-6 items-center justify-center rounded-pill text-caption-strong", active || cited ? "bg-primary text-on-primary" : "bg-canvas-parchment text-ink")}>
          {source.index}
        </span>
        <span className="truncate text-caption-strong text-ink">{source.document_title}</span>
        <span className="ml-auto text-caption text-ink-muted-48">§{source.position + 1}</span>
      </header>
      <p className="mt-xs line-clamp-5 text-caption text-ink-muted-80">{source.text}</p>
      <p className="mt-xs text-caption text-ink-muted-48">similarity {source.score.toFixed(2)}</p>
    </article>
  );
}
